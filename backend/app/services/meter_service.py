"""Usage meter creation, idempotent event ingestion, and aggregation service."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.app.models.base import utcnow
from backend.app.models.billing_cycles import BillingCycle
from backend.app.models.customers import Customer
from backend.app.models.events import DomainEventType
from backend.app.models.invoices import Invoice, InvoiceItem, InvoiceStatus
from backend.app.models.meters import (
    AggregationType,
    UsageAggregate,
    UsageAggregateStatus,
    UsageEvent,
    UsageEventStatus,
    UsageMeter,
)
from backend.app.models.subscriptions import Subscription
from backend.app.services import audit
from backend.app.services.unit_of_work import UnitOfWork


def create_meter(
    db: Session,
    organization_id: str,
    code: str,
    name: str,
    unit_name: str = "unit",
    aggregation_type: AggregationType = AggregationType.SUM,
    description: Optional[str] = None,
) -> UsageMeter:
    existing = (
        db.query(UsageMeter)
        .filter(UsageMeter.organization_id == organization_id, UsageMeter.code == code)
        .first()
    )
    if existing:
        raise ConflictAppError(f"Meter with code '{code}' already exists.")

    meter = UsageMeter(
        organization_id=organization_id,
        code=code.strip().lower(),
        name=name.strip(),
        unit_name=unit_name.strip(),
        aggregation_type=aggregation_type,
        description=description,
        is_active=True,
    )
    db.add(meter)
    db.commit()
    db.refresh(meter)
    return meter


def get_meter(db: Session, organization_id: str, meter_id_or_code: str) -> UsageMeter:
    meter = (
        db.query(UsageMeter)
        .filter(
            UsageMeter.organization_id == organization_id,
            (UsageMeter.id == meter_id_or_code) | (UsageMeter.code == meter_id_or_code),
        )
        .first()
    )
    if not meter:
        raise NotFoundAppError(f"Meter '{meter_id_or_code}' not found.")
    return meter


def list_meters(db: Session, organization_id: str) -> List[UsageMeter]:
    return (
        db.query(UsageMeter)
        .filter(UsageMeter.organization_id == organization_id)
        .order_by(UsageMeter.name.asc())
        .all()
    )


def record_usage_event(
    db: Session,
    organization_id: str,
    meter_id_or_code: str,
    customer_id: str,
    quantity: Decimal,
    idempotency_key: str,
    subscription_id: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    properties: Optional[Dict[str, Any]] = None,
) -> UsageEvent:
    """Ingests a raw usage event idempotently."""
    meter = get_meter(db, organization_id, meter_id_or_code)

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.organization_id == organization_id)
        .first()
    )
    if not customer:
        raise NotFoundAppError(f"Customer {customer_id} not found.")

    if not idempotency_key or not idempotency_key.strip():
        raise ValidationAppError("Idempotency key is required for usage events.")

    # Idempotent deduplication check
    existing_event = (
        db.query(UsageEvent)
        .filter(
            UsageEvent.organization_id == organization_id,
            UsageEvent.meter_id == meter.id,
            UsageEvent.idempotency_key == idempotency_key.strip(),
        )
        .first()
    )
    if existing_event:
        return existing_event

    event_time = timestamp or utcnow()
    if subscription_id:
        from backend.app.models.billing_cycles import BillingCycle, BillingCycleStatus
        frozen_cycle = db.query(BillingCycle).filter(
            BillingCycle.subscription_id == subscription_id,
            BillingCycle.period_start <= event_time.date(),
            BillingCycle.period_end >= event_time.date(),
            BillingCycle.status == BillingCycleStatus.FINALIZED,
        ).first()
        if frozen_cycle:
            raise ConflictAppError(
                f"Cannot record usage for cycle {frozen_cycle.cycle_number} because it has already been finalized."
            )

    event = UsageEvent(
        organization_id=organization_id,
        meter_id=meter.id,
        customer_id=customer_id,
        subscription_id=subscription_id,
        quantity=Decimal(str(quantity)),
        timestamp=event_time,
        idempotency_key=idempotency_key.strip(),
        properties=properties or {},
        status=UsageEventStatus.ACCEPTED,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def aggregate_subscription_usage(
    db: Session,
    organization_id: str,
    meter_id: str,
    subscription_id: str,
    period_start: date,
    period_end: date,
) -> Decimal:
    """Computes aggregated consumption for a subscription between period_start and period_end."""
    meter = (
        db.query(UsageMeter)
        .filter(UsageMeter.id == meter_id, UsageMeter.organization_id == organization_id)
        .first()
    )
    if not meter:
        raise NotFoundAppError(f"Meter {meter_id} not found.")

    # Base query
    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt = datetime.combine(period_end, datetime.max.time())

    query = db.query(UsageEvent).filter(
        UsageEvent.organization_id == organization_id,
        UsageEvent.meter_id == meter.id,
        UsageEvent.subscription_id == subscription_id,
        UsageEvent.status == UsageEventStatus.ACCEPTED,
        UsageEvent.timestamp >= start_dt,
        UsageEvent.timestamp <= end_dt,
    )

    if meter.aggregation_type == AggregationType.SUM:
        total = db.query(func.coalesce(func.sum(UsageEvent.quantity), Decimal("0"))).filter(
            UsageEvent.organization_id == organization_id,
            UsageEvent.meter_id == meter.id,
            UsageEvent.subscription_id == subscription_id,
            UsageEvent.status == UsageEventStatus.ACCEPTED,
            UsageEvent.timestamp >= start_dt,
            UsageEvent.timestamp <= end_dt,
        ).scalar()
        return Decimal(str(total))

    elif meter.aggregation_type == AggregationType.MAX:
        val = db.query(func.coalesce(func.max(UsageEvent.quantity), Decimal("0"))).filter(
            UsageEvent.organization_id == organization_id,
            UsageEvent.meter_id == meter.id,
            UsageEvent.subscription_id == subscription_id,
            UsageEvent.status == UsageEventStatus.ACCEPTED,
            UsageEvent.timestamp >= start_dt,
            UsageEvent.timestamp <= end_dt,
        ).scalar()
        return Decimal(str(val))

    elif meter.aggregation_type == AggregationType.COUNT:
        count = query.count()
        return Decimal(str(count))

    elif meter.aggregation_type == AggregationType.LAST:
        latest = query.order_by(desc(UsageEvent.timestamp)).first()
        return Decimal(str(latest.quantity)) if latest else Decimal("0")

    return Decimal("0")


def finalize_usage_for_cycle(
    db: Session,
    ctx: CurrentContext,
    subscription_id: str,
    billing_cycle_id: str,
    unit_price: Decimal = Decimal("0.50"),
) -> UsageAggregate:
    """Aggregates and finalizes usage charges for a billing cycle."""
    cycle = (
        db.query(BillingCycle)
        .filter(BillingCycle.id == billing_cycle_id, BillingCycle.organization_id == ctx.organization_id)
        .first()
    )
    if not cycle:
        raise NotFoundAppError(f"Billing cycle {billing_cycle_id} not found.")

    sub = (
        db.query(Subscription)
        .filter(Subscription.id == subscription_id, Subscription.organization_id == ctx.organization_id)
        .first()
    )
    if not sub:
        raise NotFoundAppError(f"Subscription {subscription_id} not found.")

    # Find meters used by subscription
    meters = list_meters(db, ctx.organization_id)
    if not meters:
        raise ValidationAppError("No usage meters configured for this organization.")

    primary_meter = meters[0]
    total_qty = aggregate_subscription_usage(
        db,
        organization_id=ctx.organization_id,
        meter_id=primary_meter.id,
        subscription_id=subscription_id,
        period_start=cycle.period_start,
        period_end=cycle.period_end,
    )

    rated_amount = (total_qty * Decimal(str(unit_price))).quantize(Decimal("0.01"))

    # Create or update aggregate
    aggregate = (
        db.query(UsageAggregate)
        .filter(
            UsageAggregate.organization_id == ctx.organization_id,
            UsageAggregate.meter_id == primary_meter.id,
            UsageAggregate.subscription_id == subscription_id,
            UsageAggregate.period_start == cycle.period_start,
            UsageAggregate.period_end == cycle.period_end,
        )
        .first()
    )
    if not aggregate:
        aggregate = UsageAggregate(
            organization_id=ctx.organization_id,
            meter_id=primary_meter.id,
            subscription_id=subscription_id,
            billing_cycle_id=cycle.id,
            period_start=cycle.period_start,
            period_end=cycle.period_end,
            total_quantity=total_qty,
            rated_amount=rated_amount,
            status=UsageAggregateStatus.FINALIZED,
            finalized_at=utcnow(),
        )
        db.add(aggregate)
    else:
        aggregate.total_quantity = total_qty
        aggregate.rated_amount = rated_amount
        aggregate.status = UsageAggregateStatus.FINALIZED
        aggregate.finalized_at = utcnow()

    # Freeze billing cycle
    from backend.app.models.billing_cycles import BillingCycleStatus, SubscriptionItem, SubscriptionItemStatus, SubscriptionItemType
    cycle.status = BillingCycleStatus.FINALIZED
    cycle.finalized_at = utcnow()

    # Link metered usage to SubscriptionItem
    metered_item = db.query(SubscriptionItem).filter(
        SubscriptionItem.subscription_id == subscription_id,
        SubscriptionItem.item_type == SubscriptionItemType.METERED,
        SubscriptionItem.status == SubscriptionItemStatus.ACTIVE,
    ).first()
    if metered_item:
        metered_item.quantity = total_qty
        metered_item.unit_price = Decimal(str(unit_price))
    else:
        metered_item = SubscriptionItem(
            organization_id=ctx.organization_id,
            subscription_id=subscription_id,
            item_type=SubscriptionItemType.METERED,
            quantity=total_qty,
            unit_price=Decimal(str(unit_price)),
            status=SubscriptionItemStatus.ACTIVE,
        )
        db.add(metered_item)

    db.commit()
    db.refresh(aggregate)
    return aggregate

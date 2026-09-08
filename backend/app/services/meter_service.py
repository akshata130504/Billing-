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


def _resolve_metered_unit_price(db: Session, sub: Subscription) -> Decimal:
    """The rate to bill usage at: the subscription's price override, else the plan's list price.

    Metered usage used to be rated at a hard-coded Decimal("0.50") regardless of the
    customer's contract, which mis-billed every metered subscription. There is exactly
    one price on a subscription/plan pair, so ASSUMPTION: every meter on the org rates
    at that same per-unit price. Per-meter pricing would need a meter->price mapping
    (e.g. a price column on UsageMeter or a plan/meter join table) which does not exist
    in the schema today.
    """
    from backend.app.models.catalog import Plan
    from backend.app.services.subscription_service import effective_unit_price

    plan = db.query(Plan).filter(Plan.id == sub.plan_id).first() if sub.plan_id else None
    if plan is None:
        raise ValidationAppError(
            "Cannot rate usage: subscription "
            f"{sub.id} has no resolvable plan, so there is no unit price to bill usage at. "
            "Attach a plan to the subscription or pass an explicit unit_price override."
        )

    price = effective_unit_price(sub, plan)
    if price is None or Decimal(str(price)) <= 0:
        raise ValidationAppError(
            "Cannot rate usage: neither subscription "
            f"{sub.id} nor plan '{plan.name}' defines a positive unit price. "
            "Set the plan's unit amount or pass an explicit unit_price override."
        )
    return Decimal(str(price))


def finalize_usage_for_cycle(
    db: Session,
    ctx: CurrentContext,
    subscription_id: str,
    billing_cycle_id: str,
    unit_price: Optional[Decimal] = None,
) -> List[UsageAggregate]:
    """Aggregates and finalizes usage charges for a billing cycle.

    Every meter on the organization that recorded usage for this subscription inside the
    cycle is rated (previously only the first meter alphabetically was billed and all the
    others were silently dropped). One UsageAggregate and one invoice line is produced per
    meter with usage.

    `unit_price` is an optional caller override; when omitted the real contracted price is
    derived from the subscription/plan instead of a made-up default rate.
    """
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

    meters = list_meters(db, ctx.organization_id)
    if not meters:
        raise ValidationAppError("No usage meters configured for this organization.")

    if unit_price is not None:
        rate = Decimal(str(unit_price))
    else:
        rate = _resolve_metered_unit_price(db, sub)

    # Rate EVERY meter that has usage in this cycle, not just the first one.
    rated: List[Dict[str, Any]] = []
    for meter in meters:
        qty = aggregate_subscription_usage(
            db,
            organization_id=ctx.organization_id,
            meter_id=meter.id,
            subscription_id=subscription_id,
            period_start=cycle.period_start,
            period_end=cycle.period_end,
        )
        if qty <= 0:
            continue
        rated.append(
            {
                "meter": meter,
                "quantity": qty,
                "amount": (qty * rate).quantize(Decimal("0.01")),
            }
        )

    aggregates: List[UsageAggregate] = []
    for entry in rated:
        meter = entry["meter"]
        aggregate = (
            db.query(UsageAggregate)
            .filter(
                UsageAggregate.organization_id == ctx.organization_id,
                UsageAggregate.meter_id == meter.id,
                UsageAggregate.subscription_id == subscription_id,
                UsageAggregate.period_start == cycle.period_start,
                UsageAggregate.period_end == cycle.period_end,
            )
            .first()
        )
        if not aggregate:
            aggregate = UsageAggregate(
                organization_id=ctx.organization_id,
                meter_id=meter.id,
                subscription_id=subscription_id,
                billing_cycle_id=cycle.id,
                period_start=cycle.period_start,
                period_end=cycle.period_end,
                total_quantity=entry["quantity"],
                rated_amount=entry["amount"],
                status=UsageAggregateStatus.FINALIZED,
                finalized_at=utcnow(),
            )
            db.add(aggregate)
        else:
            aggregate.billing_cycle_id = cycle.id
            aggregate.total_quantity = entry["quantity"]
            aggregate.rated_amount = entry["amount"]
            aggregate.status = UsageAggregateStatus.FINALIZED
            aggregate.finalized_at = utcnow()
        aggregates.append(aggregate)

    # Freeze billing cycle
    from backend.app.models.billing_cycles import (
        BillingCycleStatus,
        SubscriptionItem,
        SubscriptionItemStatus,
        SubscriptionItemType,
    )
    cycle.status = BillingCycleStatus.FINALIZED
    cycle.finalized_at = utcnow()

    prior_invoice_id = next((a.invoice_id for a in aggregates if a.invoice_id), None)
    invoice = _build_usage_invoice(db, ctx, sub, cycle, rated, rate, prior_invoice_id)
    if invoice is not None:
        db.flush()
        for aggregate in aggregates:
            aggregate.invoice_id = invoice.id
        if not cycle.invoice_id:
            cycle.invoice_id = invoice.id

    # Link metered usage to SubscriptionItem. SubscriptionItem has no meter reference,
    # so a single METERED item carries the combined usage across meters at the contracted rate.
    total_qty = sum((e["quantity"] for e in rated), Decimal("0"))
    metered_item = db.query(SubscriptionItem).filter(
        SubscriptionItem.subscription_id == subscription_id,
        SubscriptionItem.item_type == SubscriptionItemType.METERED,
        SubscriptionItem.status == SubscriptionItemStatus.ACTIVE,
    ).first()
    if metered_item:
        metered_item.quantity = total_qty
        metered_item.unit_price = rate
    else:
        metered_item = SubscriptionItem(
            organization_id=ctx.organization_id,
            subscription_id=subscription_id,
            item_type=SubscriptionItemType.METERED,
            quantity=total_qty,
            unit_price=rate,
            status=SubscriptionItemStatus.ACTIVE,
        )
        db.add(metered_item)

    db.commit()
    for aggregate in aggregates:
        db.refresh(aggregate)
    return aggregates


def _build_usage_invoice(
    db: Session,
    ctx: CurrentContext,
    sub: Subscription,
    cycle: BillingCycle,
    rated: List[Dict[str, Any]],
    rate: Decimal,
    prior_invoice_id: Optional[str] = None,
) -> Optional[Invoice]:
    """Creates (or rebuilds) the draft usage invoice for a cycle with one line per meter.

    Only an invoice this function previously raised (reached through the aggregates'
    invoice_id) is rebuilt; the cycle's recurring subscription invoice is never touched.
    """
    if not rated:
        return None

    from backend.app.core.security import generate_opaque_token
    from backend.app.services.numbering import next_number

    existing_id = prior_invoice_id
    invoice = None
    if existing_id:
        invoice = (
            db.query(Invoice)
            .filter(Invoice.id == existing_id, Invoice.organization_id == ctx.organization_id)
            .first()
        )
        if invoice is not None and invoice.status != InvoiceStatus.DRAFT:
            # Never mutate an issued document; the aggregates keep pointing at it.
            return invoice

    subtotal = sum((e["amount"] for e in rated), Decimal("0")).quantize(Decimal("0.01"))
    currency = sub.plan.currency if sub.plan is not None else "INR"

    if invoice is None:
        invoice = Invoice(
            organization_id=ctx.organization_id,
            customer_id=sub.customer_id,
            subscription_id=sub.id,
            invoice_number=next_number(db, ctx.organization_id, "invoice"),
            issue_date=cycle.period_end,
            due_date=cycle.period_end,
            status=InvoiceStatus.DRAFT,
            currency=currency,
            public_token=generate_opaque_token(32),
            notes=f"Metered usage for {cycle.period_start} to {cycle.period_end}",
        )
        db.add(invoice)
    else:
        invoice.items.clear()

    for position, entry in enumerate(rated):
        meter = entry["meter"]
        invoice.items.append(
            InvoiceItem(
                organization_id=ctx.organization_id,
                description=f"{meter.name} - {entry['quantity']} {meter.unit_name}",
                quantity=entry["quantity"],
                unit_price=rate,
                amount=entry["amount"],
                tax_rate_pct=Decimal("0"),
                position=position,
            )
        )

    invoice.subtotal = subtotal
    invoice.tax_amount = Decimal("0.00")
    invoice.total = subtotal
    invoice.amount_paid = Decimal("0.00")
    invoice.amount_due = subtotal
    return invoice

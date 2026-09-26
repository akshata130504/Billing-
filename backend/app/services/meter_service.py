"""Usage meter creation, idempotent event ingestion, and aggregation service."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.billing_cycles import BillingCycle
from backend.app.models.customers import Customer
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.meters import (
    AggregationType,
    UsageAggregate,
    UsageAggregateStatus,
    UsageEvent,
    UsageEventStatus,
    UsageMeter,
)
from backend.app.models.subscriptions import Subscription


def create_meter(
    db: Session,
    organization_id: str,
    code: str,
    name: str,
    unit_name: str = "unit",
    aggregation_type: AggregationType = AggregationType.SUM,
    description: Optional[str] = None,
    unit_price: Optional[Decimal] = None,
) -> UsageMeter:
    normalized_code = code.strip().lower()
    # Codes are stored lower-cased, so the duplicate check must compare lower-cased too
    # (otherwise "API_Calls" slipped past the check and then hit the DB constraint).
    existing = (
        db.query(UsageMeter)
        .filter(UsageMeter.organization_id == organization_id, func.lower(UsageMeter.code) == normalized_code)
        .first()
    )
    if existing:
        raise ConflictAppError(f"Meter with code '{normalized_code}' already exists.")

    meter = UsageMeter(
        organization_id=organization_id,
        code=normalized_code,
        name=name.strip(),
        unit_name=unit_name.strip(),
        aggregation_type=aggregation_type,
        description=description,
        unit_price=Decimal(str(unit_price)) if unit_price is not None else None,
        is_active=True,
    )
    db.add(meter)
    db.commit()
    db.refresh(meter)
    return meter


def update_meter(db: Session, organization_id: str, meter_id_or_code: str, changes: Dict[str, Any]) -> UsageMeter:
    meter = get_meter(db, organization_id, meter_id_or_code)
    for field in ("name", "unit_name", "description", "is_active"):
        if field in changes and changes[field] is not None:
            setattr(meter, field, changes[field])
    if "unit_price" in changes:
        meter.unit_price = Decimal(str(changes["unit_price"])) if changes["unit_price"] is not None else None
    db.commit()
    db.refresh(meter)
    return meter


def get_meter(db: Session, organization_id: str, meter_id_or_code: str) -> UsageMeter:
    meter = (
        db.query(UsageMeter)
        .filter(
            UsageMeter.organization_id == organization_id,
            (UsageMeter.id == meter_id_or_code) | (UsageMeter.code == meter_id_or_code.strip().lower()),
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


def _day_bounds(period_start: date, period_end: date):
    """Half-open [period_start 00:00, period_end 00:00) window.

    Billing periods are contiguous (one period's end is the next one's start), so an
    inclusive end double-counted every event on the boundary day in both cycles.
    """
    return datetime.combine(period_start, datetime.min.time()), datetime.combine(period_end, datetime.min.time())


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
    commit: bool = True,
) -> UsageEvent:
    """Ingests a raw usage event idempotently. `commit=False` lets a batch commit once."""
    meter = get_meter(db, organization_id, meter_id_or_code)
    if not meter.is_active:
        raise ValidationAppError(f"Meter '{meter.code}' is inactive.")

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.organization_id == organization_id)
        .first()
    )
    if not customer:
        raise NotFoundAppError(f"Customer {customer_id} not found.")

    if subscription_id:
        # The subscription must belong to this organization AND this customer - otherwise
        # usage could be attached to (and billed on) another tenant's subscription.
        sub = (
            db.query(Subscription)
            .filter(Subscription.id == subscription_id, Subscription.organization_id == organization_id)
            .first()
        )
        if sub is None:
            raise NotFoundAppError(f"Subscription {subscription_id} not found.")
        if sub.customer_id != customer_id:
            raise ValidationAppError(
                "The subscription does not belong to this customer.",
                {"fields": {"subscription_id": "belongs to a different customer"}},
            )

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
        from backend.app.models.billing_cycles import BillingCycleStatus

        event_day = event_time.date()
        frozen_cycle = db.query(BillingCycle).filter(
            BillingCycle.subscription_id == subscription_id,
            BillingCycle.period_start <= event_day,
            BillingCycle.period_end > event_day,
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
    if commit:
        db.commit()
        db.refresh(event)
    else:
        db.flush()
    return event


def record_usage_events_batch(db: Session, organization_id: str, events: List[Dict[str, Any]]) -> List[UsageEvent]:
    """All-or-nothing batch ingestion: one commit, and any invalid event rolls the whole batch back."""
    results: List[UsageEvent] = []
    try:
        for ev in events:
            results.append(record_usage_event(db, organization_id=organization_id, commit=False, **ev))
        db.commit()
    except Exception:
        db.rollback()
        raise
    for ev in results:
        db.refresh(ev)
    return results


def aggregate_subscription_usage(
    db: Session,
    organization_id: str,
    meter_id: str,
    subscription_id: str,
    period_start: date,
    period_end: date,
) -> Decimal:
    """Computes aggregated consumption for a subscription over [period_start, period_end)."""
    meter = (
        db.query(UsageMeter)
        .filter(UsageMeter.id == meter_id, UsageMeter.organization_id == organization_id)
        .first()
    )
    if not meter:
        raise NotFoundAppError(f"Meter {meter_id} not found.")

    start_dt, end_dt = _day_bounds(period_start, period_end)
    filters = (
        UsageEvent.organization_id == organization_id,
        UsageEvent.meter_id == meter.id,
        UsageEvent.subscription_id == subscription_id,
        UsageEvent.status == UsageEventStatus.ACCEPTED,
        UsageEvent.timestamp >= start_dt,
        UsageEvent.timestamp < end_dt,
    )
    query = db.query(UsageEvent).filter(*filters)

    if meter.aggregation_type == AggregationType.SUM:
        total = db.query(func.coalesce(func.sum(UsageEvent.quantity), Decimal("0"))).filter(*filters).scalar()
        return Decimal(str(total))

    elif meter.aggregation_type == AggregationType.MAX:
        val = db.query(func.coalesce(func.max(UsageEvent.quantity), Decimal("0"))).filter(*filters).scalar()
        return Decimal(str(val))

    elif meter.aggregation_type == AggregationType.COUNT:
        count = query.count()
        return Decimal(str(count))

    elif meter.aggregation_type == AggregationType.LAST:
        latest = query.order_by(desc(UsageEvent.timestamp)).first()
        return Decimal(str(latest.quantity)) if latest else Decimal("0")

    return Decimal("0")


def subscription_has_usage(db: Session, subscription_id: str, period_start: date, period_end: date) -> bool:
    start_dt, end_dt = _day_bounds(period_start, period_end)
    return (
        db.query(UsageEvent.id)
        .filter(
            UsageEvent.subscription_id == subscription_id,
            UsageEvent.status == UsageEventStatus.ACCEPTED,
            UsageEvent.timestamp >= start_dt,
            UsageEvent.timestamp < end_dt,
        )
        .first()
        is not None
    )


def list_billing_cycles(db: Session, organization_id: str, subscription_id: str) -> List[BillingCycle]:
    sub = (
        db.query(Subscription)
        .filter(Subscription.id == subscription_id, Subscription.organization_id == organization_id)
        .first()
    )
    if not sub:
        raise NotFoundAppError(f"Subscription {subscription_id} not found.")
    return (
        db.query(BillingCycle)
        .filter(BillingCycle.organization_id == organization_id, BillingCycle.subscription_id == subscription_id)
        .order_by(desc(BillingCycle.period_start))
        .all()
    )


def finalize_usage_for_cycle(
    db: Session,
    ctx: CurrentContext,
    subscription_id: str,
    billing_cycle_id: str,
    unit_price: Optional[Decimal] = None,
) -> List[UsageAggregate]:
    """Aggregates and finalizes usage charges for a billing cycle (interactive request)."""
    return _finalize_usage(
        db,
        organization_id=ctx.organization_id,
        subscription_id=subscription_id,
        billing_cycle_id=billing_cycle_id,
        unit_price=unit_price,
        created_by_id=ctx.user_id,
    )


def finalize_usage_for_cycle_system(
    db: Session, *, organization_id: str, subscription_id: str, billing_cycle_id: str
) -> List[UsageAggregate]:
    """Scheduler variant (no request context): finalizes the cycle that is ending at renewal."""
    return _finalize_usage(
        db,
        organization_id=organization_id,
        subscription_id=subscription_id,
        billing_cycle_id=billing_cycle_id,
    )


def _finalize_usage(
    db: Session,
    *,
    organization_id: str,
    subscription_id: str,
    billing_cycle_id: str,
    unit_price: Optional[Decimal] = None,
    created_by_id: Optional[str] = None,
) -> List[UsageAggregate]:
    """Every meter on the organization that recorded usage for this subscription inside the
    cycle is rated at that meter's own `unit_price` (or the explicit `unit_price` override).
    One UsageAggregate and one invoice line is produced per meter with usage.

    Meters without a price rate at 0 and are logged/flagged on the invoice line - usage
    used to be rated at the plan's recurring price, which has nothing to do with usage.
    """
    cycle = (
        db.query(BillingCycle)
        .filter(BillingCycle.id == billing_cycle_id, BillingCycle.organization_id == organization_id)
        .first()
    )
    if not cycle:
        raise NotFoundAppError(f"Billing cycle {billing_cycle_id} not found.")
    if cycle.subscription_id != subscription_id:
        raise ValidationAppError(
            "The billing cycle does not belong to this subscription.",
            {"fields": {"cycle_id": "belongs to a different subscription"}},
        )

    sub = (
        db.query(Subscription)
        .filter(Subscription.id == subscription_id, Subscription.organization_id == organization_id)
        .first()
    )
    if not sub:
        raise NotFoundAppError(f"Subscription {subscription_id} not found.")

    meters = list_meters(db, organization_id)
    if not meters:
        raise ValidationAppError("No usage meters configured for this organization.")

    override = Decimal(str(unit_price)) if unit_price is not None else None

    # Rate EVERY meter that has usage in this cycle, not just the first one.
    rated: List[Dict[str, Any]] = []
    for meter in meters:
        qty = aggregate_subscription_usage(
            db,
            organization_id=organization_id,
            meter_id=meter.id,
            subscription_id=subscription_id,
            period_start=cycle.period_start,
            period_end=cycle.period_end,
        )
        if qty <= 0:
            continue
        if override is not None:
            rate, unpriced = override, False
        elif meter.unit_price is not None:
            rate, unpriced = Decimal(str(meter.unit_price)), False
        else:
            rate, unpriced = Decimal("0"), True
            logger.warning(
                "Usage meter %s has no unit_price; %s %s for subscription %s rated at 0",
                meter.code,
                qty,
                meter.unit_name,
                subscription_id,
            )
        rated.append(
            {
                "meter": meter,
                "quantity": qty,
                "rate": rate,
                "unpriced": unpriced,
                "amount": (qty * rate).quantize(Decimal("0.01")),
            }
        )

    aggregates: List[UsageAggregate] = []
    for entry in rated:
        meter = entry["meter"]
        aggregate = (
            db.query(UsageAggregate)
            .filter(
                UsageAggregate.organization_id == organization_id,
                UsageAggregate.meter_id == meter.id,
                UsageAggregate.subscription_id == subscription_id,
                UsageAggregate.period_start == cycle.period_start,
                UsageAggregate.period_end == cycle.period_end,
            )
            .first()
        )
        if not aggregate:
            aggregate = UsageAggregate(
                organization_id=organization_id,
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
    invoice = _build_usage_invoice(db, organization_id, sub, cycle, rated, prior_invoice_id, created_by_id)
    if invoice is not None:
        db.flush()
        for aggregate in aggregates:
            aggregate.invoice_id = invoice.id
        if not cycle.invoice_id or cycle.invoice_id == prior_invoice_id:
            cycle.invoice_id = invoice.id

    # Link metered usage to SubscriptionItem. SubscriptionItem has no meter reference,
    # so a single METERED item carries the combined usage and its blended rate.
    total_qty = sum((e["quantity"] for e in rated), Decimal("0"))
    total_amount = sum((e["amount"] for e in rated), Decimal("0"))
    blended_rate = (total_amount / total_qty).quantize(Decimal("0.01")) if total_qty > 0 else Decimal("0")
    metered_item = db.query(SubscriptionItem).filter(
        SubscriptionItem.subscription_id == subscription_id,
        SubscriptionItem.item_type == SubscriptionItemType.METERED,
        SubscriptionItem.status == SubscriptionItemStatus.ACTIVE,
    ).first()
    if metered_item:
        metered_item.quantity = total_qty
        metered_item.unit_price = blended_rate
    else:
        metered_item = SubscriptionItem(
            organization_id=organization_id,
            subscription_id=subscription_id,
            item_type=SubscriptionItemType.METERED,
            quantity=total_qty,
            unit_price=blended_rate,
            status=SubscriptionItemStatus.ACTIVE,
        )
        db.add(metered_item)

    db.commit()
    for aggregate in aggregates:
        db.refresh(aggregate)
    return aggregates


def _build_usage_invoice(
    db: Session,
    organization_id: str,
    sub: Subscription,
    cycle: BillingCycle,
    rated: List[Dict[str, Any]],
    prior_invoice_id: Optional[str] = None,
    created_by_id: Optional[str] = None,
) -> Optional[Invoice]:
    """Creates (or rebuilds) the draft usage invoice for a cycle with one line per meter,
    through the standard invoice builder so it carries the plan product's tax rate.

    Only an invoice this function previously raised (reached through the aggregates'
    invoice_id) is rebuilt; the cycle's recurring subscription invoice is never touched.
    """
    if not rated:
        return None

    from backend.app.services.invoice_service import create_invoice_record
    from backend.app.services.money import LineInput
    from backend.app.services.subscription_service import plan_tax_rate

    if prior_invoice_id:
        prior = (
            db.query(Invoice)
            .filter(Invoice.id == prior_invoice_id, Invoice.organization_id == organization_id)
            .first()
        )
        if prior is not None and prior.status != InvoiceStatus.DRAFT:
            # Never mutate an issued document; the aggregates keep pointing at it.
            return prior
        if prior is not None:
            # A draft is rebuilt from scratch (drafts are freely deletable).
            if cycle.invoice_id == prior.id:
                cycle.invoice_id = None
            for agg in db.query(UsageAggregate).filter(UsageAggregate.invoice_id == prior.id).all():
                agg.invoice_id = None
            db.flush()
            db.delete(prior)
            db.flush()

    if sum((e["amount"] for e in rated), Decimal("0")) <= 0:
        # Nothing billable (e.g. only unpriced meters): record the aggregates, no invoice.
        return None

    customer = db.query(Customer).filter(Customer.id == sub.customer_id).first()
    plan = sub.plan
    tax_rate = plan_tax_rate(plan, customer)
    lines = []
    for entry in rated:
        meter = entry["meter"]
        desc_text = f"{meter.name} - {entry['quantity']} {meter.unit_name}"
        if entry["unpriced"]:
            desc_text += " (unpriced meter - rated at 0)"
        lines.append(
            LineInput(
                description=desc_text,
                quantity=entry["quantity"],
                unit_price=entry["rate"],
                tax_rate_pct=tax_rate,
                product_id=plan.product_id if plan is not None else None,
            )
        )
    # period_start stays NULL on purpose: (subscription_id, period_start) identifies the
    # recurring period invoice, which this separate usage invoice is not.
    return create_invoice_record(
        db,
        organization_id=organization_id,
        customer=customer,
        lines=lines,
        issue_date=cycle.period_end,
        due_date=cycle.period_end,
        currency=sub.currency or (plan.currency if plan is not None else None),
        notes=f"Metered usage for {cycle.period_start} to {cycle.period_end}",
        subscription_id=sub.id,
        created_by_id=created_by_id,
        status=InvoiceStatus.DRAFT,
    )

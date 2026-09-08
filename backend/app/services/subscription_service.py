"""Subscriptions: period arithmetic, lifecycle and renewal invoices (contract §7)."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import EntityNotFoundError, InvalidStateError, ValidationAppError
from backend.app.models import (
    INTERVAL_MONTHS,
    BillingInterval,
    Customer,
    Invoice,
    InvoiceStatus,
    Plan,
    PricingModel,
    Subscription,
    SubscriptionStatus,
    utcnow,
)
from backend.app.schemas.common_refs import customer_ref, iso_dt, money_str
from backend.app.schemas.subscriptions import SubscriptionCreate, SubscriptionUpdate
from backend.app.services import audit
from backend.app.services.invoice_service import (
    create_invoice_record,
    email_invoice,
    get_customer,
    get_invoice,
    snapshot as invoice_snapshot,
)
from backend.app.services.money import D, LineInput, q2
from backend.app.services.numbering import next_number
from backend.app.services.pagination import PageParams, apply_sort, paginate

SUBSCRIPTION_SNAPSHOT_FIELDS = (
    "subscription_number",
    "status",
    "quantity",
    "billing_frequency",
    "currency",
    "pricing_model",
    "unit_price",
    "subtotal",
    "discount_amount",
    "tax_amount",
    "total_amount",
    "start_date",
    "trial_start",
    "trial_end",
    "current_period_start",
    "current_period_end",
    "next_billing_date",
    "auto_renewal",
    "cancel_at_period_end",
    "cancelled_at",
    "cancellation_reason",
    "paused_at",
    "ended_at",
    "notes",
)
SUBSCRIPTION_SORT_FIELDS = (
    "created_at",
    "start_date",
    "next_billing_date",
    "status",
    "subscription_number",
    "updated_at",
    "total_amount",
)


# --- period arithmetic ----------------------------------------------------------------------------


def add_months(value: date, months: int, anchor_day: Optional[int] = None) -> date:
    """Calendar-safe month addition: the day is clamped to the target month's length.

    `anchor_day` keeps a billing anchor (e.g. the 31st) alive across short months so
    Jan 31 -> Feb 28 -> Mar 31 instead of drifting to the 28th forever.
    """
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor_day or value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def interval_months(plan: Plan) -> int:
    months = INTERVAL_MONTHS.get(plan.billing_interval)
    if not months:
        raise ValidationAppError(
            "One-time plans cannot be used for subscriptions.", {"fields": {"plan_id": "one_time plan"}}
        )
    return months * max(1, int(plan.interval_count or 1))


def period_end_for(start: date, plan: Plan, anchor_day: Optional[int] = None) -> date:
    return add_months(start, interval_months(plan), anchor_day)


def compute_mrr(plan: Plan, quantity: int, unit_price_override: Optional[Decimal] = None) -> Decimal:
    months = INTERVAL_MONTHS.get(plan.billing_interval)
    if not months:
        return Decimal("0.00")
    months *= max(1, int(plan.interval_count or 1))
    units = D(quantity) if plan.pricing_model == PricingModel.PER_UNIT else Decimal("1")
    price = D(unit_price_override) if unit_price_override is not None else D(plan.unit_amount)
    return q2(price * units / Decimal(months))


def anchor_day(subscription: Subscription) -> int:
    return (subscription.trial_end or subscription.start_date).day


# --- serialisation ----------------------------------------------------------------------------------------


def snapshot(subscription: Subscription) -> Dict[str, Any]:
    return audit.snapshot(subscription, SUBSCRIPTION_SNAPSHOT_FIELDS)


def serialize_subscription(subscription: Subscription) -> Dict[str, Any]:
    plan = subscription.plan
    qty = int(subscription.quantity or 1)
    unit_price = D(subscription.unit_price if subscription.unit_price is not None else plan.unit_amount)
    subtotal = D(
        subscription.subtotal
        if subscription.subtotal is not None
        else (unit_price * qty if plan.pricing_model == PricingModel.PER_UNIT else unit_price)
    )
    discount = D(subscription.discount_amount or 0)
    tax = D(subscription.tax_amount or 0)
    total = D(subscription.total_amount if subscription.total_amount is not None else (subtotal - discount + tax))

    billing_freq = subscription.billing_frequency or (
        plan.billing_interval.value if hasattr(plan.billing_interval, "value") else str(plan.billing_interval)
    )
    pricing_model_val = subscription.pricing_model or (
        plan.pricing_model.value if hasattr(plan.pricing_model, "value") else str(plan.pricing_model)
    )

    return {
        "id": subscription.id,
        "subscription_number": subscription.subscription_number,
        "customer": customer_ref(subscription.customer),
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "code": plan.code,
            "billing_interval": plan.billing_interval,
            "interval_count": int(plan.interval_count or 1),
            "unit_amount": money_str(plan.unit_amount),
            "currency": plan.currency,
            "product_name": plan.product.name if plan.product else "",
            "pricing_model": pricing_model_val,
        },
        "quantity": qty,
        "status": subscription.status,
        "billing_frequency": billing_freq,
        "currency": subscription.currency or plan.currency,
        "pricing_model": pricing_model_val,
        "unit_price": money_str(unit_price),
        "subtotal": money_str(subtotal),
        "discount_amount": money_str(discount),
        "tax_amount": money_str(tax),
        "total_amount": money_str(total),
        "start_date": subscription.start_date,
        "trial_start": subscription.trial_start,
        "trial_end": subscription.trial_end,
        "current_period_start": subscription.current_period_start,
        "current_period_end": subscription.current_period_end,
        "next_billing_date": subscription.next_billing_date,
        "auto_renewal": bool(subscription.auto_renewal if subscription.auto_renewal is not None else True),
        "cancel_at_period_end": bool(subscription.cancel_at_period_end),
        "cancelled_at": iso_dt(subscription.cancelled_at),
        "cancellation_reason": subscription.cancellation_reason,
        "paused_at": iso_dt(subscription.paused_at),
        "ended_at": iso_dt(subscription.ended_at),
        "notes": subscription.notes,
        "mrr": money_str(compute_mrr(plan, qty, unit_price)),
        "created_at": iso_dt(subscription.created_at),
        "updated_at": iso_dt(subscription.updated_at),
    }


# --- queries -----------------------------------------------------------------------------------------------------


def _base_query() -> Select:
    return select(Subscription).options(
        selectinload(Subscription.customer),
        selectinload(Subscription.plan).selectinload(Plan.product),
    )


def get_subscription(db: Session, organization_id: str, subscription_id: str) -> Subscription:
    subscription = db.scalars(
        _base_query().where(Subscription.id == subscription_id, Subscription.organization_id == organization_id)
    ).first()
    if subscription is None:
        raise EntityNotFoundError("Subscription", subscription_id)
    return subscription


def get_plan(db: Session, organization_id: str, plan_id: str) -> Plan:
    plan = db.scalars(
        select(Plan).options(selectinload(Plan.product)).where(Plan.id == plan_id, Plan.organization_id == organization_id)
    ).first()
    if plan is None:
        raise EntityNotFoundError("Plan", plan_id)
    return plan


def list_subscriptions(
    db: Session,
    organization_id: str,
    params: PageParams,
    *,
    search: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    billing_frequency: Optional[str] = None,
):
    stmt = _base_query().where(Subscription.organization_id == organization_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = (
            stmt.outerjoin(Customer, Customer.id == Subscription.customer_id)
            .outerjoin(Plan, Plan.id == Subscription.plan_id)
            .where(or_(Subscription.subscription_number.ilike(like), Customer.display_name.ilike(like), Plan.name.ilike(like)))
        )
    if status:
        try:
            stmt = stmt.where(Subscription.status == SubscriptionStatus(status))
        except ValueError:
            raise ValidationAppError("Unknown subscription status.", {"fields": {"status": "invalid"}})
    if customer_id:
        stmt = stmt.where(Subscription.customer_id == customer_id)
    if plan_id:
        stmt = stmt.where(Subscription.plan_id == plan_id)
    if billing_frequency:
        stmt = stmt.where(Subscription.billing_frequency == billing_frequency)
    stmt = apply_sort(stmt, Subscription, params.sort, SUBSCRIPTION_SORT_FIELDS, "-created_at")
    return paginate(db, stmt, params)


def get_subscriptions_summary(db: Session, organization_id: str) -> Dict[str, Any]:
    """Computes real database aggregation for subscription KPIs."""
    today = date.today()
    seven_days = today + timedelta(days=7)

    subs = db.scalars(
        select(Subscription).options(selectinload(Subscription.plan)).where(Subscription.organization_id == organization_id)
    ).all()

    total_count = len(subs)
    active_count = 0
    trialing_count = 0
    paused_count = 0
    renewing_soon_count = 0
    cancelled_count = 0
    total_mrr = Decimal("0.00")

    for s in subs:
        if s.status == SubscriptionStatus.ACTIVE:
            active_count += 1
            if s.plan:
                unit_price = D(s.unit_price if s.unit_price is not None else s.plan.unit_amount)
                total_mrr += compute_mrr(s.plan, s.quantity or 1, unit_price)
            if s.next_billing_date and today <= s.next_billing_date <= seven_days:
                renewing_soon_count += 1
        elif s.status == SubscriptionStatus.TRIALING:
            trialing_count += 1
        elif s.status == SubscriptionStatus.PAUSED:
            paused_count += 1
        elif s.status == SubscriptionStatus.CANCELLED:
            cancelled_count += 1

    return {
        "total_subscriptions": total_count,
        "active_count": active_count,
        "trialing_count": trialing_count,
        "paused_count": paused_count,
        "renewing_soon_count": renewing_soon_count,
        "cancelled_count": cancelled_count,
        "total_mrr": money_str(q2(total_mrr)),
    }


# --- renewal invoices ------------------------------------------------------------------------------------------------


def period_invoice_exists(db: Session, subscription: Subscription) -> bool:
    count = db.scalar(
        select(func.count()).select_from(Invoice).where(
            Invoice.subscription_id == subscription.id,
            Invoice.period_start == subscription.current_period_start,
            Invoice.status != InvoiceStatus.VOID,
        )
    )
    return bool(count)


def generate_period_invoice(
    db: Session,
    subscription: Subscription,
    *,
    ctx: Optional[CurrentContext] = None,
    actor_label: Optional[str] = None,
    include_setup_fee: bool = False,
    send: bool = True,
) -> Invoice:
    """Issue (status sent) the invoice for the subscription's current period. Idempotent per period. No commit."""
    if subscription.status in (SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED, SubscriptionStatus.DRAFT):
        raise InvalidStateError(f"A {subscription.status.value} subscription cannot be invoiced.")
    if period_invoice_exists(db, subscription):
        raise InvalidStateError(
            f"An invoice for the period starting {subscription.current_period_start.isoformat()} already exists."
        )
    plan = subscription.plan
    product = plan.product if plan else None
    customer = subscription.customer
    quantity = Decimal(int(subscription.quantity or 1)) if plan.pricing_model == PricingModel.PER_UNIT else Decimal("1")
    unit_price = D(subscription.unit_price if subscription.unit_price is not None else plan.unit_amount)

    tax_rate = D(product.tax_rate_pct if product is not None else 0)
    if customer.tax_exempt:
        tax_rate = Decimal("0")

    lines = [
        LineInput(
            description=f"{plan.name} ({subscription.current_period_start.isoformat()} – {subscription.current_period_end.isoformat()})",
            quantity=quantity,
            unit_price=unit_price,
            tax_rate_pct=tax_rate,
            product_id=plan.product_id,
            plan_id=plan.id,
        )
    ]
    if include_setup_fee and D(plan.setup_fee) > 0:
        lines.append(
            LineInput(
                description=f"{plan.name} setup fee",
                quantity=Decimal("1"),
                unit_price=D(plan.setup_fee),
                tax_rate_pct=tax_rate,
                product_id=plan.product_id,
                plan_id=plan.id,
            )
        )
    invoice = create_invoice_record(
        db,
        organization_id=subscription.organization_id,
        customer=customer,
        lines=lines,
        issue_date=date.today(),
        currency=subscription.currency or plan.currency or customer.currency,
        subscription_id=subscription.id,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        created_by_id=ctx.user.id if ctx else subscription.created_by_id,
        status=InvoiceStatus.SENT,
    )
    audit.record(
        db,
        action="INVOICE_CREATED",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        organization_id=subscription.organization_id,
        ctx=ctx,
        actor_label=actor_label,
        after={**invoice_snapshot(invoice), "subscription_id": subscription.id},
    )
    if send:
        email_invoice(db, invoice)
    audit.record(
        db,
        action="INVOICE_SENT",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        organization_id=subscription.organization_id,
        ctx=ctx,
        actor_label=actor_label,
        after=invoice_snapshot(invoice),
    )
    return invoice


def generate_invoice(db: Session, ctx: CurrentContext, subscription: Subscription) -> Invoice:
    """POST /subscriptions/{id}/generate-invoice."""
    invoice = generate_period_invoice(db, subscription, ctx=ctx)
    db.commit()
    return get_invoice(db, ctx.organization_id, invoice.id)


# --- lifecycle ----------------------------------------------------------------------------------------------------------


def create_subscription(db: Session, ctx: CurrentContext, data: SubscriptionCreate) -> Subscription:
    customer = get_customer(db, ctx.organization_id, data.customer_id)
    plan = get_plan(db, ctx.organization_id, data.plan_id)
    if not plan.is_active:
        raise ValidationAppError("This plan is inactive.", {"fields": {"plan_id": "inactive plan"}})
    months = interval_months(plan)  # 422 for one_time plans
    start = data.start_date or date.today()
    trial_days = data.trial_days if data.trial_days is not None else int(plan.trial_days or 0)
    qty = max(1, int(data.quantity or 1))

    # Calculate commercial pricing snapshot using Decimal precision
    unit_price = D(plan.unit_amount)
    product = plan.product
    tax_rate = D(product.tax_rate_pct if product else 0)
    if customer.tax_exempt:
        tax_rate = Decimal("0")

    units = Decimal(qty) if plan.pricing_model == PricingModel.PER_UNIT else Decimal("1")
    subtotal = q2(unit_price * units)
    discount_amount = Decimal("0.00")
    tax_amount = q2(subtotal * tax_rate / Decimal("100"))
    total_amount = q2(subtotal - discount_amount + tax_amount)

    billing_freq = data.billing_frequency or (
        plan.billing_interval.value if hasattr(plan.billing_interval, "value") else str(plan.billing_interval)
    )
    pricing_model_val = plan.pricing_model.value if hasattr(plan.pricing_model, "value") else str(plan.pricing_model)

    if data.status == SubscriptionStatus.DRAFT:
        status = SubscriptionStatus.DRAFT
        trial_start = None
        trial_end = None
        period_start = start
        next_billing = None
    elif trial_days > 0:
        trial_start = start
        trial_end = start + timedelta(days=trial_days)
        status = SubscriptionStatus.TRIALING
        period_start = trial_end
        next_billing = trial_end
    else:
        trial_start = None
        trial_end = None
        status = data.status or SubscriptionStatus.ACTIVE
        period_start = start
        next_billing = None

    period_end = add_months(period_start, months, period_start.day)
    if status == SubscriptionStatus.ACTIVE and next_billing is None:
        next_billing = period_end

    subscription = Subscription(
        organization_id=ctx.organization_id,
        subscription_number=next_number(db, ctx.organization_id, "subscription"),
        customer_id=customer.id,
        plan_id=plan.id,
        quantity=qty,
        status=status,
        billing_frequency=billing_freq,
        currency=plan.currency or customer.currency,
        pricing_model=pricing_model_val,
        unit_price=unit_price,
        subtotal=subtotal,
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        total_amount=total_amount,
        start_date=start,
        trial_start=trial_start,
        trial_end=trial_end,
        current_period_start=period_start,
        current_period_end=period_end,
        next_billing_date=next_billing,
        auto_renewal=bool(data.auto_renewal),
        cancel_at_period_end=False,
        notes=data.notes,
        created_by_id=ctx.user.id,
    )
    db.add(subscription)
    db.flush()
    audit.record(
        db,
        action="SUBSCRIPTION_CREATED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        ctx=ctx,
        after={**snapshot(subscription), "plan_id": plan.id, "customer_id": customer.id},
    )

    generate_first = data.generate_first_invoice if data.generate_first_invoice is not None else (status == SubscriptionStatus.ACTIVE)
    if generate_first and status == SubscriptionStatus.ACTIVE:
        db.refresh(subscription)
        generate_period_invoice(db, subscription, ctx=ctx, include_setup_fee=True)
    db.commit()
    return get_subscription(db, ctx.organization_id, subscription.id)


def activate_subscription(db: Session, ctx: CurrentContext, subscription: Subscription) -> Subscription:
    """Transition DRAFT or PENDING_ACTIVATION subscription to ACTIVE."""
    if subscription.status not in (SubscriptionStatus.DRAFT, SubscriptionStatus.PENDING_ACTIVATION):
        raise InvalidStateError(f"Only draft or pending subscriptions can be activated; this one is {subscription.status.value}.")
    before = snapshot(subscription)
    today = date.today()
    months = interval_months(subscription.plan)
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.current_period_start = today
    subscription.current_period_end = add_months(today, months, today.day)
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()
    subscription.updated_by_id = ctx.user.id
    db.flush()

    audit.record(
        db,
        action="SUBSCRIPTION_ACTIVATED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        ctx=ctx,
        before=before,
        after=snapshot(subscription),
    )
    db.commit()
    return get_subscription(db, ctx.organization_id, subscription.id)


def update_subscription(db: Session, ctx: CurrentContext, subscription: Subscription, data: SubscriptionUpdate) -> Subscription:
    if subscription.status in (SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED):
        raise InvalidStateError(f"A {subscription.status.value} subscription cannot be edited.")
    before = snapshot(subscription)
    changes = data.model_dump(exclude_unset=True)
    plan = subscription.plan

    if "quantity" in changes and changes["quantity"] is not None:
        qty = int(changes["quantity"])
        subscription.quantity = qty
        # Update snapshot amounts
        units = Decimal(qty) if plan.pricing_model == PricingModel.PER_UNIT else Decimal("1")
        subtotal = q2(D(subscription.unit_price or plan.unit_amount) * units)
        tax_rate = D(plan.product.tax_rate_pct if plan.product and not subscription.customer.tax_exempt else 0)
        tax = q2(subtotal * tax_rate / Decimal("100"))
        subscription.subtotal = subtotal
        subscription.tax_amount = tax
        subscription.total_amount = q2(subtotal - D(subscription.discount_amount or 0) + tax)

    if "notes" in changes:
        subscription.notes = changes["notes"]
    if "auto_renewal" in changes and changes["auto_renewal"] is not None:
        subscription.auto_renewal = bool(changes["auto_renewal"])
    if "cancel_at_period_end" in changes and changes["cancel_at_period_end"] is not None:
        subscription.cancel_at_period_end = bool(changes["cancel_at_period_end"])
    if "billing_frequency" in changes and changes["billing_frequency"]:
        subscription.billing_frequency = changes["billing_frequency"]

    subscription.updated_at = utcnow()
    subscription.updated_by_id = ctx.user.id
    db.flush()
    audit.record(
        db,
        action="SUBSCRIPTION_UPDATED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        ctx=ctx,
        before=before,
        after=snapshot(subscription),
    )
    db.commit()
    return get_subscription(db, ctx.organization_id, subscription.id)


def pause_subscription(db: Session, ctx: CurrentContext, subscription: Subscription) -> Subscription:
    if subscription.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE):
        raise InvalidStateError(f"Only active, trialing or past-due subscriptions can be paused; this one is {subscription.status.value}.")
    before = snapshot(subscription)
    subscription.status = SubscriptionStatus.PAUSED
    subscription.paused_at = utcnow()
    subscription.next_billing_date = None
    subscription.updated_at = utcnow()
    subscription.updated_by_id = ctx.user.id
    db.flush()
    audit.record(
        db,
        action="SUBSCRIPTION_PAUSED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        ctx=ctx,
        before=before,
        after=snapshot(subscription),
    )
    db.commit()
    return get_subscription(db, ctx.organization_id, subscription.id)


def resume_subscription(db: Session, ctx: CurrentContext, subscription: Subscription) -> Subscription:
    if subscription.status != SubscriptionStatus.PAUSED:
        raise InvalidStateError(f"Only paused subscriptions can be resumed; this one is {subscription.status.value}.")
    before = snapshot(subscription)
    today = date.today()
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.paused_at = None
    subscription.current_period_start = today
    subscription.current_period_end = period_end_for(today, subscription.plan, today.day)
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()
    subscription.updated_by_id = ctx.user.id
    db.flush()
    audit.record(
        db,
        action="SUBSCRIPTION_RESUMED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        ctx=ctx,
        before=before,
        after=snapshot(subscription),
    )
    db.commit()
    return get_subscription(db, ctx.organization_id, subscription.id)


def _end_now(subscription: Subscription, reason: Optional[str] = None) -> None:
    now = utcnow()
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = subscription.cancelled_at or now
    subscription.cancellation_reason = reason
    subscription.ended_at = now
    subscription.next_billing_date = None
    subscription.cancel_at_period_end = False
    subscription.updated_at = now


def cancel_subscription(
    db: Session, ctx: CurrentContext, subscription: Subscription, *, at_period_end: bool, reason: Optional[str]
) -> Subscription:
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise InvalidStateError("This subscription is already cancelled.")
    before = snapshot(subscription)
    if at_period_end and subscription.status != SubscriptionStatus.PAUSED:
        subscription.cancel_at_period_end = True
        subscription.cancelled_at = utcnow()
        subscription.cancellation_reason = reason
        subscription.updated_at = utcnow()
        subscription.updated_by_id = ctx.user.id
    else:
        _end_now(subscription, reason=reason)
        subscription.updated_by_id = ctx.user.id
    db.flush()
    audit.record(
        db,
        action="SUBSCRIPTION_CANCELLED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        ctx=ctx,
        before=before,
        after={**snapshot(subscription), "reason": reason, "at_period_end": at_period_end},
    )
    db.commit()
    return get_subscription(db, ctx.organization_id, subscription.id)


# --- scheduler primitives (no commit) -----------------------------------------------------------------------------------


def convert_trial(db: Session, subscription: Subscription, *, actor_label: str = audit.SYSTEM_ACTOR) -> Optional[Invoice]:
    """Scheduler: trialing -> active at trial end, first period starts, renewal invoice issued."""
    if subscription.status != SubscriptionStatus.TRIALING:
        return None
    before = snapshot(subscription)
    period_start = subscription.trial_end or date.today()
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.current_period_start = period_start
    subscription.current_period_end = period_end_for(period_start, subscription.plan, period_start.day)
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()
    db.flush()
    invoice = None
    if not period_invoice_exists(db, subscription):
        invoice = generate_period_invoice(db, subscription, actor_label=actor_label, include_setup_fee=True)
    audit.record(
        db,
        action="TRIAL_CONVERTED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        organization_id=subscription.organization_id,
        actor_label=actor_label,
        before=before,
        after={**snapshot(subscription), "invoice_id": invoice.id if invoice else None},
    )
    return invoice


def renew_subscription(db: Session, subscription: Subscription, *, actor_label: str = audit.SYSTEM_ACTOR) -> str:
    """Advance the period and issue the renewal invoice, or end it when cancel_at_period_end."""
    if subscription.status != SubscriptionStatus.ACTIVE:
        return "skipped"
    before = snapshot(subscription)
    if subscription.cancel_at_period_end:
        _end_now(subscription, reason="cancel_at_period_end reached")
        db.flush()
        audit.record(
            db,
            action="SUBSCRIPTION_CANCELLED",
            entity_type="subscription",
            entity_id=subscription.id,
            entity_label=subscription.subscription_number,
            organization_id=subscription.organization_id,
            actor_label=actor_label,
            before=before,
            after={**snapshot(subscription), "reason": "cancel_at_period_end reached"},
        )
        return "ended"
    new_start = subscription.current_period_end
    subscription.current_period_start = new_start
    subscription.current_period_end = period_end_for(new_start, subscription.plan, anchor_day(subscription))
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()
    db.flush()
    invoice = None
    if not period_invoice_exists(db, subscription):
        invoice = generate_period_invoice(db, subscription, actor_label=actor_label)
    audit.record(
        db,
        action="SUBSCRIPTION_RENEWED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        organization_id=subscription.organization_id,
        actor_label=actor_label,
        before=before,
        after={**snapshot(subscription), "invoice_id": invoice.id if invoice else None},
    )
    return "renewed"


__all__ = [
    "add_months",
    "interval_months",
    "compute_mrr",
    "serialize_subscription",
    "get_subscription",
    "list_subscriptions",
    "get_subscriptions_summary",
    "create_subscription",
    "activate_subscription",
    "update_subscription",
    "pause_subscription",
    "resume_subscription",
    "cancel_subscription",
    "generate_invoice",
    "generate_period_invoice",
    "convert_trial",
    "renew_subscription",
]

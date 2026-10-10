"""Subscriptions: period arithmetic, lifecycle and renewal invoices (contract §7)."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import Select, func, or_, select, update
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
from backend.app.models.billing_cycles import (
    BillingCycle,
    BillingCycleStatus,
    PriceSnapshot,
    SubscriptionItem,
    SubscriptionItemStatus,
    SubscriptionItemType,
)
from backend.app.models.events import DomainEventType, OutboxEvent, OutboxStatus
from backend.app.schemas.common_refs import customer_ref, iso_dt, money_str
from backend.app.schemas.subscriptions import SubscriptionCreate, SubscriptionUpdate
from backend.app.services import audit, timezones
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


def effective_unit_price(subscription: Subscription, plan: Plan) -> Decimal:
    """The price to bill a subscription at, falling back to the plan's list price.

    `Subscription.unit_price` is NOT NULL with a default of 0, so an unset
    override reads as 0, not None, on any row created without an explicit price
    (trial conversion and other internal paths create rows exactly that way).
    Testing only for None therefore billed those subscriptions at zero.
    """
    override = D(subscription.unit_price) if subscription.unit_price is not None else Decimal("0")
    return override if override > 0 else D(plan.unit_amount)


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


def plan_tax_rate(plan: Optional[Plan], customer: Optional[Customer] = None) -> Decimal:
    """The tax rate a plan's lines are billed at for this customer (0 when tax exempt)."""
    if customer is not None and customer.tax_exempt:
        return Decimal("0")
    product = plan.product if plan is not None else None
    return D(product.tax_rate_pct if product is not None else 0)


def primary_plan_item(db: Session, subscription: Subscription) -> Optional[SubscriptionItem]:
    return db.scalars(
        select(SubscriptionItem).where(
            SubscriptionItem.subscription_id == subscription.id,
            SubscriptionItem.item_type == SubscriptionItemType.PLAN,
            SubscriptionItem.status == SubscriptionItemStatus.ACTIVE,
        )
    ).first()


def contracted_unit_price(db: Session, subscription: Subscription, plan: Optional[Plan] = None) -> Decimal:
    """The per-unit price the subscription is actually billed at on renewal.

    Mirrors generate_period_invoice: the primary item's price snapshot, then the item's
    own unit_price, then the subscription override / plan list price.
    """
    plan = plan or subscription.plan
    item = primary_plan_item(db, subscription)
    if item is not None:
        if item.price_snapshot is not None:
            return D(item.price_snapshot.unit_amount)
        if item.unit_price is not None and D(item.unit_price) > 0:
            return D(item.unit_price)
    return effective_unit_price(subscription, plan)


def terms_for_quantity(
    db: Session, subscription: Subscription, plan: Plan, quantity, *, same_plan: bool
) -> tuple[Decimal, Optional[Dict[str, Any]]]:
    """(snapshot unit amount, snapshot metadata) for moving `subscription` to `plan` x `quantity`.

    Legacy plans keep the existing rules: the contracted price for a same-plan change, the
    target plan's list price otherwise (no metadata). Offering-linked plans are priced by
    the pricing engine, except a same-plan seat change on a per-unit offering, which keeps
    the contracted per-unit price (as legacy per-unit plans do).
    """
    item = primary_plan_item(db, subscription)
    if not plan.offering_id:
        return (contracted_unit_price(db, subscription, plan) if same_plan else D(plan.unit_amount)), None
    from backend.app.services import offering_subscription_service as offering_svc

    if same_plan and plan.pricing_model == PricingModel.PER_UNIT:
        meta = offering_svc.snapshot_metadata(item)
        if meta:
            meta["quantity"] = int(D(quantity))
        return contracted_unit_price(db, subscription, plan), (meta or None)
    return offering_svc.price_for_plan(db, plan, int(D(quantity)), current_item=item)


def billable_units(plan: Plan, quantity) -> Decimal:
    """FLAT plans bill a single unit per period regardless of the seat count."""
    return D(quantity) if plan.pricing_model == PricingModel.PER_UNIT else Decimal("1")


def apply_plan_terms(
    db: Session,
    subscription: Subscription,
    plan: Plan,
    quantity: int,
    *,
    unit_price: Optional[Decimal] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SubscriptionItem:
    """Point the subscription (and its primary PLAN item) at `plan`/`quantity` with a fresh
    immutable PriceSnapshot, and recompute the commercial totals. No commit.

    Every path that changes plan or quantity must go through here - mutating only
    `subscription.plan_id`/`quantity` leaves the item/snapshot on the old terms, and
    generate_period_invoice bills from the item, so renewals kept billing the old plan.

    `metadata` (offering-linked plans) records how the price was derived - offering,
    pricing model, price book, negotiated discount - so later changes can re-price.
    """
    price = D(unit_price) if unit_price is not None else D(plan.unit_amount)
    snap = PriceSnapshot(
        organization_id=subscription.organization_id,
        plan_id=plan.id,
        unit_amount=price,
        currency=plan.currency,
        billing_interval=plan.billing_interval,
        interval_count=int(plan.interval_count or 1),
        pricing_model=plan.pricing_model,
        tax_rate_pct=plan_tax_rate(plan),
        setup_fee=D(plan.setup_fee or 0),
        trial_days=int(plan.trial_days or 0),
        snapshot_at=utcnow(),
        metadata_=metadata or None,
    )
    db.add(snap)
    db.flush()

    item = primary_plan_item(db, subscription)
    if item is not None:
        item.plan_id = plan.id
        item.price_snapshot_id = snap.id
        item.price_snapshot = snap
        item.unit_price = price
        item.quantity = Decimal(int(quantity))
    else:
        item = SubscriptionItem(
            organization_id=subscription.organization_id,
            subscription_id=subscription.id,
            plan_id=plan.id,
            price_snapshot_id=snap.id,
            item_type=SubscriptionItemType.PLAN,
            quantity=Decimal(int(quantity)),
            unit_price=price,
            status=SubscriptionItemStatus.ACTIVE,
        )
        db.add(item)

    subscription.plan_id = plan.id
    subscription.plan = plan
    subscription.quantity = int(quantity)
    subscription.unit_price = price
    subscription.pricing_model = plan.pricing_model.value if hasattr(plan.pricing_model, "value") else str(plan.pricing_model)
    subscription.billing_frequency = (
        plan.billing_interval.value if hasattr(plan.billing_interval, "value") else str(plan.billing_interval)
    )
    subtotal = q2(price * billable_units(plan, quantity))
    tax = q2(subtotal * plan_tax_rate(plan, subscription.customer) / Decimal("100"))
    # Add-on items (e.g. extra recurring lines of a converted quote) keep billing on
    # their own snapshots; keep them in the displayed commercial totals.
    for addon in db.scalars(
        select(SubscriptionItem).where(
            SubscriptionItem.subscription_id == subscription.id,
            SubscriptionItem.item_type == SubscriptionItemType.ADDON,
            SubscriptionItem.status == SubscriptionItemStatus.ACTIVE,
        )
    ):
        addon_snap = addon.price_snapshot
        addon_plan = addon.plan
        units = billable_units(addon_plan, addon.quantity) if addon_plan is not None else Decimal("1")
        addon_subtotal = q2(D(addon_snap.unit_amount if addon_snap else addon.unit_price) * units)
        addon_rate = (
            Decimal("0")
            if subscription.customer is not None and subscription.customer.tax_exempt
            else D(addon_snap.tax_rate_pct if addon_snap else plan_tax_rate(addon_plan))
        )
        subtotal += addon_subtotal
        tax += q2(addon_subtotal * addon_rate / Decimal("100"))
    subscription.subtotal = subtotal
    subscription.tax_amount = tax
    subscription.total_amount = q2(subtotal - D(subscription.discount_amount or 0) + tax)
    subscription.updated_at = utcnow()
    db.flush()
    # Drop any stale in-memory item collection so the next invoice sees the new terms.
    db.expire(subscription, ["subscription_items"])
    return item


def lock_subscription_row(db: Session, subscription_id: str) -> None:
    """SELECT ... FOR UPDATE on the subscription row (no-op on SQLite) so concurrent
    renewal / invoice-generation runs serialise instead of double-invoicing a period."""
    db.execute(select(Subscription.id).where(Subscription.id == subscription_id).with_for_update())


def lock_customer_row(db: Session, organization_id: str, customer_id: str) -> None:
    """SELECT ... FOR UPDATE on the customer (skipped on SQLite) so concurrent create /
    activate / resume requests for the same customer serialise before the conflict check."""
    if db.bind is None or db.bind.dialect.name == "sqlite":
        return
    db.execute(
        select(Customer.id)
        .where(Customer.id == customer_id, Customer.organization_id == organization_id)
        .with_for_update()
    )


_SLOT_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAUSED)


def assert_no_conflicting_subscription(
    db: Session,
    organization_id: str,
    customer_id: str,
    plan_id: str,
    *,
    statuses=_SLOT_STATUSES,
    exclude_id: Optional[str] = None,
) -> None:
    """One live subscription per (organization, customer, plan): a paused subscription
    still occupies the slot. Raises ValidationAppError (422) when another one exists."""
    stmt = select(Subscription).where(
        Subscription.organization_id == organization_id,
        Subscription.customer_id == customer_id,
        Subscription.plan_id == plan_id,
        Subscription.status.in_(list(statuses)),
    )
    if exclude_id:
        stmt = stmt.where(Subscription.id != exclude_id)
    existing = db.scalars(stmt.order_by(Subscription.created_at)).first()
    if existing is None:
        return
    if existing.status == SubscriptionStatus.PAUSED:
        raise ValidationAppError(
            f"This customer already has a paused subscription ({existing.subscription_number}) to this plan. "
            "Resume or cancel it instead.",
            {"fields": {"plan_id": "A paused subscription for this customer and plan already exists."}},
        )
    raise ValidationAppError(
        f"Customer already has an active subscription ({existing.subscription_number}) for this plan.",
        {"fields": {"plan_id": "An active subscription for this customer and plan already exists."}},
    )


def lock_and_reload(db: Session, subscription: Subscription) -> Subscription:
    """Flush pending changes, then re-read the subscription row under SELECT ... FOR UPDATE
    so the in-memory object reflects what a concurrent (now committed) request did."""
    db.flush()
    return db.scalars(
        select(Subscription)
        .where(Subscription.id == subscription.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def claim_status_transition(db: Session, subscription: Subscription, from_statuses, to_status: SubscriptionStatus) -> bool:
    """Compare-and-set the status in one UPDATE: True only for the single request that
    actually performed the transition (callers audit only then)."""
    result = db.execute(
        update(Subscription)
        .where(Subscription.id == subscription.id, Subscription.status.in_(list(from_statuses)))
        .values(status=to_status, updated_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if (result.rowcount or 0) != 1:
        return False
    subscription.status = to_status
    return True


def _inactive_linked_offering_name(db: Session, plan: Optional[Plan]) -> Optional[str]:
    """Name of the catalog offering behind a linked plan when that offering is archived."""
    if plan is None or not plan.offering_id:
        return None
    from backend.app.services.offering_subscription_service import linked_offering

    offering = linked_offering(db, plan)
    if offering is None:
        return plan.name
    return None if offering.is_active else offering.name


# --- serialisation ----------------------------------------------------------------------------------------


def snapshot(subscription: Subscription) -> Dict[str, Any]:
    return audit.snapshot(subscription, SUBSCRIPTION_SNAPSHOT_FIELDS)


def _primary_snapshot_meta(subscription: Subscription) -> Dict[str, Any]:
    for item in subscription.subscription_items or []:
        if (
            item.item_type == SubscriptionItemType.PLAN
            and item.status == SubscriptionItemStatus.ACTIVE
            and item.price_snapshot is not None
            and isinstance(item.price_snapshot.metadata_, dict)
        ):
            return item.price_snapshot.metadata_
    return {}


def serialize_subscription(subscription: Subscription) -> Dict[str, Any]:
    plan = subscription.plan
    qty = int(subscription.quantity or 1)
    unit_price = effective_unit_price(subscription, plan)
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
            "source": "offering" if plan.offering_id else "plan",
            "offering_id": plan.offering_id,
            "offering_pricing_model": _primary_snapshot_meta(subscription).get("offering_pricing_model")
            if plan.offering_id
            else None,
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
        selectinload(Subscription.subscription_items).selectinload(SubscriptionItem.price_snapshot),
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
        # A comma-separated list filters on any of the statuses (e.g. the Draft tab lists
        # "draft,pending_activation", matching the summary's draft_count).
        try:
            wanted = [SubscriptionStatus(part.strip()) for part in status.split(",") if part.strip()]
        except ValueError:
            raise ValidationAppError("Unknown subscription status.", {"fields": {"status": "invalid"}})
        if not wanted:
            raise ValidationAppError("Unknown subscription status.", {"fields": {"status": "invalid"}})
        stmt = stmt.where(Subscription.status == wanted[0]) if len(wanted) == 1 else stmt.where(Subscription.status.in_(wanted))
    if customer_id:
        stmt = stmt.where(Subscription.customer_id == customer_id)
    if plan_id:
        stmt = stmt.where(Subscription.plan_id == plan_id)
    if billing_frequency:
        stmt = stmt.where(Subscription.billing_frequency == billing_frequency)
    stmt = apply_sort(stmt, Subscription, params.sort, SUBSCRIPTION_SORT_FIELDS, "-created_at")
    return paginate(db, stmt, params)


def get_subscriptions_summary(db: Session, organization_id: str) -> Dict[str, Any]:
    """Computes real database aggregation for subscription KPIs.

    Field meanings (the Subscriptions list / Trial Center / Revenue pages rely on them):

    - ``draft_count``: subscriptions not yet live - ``draft`` and ``pending_activation``
      (the list renders both as drafts and the Draft tab lists both).
    - ``past_due_count``: subscriptions whose renewal invoice is overdue.
    - ``total_arr``: the headline MRR annualised (MRR x 12).
    - ``renewing_soon_count``: active subscriptions billing again within 7 days.
    - ``expiring_soon_count``: live (active / past due) subscriptions whose current period
      ends within 7 days and that will NOT renew (auto-renewal off or cancel at period end).
    - ``trial_expiring_soon_count``: trialing subscriptions whose trial ends within 7 days.
    - ``auto_renew_enabled_count``: active subscriptions that will auto-renew
      (auto-renewal on and not set to cancel at period end).
    """
    today = timezones.org_today_for_id(db, organization_id)
    seven_days = today + timedelta(days=7)

    subs = db.scalars(
        select(Subscription).options(selectinload(Subscription.plan)).where(Subscription.organization_id == organization_id)
    ).all()

    total_count = len(subs)
    active_count = 0
    trialing_count = 0
    paused_count = 0
    past_due_count = 0
    renewing_soon_count = 0
    expiring_soon_count = 0
    trial_expiring_soon_count = 0
    auto_renew_enabled_count = 0
    cancelled_count = 0
    draft_count = 0
    total_mrr = Decimal("0.00")

    for s in subs:
        will_renew = bool(s.auto_renewal) and not bool(s.cancel_at_period_end)
        if s.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE):
            if not will_renew and s.current_period_end and today <= s.current_period_end <= seven_days:
                expiring_soon_count += 1
        if s.status == SubscriptionStatus.ACTIVE:
            active_count += 1
            if will_renew:
                auto_renew_enabled_count += 1
            if s.plan:
                unit_price = effective_unit_price(s, s.plan)
                total_mrr += compute_mrr(s.plan, s.quantity or 1, unit_price)
            if s.next_billing_date and today <= s.next_billing_date <= seven_days:
                renewing_soon_count += 1
        elif s.status == SubscriptionStatus.TRIALING:
            trialing_count += 1
            if s.trial_end and today <= s.trial_end <= seven_days:
                trial_expiring_soon_count += 1
        elif s.status == SubscriptionStatus.PAST_DUE:
            past_due_count += 1
        elif s.status == SubscriptionStatus.PAUSED:
            paused_count += 1
        elif s.status == SubscriptionStatus.CANCELLED:
            cancelled_count += 1
        elif s.status in (SubscriptionStatus.DRAFT, SubscriptionStatus.PENDING_ACTIVATION):
            draft_count += 1

    # Headline MRR comes from the single shared definition (dashboard/reports/AI agree).
    try:
        from backend.app.services.dashboard_service import compute_mrr as shared_compute_mrr

        total_mrr = D(shared_compute_mrr(db, organization_id)["mrr"])
    except Exception:  # pragma: no cover - fall back to the local sum above
        pass
    total_mrr = q2(total_mrr)

    return {
        "total_subscriptions": total_count,
        "active_count": active_count,
        "trialing_count": trialing_count,
        "paused_count": paused_count,
        "past_due_count": past_due_count,
        "renewing_soon_count": renewing_soon_count,
        "expiring_soon_count": expiring_soon_count,
        "trial_expiring_soon_count": trial_expiring_soon_count,
        "auto_renew_enabled_count": auto_renew_enabled_count,
        "cancelled_count": cancelled_count,
        "draft_count": draft_count,
        "total_mrr": money_str(total_mrr),
        "total_arr": money_str(q2(total_mrr * Decimal("12"))),
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
    # Serialise with any concurrent generator for this subscription before the
    # duplicate check, otherwise two runs can both see "no invoice" and both issue one.
    lock_subscription_row(db, subscription.id)
    if period_invoice_exists(db, subscription):
        raise InvalidStateError(
            f"An invoice for the period starting {subscription.current_period_start.isoformat()} already exists."
        )
    plan = subscription.plan
    product = plan.product if plan else None
    customer = subscription.customer

    # Resolved up-front: the setup-fee line below needs it on every branch (it used to be
    # assigned only in the no-items fallback, raising UnboundLocalError otherwise).
    tax_rate = plan_tax_rate(plan, customer)

    lines = []
    # If subscription has active subscription_items, generate lines from them.
    # METERED items are excluded: they're a bookkeeping row finalize_usage_for_cycle
    # upserts to remember the last-rated usage total, already billed on its own
    # separate usage invoice - including it here would double-bill it, and since it
    # has no plan/price_snapshot its quantity would also collapse to 1 (see
    # generate_period_invoice's fallback below), losing the real rated amount.
    active_items = [
        it
        for it in (subscription.subscription_items or [])
        if it.status == SubscriptionItemStatus.ACTIVE and it.item_type != SubscriptionItemType.METERED
    ]
    if active_items:
        for item in active_items:
            snap = item.price_snapshot
            item_plan = item.plan or plan
            item_prod = item_plan.product if item_plan else product
            snap_pricing_model = snap.pricing_model if snap else (item_plan.pricing_model if item_plan else PricingModel.FLAT)
            item_qty = Decimal(str(item.quantity)) if snap_pricing_model == PricingModel.PER_UNIT else Decimal("1")
            item_unit_amount = D(snap.unit_amount if snap else (item.unit_price or item_plan.unit_amount))
            item_tax = Decimal("0") if customer.tax_exempt else D(snap.tax_rate_pct if snap else (item_prod.tax_rate_pct if item_prod else 0))
            name = item_plan.name if item_plan else "Subscription Item"
            if item_plan is not None and item_plan.offering_id and item_qty == 1 and D(item.quantity) != 1:
                # Offering priced per period for the whole quantity (flat/volume/tiered/package).
                name = f"{name} x {int(D(item.quantity))}"
            desc = f"{name} ({subscription.current_period_start.isoformat()} – {subscription.current_period_end.isoformat()})"
            lines.append(
                LineInput(
                    description=desc,
                    quantity=item_qty,
                    unit_price=item_unit_amount,
                    tax_rate_pct=item_tax,
                    offering_id=item_plan.offering_id if item_plan else None,
                    product_id=item_plan.product_id if item_plan else None,
                    plan_id=item_plan.id if item_plan else None,
                )
            )
    else:
        quantity = Decimal(int(subscription.quantity or 1)) if plan.pricing_model == PricingModel.PER_UNIT else Decimal("1")
        unit_price = effective_unit_price(subscription, plan)
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
        issue_date=timezones.org_today_for_id(db, subscription.organization_id),
        currency=subscription.currency or plan.currency or customer.currency,
        subscription_id=subscription.id,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        created_by_id=ctx.user.id if ctx else subscription.created_by_id,
        status=InvoiceStatus.SENT,
    )

    # Link or record BillingCycle
    bc = db.scalars(
        select(BillingCycle).where(
            BillingCycle.subscription_id == subscription.id,
            BillingCycle.period_start == subscription.current_period_start,
        )
    ).first()
    if bc is None:
        max_cycle = db.scalar(
            select(func.max(BillingCycle.cycle_number)).where(
                BillingCycle.subscription_id == subscription.id
            )
        ) or 0
        bc = BillingCycle(
            organization_id=subscription.organization_id,
            subscription_id=subscription.id,
            cycle_number=max_cycle + 1,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            status=BillingCycleStatus.INVOICED,
            invoice_id=invoice.id,
            finalized_at=utcnow(),
        )
        db.add(bc)
    else:
        bc.invoice_id = invoice.id
        bc.status = BillingCycleStatus.INVOICED
        bc.finalized_at = utcnow()
    db.flush()
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


@dataclass
class ItemTerms:
    """Commercial terms of one subscription item, frozen into its PriceSnapshot."""

    plan: Plan
    quantity: int
    unit_amount: Decimal  # per unit (PER_UNIT plans) or per period (FLAT plans)
    tax_rate_pct: Decimal  # snapshot rate before any customer exemption
    metadata: Optional[Dict[str, Any]] = None
    item_type: SubscriptionItemType = SubscriptionItemType.PLAN

    @property
    def subtotal(self) -> Decimal:
        return q2(D(self.unit_amount) * billable_units(self.plan, self.quantity))


def legacy_item_terms(plan: Plan, quantity: int) -> ItemTerms:
    product = plan.product
    return ItemTerms(
        plan=plan,
        quantity=quantity,
        unit_amount=D(plan.unit_amount),
        tax_rate_pct=D(product.tax_rate_pct if product is not None else 0),
    )


def offering_item_terms(
    db: Session,
    organization_id: str,
    offering_id: str,
    quantity: int,
    *,
    price_book_id: Optional[str] = None,
    field_name: str = "offering_id",
) -> ItemTerms:
    """Terms for subscribing to a recurring Plans & Pricing offering (via its linked plan)."""
    from backend.app.services import offering_subscription_service as offering_svc

    offering = offering_svc.get_subscribable_offering(db, organization_id, offering_id, field_name=field_name)
    entry = offering_svc.resolve_price_book_entry(db, organization_id, offering, price_book_id)
    price = offering_svc.price_offering(offering, quantity, entry)
    plan = offering_svc.ensure_linked_plan(db, organization_id, offering)
    return ItemTerms(
        plan=plan,
        quantity=quantity,
        unit_amount=price.unit_amount,
        tax_rate_pct=price.tax_rate_pct,
        metadata=price.metadata,
    )


def _snapshot_for(organization_id: str, terms: ItemTerms, trial_days: int) -> PriceSnapshot:
    plan = terms.plan
    return PriceSnapshot(
        organization_id=organization_id,
        plan_id=plan.id,
        unit_amount=D(terms.unit_amount),
        currency=plan.currency,
        billing_interval=plan.billing_interval,
        interval_count=int(plan.interval_count or 1),
        pricing_model=plan.pricing_model,
        tax_rate_pct=D(terms.tax_rate_pct),
        setup_fee=D(plan.setup_fee or 0),
        trial_days=trial_days,
        snapshot_at=utcnow(),
        metadata_=terms.metadata or None,
    )


def create_subscription(db: Session, ctx: CurrentContext, data: SubscriptionCreate) -> Subscription:
    customer = get_customer(db, ctx.organization_id, data.customer_id)
    qty = max(1, int(data.quantity or 1))
    offering_id = data.offering_id
    plan: Optional[Plan] = None
    if not offering_id:
        plan = get_plan(db, ctx.organization_id, data.plan_id)
        if plan.offering_id:
            # A linked plan is always (re)priced through its catalog offering, so the
            # offering's active flag, price book and pricing model are honoured.
            offering_id = plan.offering_id
    if offering_id:
        terms = offering_item_terms(
            db,
            ctx.organization_id,
            offering_id,
            qty,
            price_book_id=data.price_book_id,
            field_name="offering_id" if data.offering_id else "plan_id",
        )
    else:
        if not plan.is_active:
            raise ValidationAppError("This plan is inactive.", {"fields": {"plan_id": "inactive plan"}})
        terms = legacy_item_terms(plan, qty)
    # The subscription is invoiced in the plan's currency. Billing a customer in a currency
    # other than their own billing currency must be an explicit choice, never silent.
    plan_currency = (terms.plan.currency or "INR").upper()
    customer_currency = (customer.currency or "INR").upper()
    currency_override = plan_currency != customer_currency
    if currency_override and not data.allow_currency_mismatch:
        raise ValidationAppError(
            f"This plan is priced in {plan_currency} but the customer is billed in {customer_currency}. "
            f"Choose a {customer_currency} plan, or confirm billing this customer in {plan_currency}.",
            {
                "reason": "CURRENCY_MISMATCH",
                "fields": {"offering_id" if data.offering_id else "plan_id": "currency mismatch"},
                "plan_currency": plan_currency,
                "customer_currency": customer_currency,
            },
        )
    subscription = build_subscription(
        db,
        ctx,
        customer=customer,
        items=[terms],
        start=data.start_date or timezones.org_today(ctx.organization),
        trial_days=data.trial_days,
        requested_status=data.status,
        auto_renewal=bool(data.auto_renewal),
        notes=data.notes,
        billing_frequency=data.billing_frequency,
        generate_first_invoice=data.generate_first_invoice,
        audit_extra={"currency_mismatch_override": f"{customer_currency}->{plan_currency}"} if currency_override else None,
    )
    db.commit()
    return get_subscription(db, ctx.organization_id, subscription.id)


def build_subscription(
    db: Session,
    ctx: CurrentContext,
    *,
    customer: Customer,
    items: List[ItemTerms],
    start: date,
    trial_days: Optional[int] = None,
    requested_status: Optional[SubscriptionStatus] = None,
    auto_renewal: bool = True,
    notes: Optional[str] = None,
    billing_frequency: Optional[str] = None,
    generate_first_invoice: Optional[bool] = None,
    currency: Optional[str] = None,
    audit_extra: Optional[Dict[str, Any]] = None,
) -> Subscription:
    """Create a subscription (items, snapshots, first billing cycle, trial, outbox, audit and -
    when it starts active - the first period invoice) from resolved item terms. No commit.

    ``items[0]`` is the primary PLAN item; further items are ADDONs billed on the same
    periods (they must share the primary plan's interval and currency).
    """
    if not items:
        raise ValidationAppError("At least one plan is required.", {"fields": {"plan_id": "required"}})
    primary = items[0]
    plan = primary.plan
    months = interval_months(plan)  # 422 for one_time plans
    for extra in items[1:]:
        if interval_months(extra.plan) != months or (extra.plan.currency or "").upper() != (plan.currency or "").upper():
            raise ValidationAppError(
                "All recurring lines must share the same billing interval and currency.",
                {"fields": {"items": "mixed billing terms"}},
            )
    trial_days = trial_days if trial_days is not None else int(plan.trial_days or 0)

    # A new subscription may only start as a draft, active, or (via trial_days) trialing.
    # Anything else (paused, cancelled, past_due, ...) would skip the lifecycle invariants.
    if requested_status is not None and requested_status not in (
        SubscriptionStatus.DRAFT,
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.TRIALING,
    ):
        raise ValidationAppError(
            "A new subscription can only be created as draft or active.",
            {"fields": {"status": "must be draft or active"}},
        )
    if requested_status == SubscriptionStatus.TRIALING and trial_days <= 0:
        raise ValidationAppError(
            "A trialing subscription requires trial_days greater than 0.",
            {"fields": {"trial_days": "required for trialing"}},
        )
    qty = max(1, int(primary.quantity or 1))

    # Commercial totals (Decimal precision); tax exempt customers carry no tax.
    unit_price = D(primary.unit_amount)
    subtotal = Decimal("0.00")
    tax_amount = Decimal("0.00")
    for terms in items:
        line_subtotal = terms.subtotal
        subtotal += line_subtotal
        rate = Decimal("0") if customer.tax_exempt else D(terms.tax_rate_pct)
        tax_amount += q2(line_subtotal * rate / Decimal("100"))
    subtotal = q2(subtotal)
    tax_amount = q2(tax_amount)
    discount_amount = Decimal("0.00")
    total_amount = q2(subtotal - discount_amount + tax_amount)

    billing_freq = billing_frequency or (
        plan.billing_interval.value if hasattr(plan.billing_interval, "value") else str(plan.billing_interval)
    )
    pricing_model_val = plan.pricing_model.value if hasattr(plan.pricing_model, "value") else str(plan.pricing_model)
    status_req = requested_status

    if status_req == SubscriptionStatus.DRAFT:
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
        status = SubscriptionStatus.ACTIVE
        period_start = start
        next_billing = None

    period_end = add_months(period_start, months, period_start.day)
    if status == SubscriptionStatus.ACTIVE and next_billing is None:
        next_billing = period_end

    if status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        lock_customer_row(db, ctx.organization_id, customer.id)
        assert_no_conflicting_subscription(db, ctx.organization_id, customer.id, plan.id)

    subscription = Subscription(
        organization_id=ctx.organization_id,
        subscription_number=next_number(db, ctx.organization_id, "subscription"),
        customer_id=customer.id,
        plan_id=plan.id,
        quantity=qty,
        status=status,
        billing_frequency=billing_freq,
        currency=currency or plan.currency or customer.currency,
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
        auto_renewal=bool(auto_renewal),
        cancel_at_period_end=False,
        notes=notes,
        created_by_id=ctx.user.id,
    )
    db.add(subscription)
    db.flush()

    # One immutable PriceSnapshot + SubscriptionItem per item (the first is the PLAN item).
    for index, terms in enumerate(items):
        snap = _snapshot_for(ctx.organization_id, terms, trial_days)
        db.add(snap)
        db.flush()
        db.add(
            SubscriptionItem(
                organization_id=ctx.organization_id,
                subscription_id=subscription.id,
                plan_id=terms.plan.id,
                price_snapshot_id=snap.id,
                item_type=SubscriptionItemType.PLAN if index == 0 else SubscriptionItemType.ADDON,
                quantity=Decimal(int(terms.quantity or 1)),
                unit_price=D(terms.unit_amount),
                status=SubscriptionItemStatus.ACTIVE,
            )
        )
        db.flush()

    # Create initial BillingCycle
    bc = BillingCycle(
        organization_id=ctx.organization_id,
        subscription_id=subscription.id,
        cycle_number=1,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        status=BillingCycleStatus.OPEN,
    )
    db.add(bc)
    db.flush()

    # Register OutboxEvent for transactional decoupling
    outbox = OutboxEvent(
        organization_id=ctx.organization_id,
        event_type=DomainEventType.SUBSCRIPTION_CREATED.value,
        aggregate_type="subscription",
        aggregate_id=subscription.id,
        payload={"subscription_number": subscription.subscription_number, "status": subscription.status.value},
        status=OutboxStatus.PENDING,
    )
    db.add(outbox)

    if status == SubscriptionStatus.TRIALING:
        from backend.app.models.trials import TrialPeriod, TrialPeriodStatus
        tp = TrialPeriod(
            organization_id=ctx.organization_id,
            subscription_id=subscription.id,
            trial_start_date=start,
            trial_end_date=trial_end,
            extension_count=0,
            max_extensions_allowed=2,
            allow_customer_extension=True,
            allow_early_conversion=True,
            auto_charge_enabled=True,
            status=TrialPeriodStatus.ACTIVE,
        )
        db.add(tp)
        db.flush()

    after = {**snapshot(subscription), "plan_id": plan.id, "customer_id": customer.id}
    if plan.offering_id:
        after["offering_id"] = plan.offering_id
    audit.record(
        db,
        action="SUBSCRIPTION_CREATED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        ctx=ctx,
        after={**after, **(audit_extra or {})},
    )

    generate_first = generate_first_invoice if generate_first_invoice is not None else (status == SubscriptionStatus.ACTIVE)
    if generate_first and status == SubscriptionStatus.ACTIVE:
        db.refresh(subscription)
        generate_period_invoice(db, subscription, ctx=ctx, include_setup_fee=True)
    return subscription


def activate_subscription(db: Session, ctx: CurrentContext, subscription: Subscription) -> Subscription:
    """Transition DRAFT or PENDING_ACTIVATION subscription to ACTIVE."""
    activatable = (SubscriptionStatus.DRAFT, SubscriptionStatus.PENDING_ACTIVATION)
    if subscription.status not in activatable:
        raise InvalidStateError(f"Only draft or pending subscriptions can be activated; this one is {subscription.status.value}.")
    # Serialise concurrent activations: re-read under a row lock and claim the transition
    # with a conditional UPDATE below. Only the request that performed the transition goes
    # on to invoice and audit; a loser gets 409 and records nothing.
    lock_and_reload(db, subscription)
    if subscription.status not in activatable:
        raise InvalidStateError("This subscription has already been activated.")
    inactive_offering = _inactive_linked_offering_name(db, subscription.plan)
    if inactive_offering:
        raise ValidationAppError(
            f"The plan '{inactive_offering}' is inactive and cannot be activated.",
            {"fields": {"plan_id": "inactive plan"}},
        )

    lock_customer_row(db, ctx.organization_id, subscription.customer_id)
    assert_no_conflicting_subscription(
        db, ctx.organization_id, subscription.customer_id, subscription.plan_id, exclude_id=subscription.id
    )

    before = snapshot(subscription)
    today = timezones.org_today(ctx.organization)
    months = interval_months(subscription.plan)
    if not claim_status_transition(db, subscription, activatable, SubscriptionStatus.ACTIVE):
        raise InvalidStateError("This subscription has already been activated.")
    subscription.current_period_start = today
    subscription.current_period_end = add_months(today, months, today.day)
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()
    subscription.updated_by_id = ctx.user.id
    db.flush()

    # The first period starts now, so bill it now (the next scheduler renewal only
    # bills from current_period_end onwards - without this the first period was free).
    if not period_invoice_exists(db, subscription):
        generate_period_invoice(db, subscription, ctx=ctx, include_setup_fee=True)

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

    if (
        "quantity" in changes
        and changes["quantity"] is not None
        and int(changes["quantity"]) != int(subscription.quantity or 1)
    ):
        qty = int(changes["quantity"])
        if subscription.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
            # Live subscriptions: a seat change is a subscription change - prorated
            # (credit note / invoice) and applied to the item + snapshot. It commits.
            from backend.app.services.subscription_change_service import apply_subscription_change

            apply_subscription_change(db, ctx, subscription.id, target_quantity=Decimal(qty))
            db.refresh(subscription)
        else:
            price, meta = terms_for_quantity(db, subscription, plan, qty, same_plan=True)
            apply_plan_terms(db, subscription, plan, qty, unit_price=price, metadata=meta)

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
    _emit(db, subscription, "subscription.paused")
    db.commit()
    return get_subscription(db, ctx.organization_id, subscription.id)


def resume_subscription(db: Session, ctx: CurrentContext, subscription: Subscription) -> Subscription:
    if subscription.status != SubscriptionStatus.PAUSED:
        raise InvalidStateError(f"Only paused subscriptions can be resumed; this one is {subscription.status.value}.")
    # Serialise with concurrent resumes / activations / creates for this customer, then
    # re-check state and conflicts under the lock; a loser changes and records nothing.
    lock_customer_row(db, ctx.organization_id, subscription.customer_id)
    lock_and_reload(db, subscription)
    if subscription.status != SubscriptionStatus.PAUSED:
        raise InvalidStateError("This subscription has already been resumed.")
    assert_no_conflicting_subscription(
        db,
        ctx.organization_id,
        subscription.customer_id,
        subscription.plan_id,
        statuses=(SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING),
        exclude_id=subscription.id,
    )
    before = snapshot(subscription)
    today = timezones.org_today(ctx.organization)
    if not claim_status_transition(db, subscription, (SubscriptionStatus.PAUSED,), SubscriptionStatus.ACTIVE):
        raise InvalidStateError("This subscription has already been resumed.")
    subscription.paused_at = None
    subscription.current_period_start = today
    subscription.current_period_end = period_end_for(today, subscription.plan, today.day)
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()
    subscription.updated_by_id = ctx.user.id
    db.flush()
    # Resuming restarts the period today; invoice it (idempotent per period start).
    if not period_invoice_exists(db, subscription):
        generate_period_invoice(db, subscription, ctx=ctx)
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
    _emit(db, subscription, "subscription.resumed")
    db.commit()
    return get_subscription(db, ctx.organization_id, subscription.id)


def _emit(db: Session, subscription: Subscription, event_type: str, **extra: Any) -> None:
    """Queue a webhook/automation outbox event in the caller's transaction (never fatal)."""
    try:
        from backend.app.services.outbox_processor import emit_event

        emit_event(db, subscription.organization_id, event_type, {"subscription_id": subscription.id, **extra})
    except Exception:
        from backend.app.core.logging import logger

        logger.exception("Could not queue %s for subscription %s", event_type, subscription.id)


def _end_now(subscription: Subscription, reason: Optional[str] = None) -> None:
    now = utcnow()
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = subscription.cancelled_at or now
    subscription.cancellation_reason = reason
    subscription.ended_at = now
    subscription.next_billing_date = None
    subscription.cancel_at_period_end = False
    subscription.updated_at = now


def _unused_period_credit(db: Session, subscription: Subscription, today: date) -> Decimal:
    """Pre-tax value of the unused remainder of an invoiced current period (0 when none)."""
    from backend.app.services.proration_calculator import calculate_proration

    if subscription.status != SubscriptionStatus.ACTIVE or not period_invoice_exists(db, subscription):
        return Decimal("0")
    plan = subscription.plan
    calc = calculate_proration(
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        change_date=today,
        old_price=contracted_unit_price(db, subscription, plan),
        new_price=Decimal("0"),
        old_quantity=billable_units(plan, subscription.quantity or 1),
        new_quantity=Decimal("0"),
        currency=subscription.currency or plan.currency,
    )
    return calc.unused_credit


def cancel_subscription(
    db: Session,
    ctx: CurrentContext,
    subscription: Subscription,
    *,
    at_period_end: bool,
    reason: Optional[str],
    prorate_credit: bool = False,
) -> Subscription:
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise InvalidStateError("This subscription is already cancelled.")
    before = snapshot(subscription)
    credit_amount = Decimal("0")
    if at_period_end and subscription.status != SubscriptionStatus.PAUSED:
        subscription.cancel_at_period_end = True
        subscription.cancelled_at = utcnow()
        subscription.cancellation_reason = reason
        subscription.updated_at = utcnow()
        subscription.updated_by_id = ctx.user.id
    else:
        if prorate_credit:
            credit_amount = _unused_period_credit(db, subscription, timezones.org_today(ctx.organization))
        _end_now(subscription, reason=reason)
        subscription.updated_by_id = ctx.user.id
    db.flush()
    credit_note_id = None
    if credit_amount > 0:
        from backend.app.services import credit_service

        plan = subscription.plan
        credit_note = credit_service.create_credit_note(
            db,
            ctx,
            customer_id=subscription.customer_id,
            subscription_id=subscription.id,
            reason=f"Prorated credit for immediate cancellation of {subscription.subscription_number}",
            currency=subscription.currency or plan.currency,
            lines=[
                {
                    "description": f"Unused period credit - {plan.name}",
                    "amount": credit_amount,
                    "tax_rate_pct": plan_tax_rate(plan, subscription.customer),
                }
            ],
        )
        credit_note_id = credit_note.id
    audit.record(
        db,
        action="SUBSCRIPTION_CANCELLED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        ctx=ctx,
        before=before,
        after={
            **snapshot(subscription),
            "reason": reason,
            "at_period_end": at_period_end,
            "credit_note_id": credit_note_id,
        },
    )
    _emit(db, subscription, "subscription.cancelled")
    db.commit()
    return get_subscription(db, ctx.organization_id, subscription.id)


# --- scheduler primitives (no commit) -----------------------------------------------------------------------------------


def end_cancelled_trial(db: Session, subscription: Subscription, *, actor_label: str = audit.SYSTEM_ACTOR) -> None:
    """A trial whose customer asked to cancel at period end ends at trial end - never converts/charges."""
    before = snapshot(subscription)
    reason = subscription.cancellation_reason or "cancel_at_period_end reached at trial end"
    _end_now(subscription, reason=reason)
    if subscription.trial_period:
        from backend.app.models.trials import TrialPeriodStatus

        subscription.trial_period.status = TrialPeriodStatus.CANCELLED
        subscription.trial_period.cancelled_at = utcnow()
        subscription.trial_period.updated_at = utcnow()
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
        after={**snapshot(subscription), "reason": reason},
    )


def convert_trial(db: Session, subscription: Subscription, *, actor_label: str = audit.SYSTEM_ACTOR) -> Optional[Invoice]:
    """Scheduler: trialing -> active at trial end, first period starts, renewal invoice issued."""
    if subscription.status != SubscriptionStatus.TRIALING:
        return None
    if subscription.cancel_at_period_end:
        end_cancelled_trial(db, subscription, actor_label=actor_label)
        return None
    # Re-check under the row lock and claim the transition: an overlapping run (or a manual
    # conversion) that already converted it wins, and this call records nothing.
    lock_and_reload(db, subscription)
    if subscription.status != SubscriptionStatus.TRIALING:
        return None
    try:
        assert_no_conflicting_subscription(
            db,
            subscription.organization_id,
            subscription.customer_id,
            subscription.plan_id,
            statuses=(SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING),
            exclude_id=subscription.id,
        )
    except ValidationAppError as exc:
        # Pre-existing duplicate: never create a second live subscription automatically.
        from backend.app.core.logging import logger

        logger.warning("Trial conversion skipped for %s: %s", subscription.id, exc)
        return None
    before = snapshot(subscription)
    period_start = subscription.trial_end or timezones.org_today_for_id(db, subscription.organization_id)
    if not claim_status_transition(db, subscription, (SubscriptionStatus.TRIALING,), SubscriptionStatus.ACTIVE):
        return None
    subscription.current_period_start = period_start
    subscription.current_period_end = period_end_for(period_start, subscription.plan, period_start.day)
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()
    if subscription.trial_period:
        from backend.app.models.trials import TrialPeriodStatus
        subscription.trial_period.status = TrialPeriodStatus.CONVERTED
        subscription.trial_period.converted_at = utcnow()
        subscription.trial_period.updated_at = utcnow()
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


def is_renewal_due(subscription: Subscription, today: Optional[date] = None) -> bool:
    today = today or date.today()
    return subscription.next_billing_date is not None and subscription.next_billing_date <= today


def renew_subscription(
    db: Session,
    subscription: Subscription,
    *,
    actor_label: str = audit.SYSTEM_ACTOR,
    only_if_due: bool = False,
    today: Optional[date] = None,
) -> str:
    """Advance the period and issue the renewal invoice, or end it when cancel_at_period_end
    or auto_renewal is off.

    `only_if_due` (scheduler / manual endpoint) re-checks next_billing_date after taking the
    row lock, so two overlapping runs cannot both advance the same period.
    """
    db.flush()
    lock_subscription_row(db, subscription.id)
    db.refresh(subscription)
    if subscription.status != SubscriptionStatus.ACTIVE:
        return "skipped"
    if only_if_due and not is_renewal_due(
        subscription, today or timezones.org_today_for_id(db, subscription.organization_id)
    ):
        return "skipped"
    customer = subscription.customer
    if customer is not None and getattr(customer.status, "value", customer.status) == "inactive":
        # Inactive customers are not billed further; the subscription stays as-is until
        # the customer is reactivated or the subscription is cancelled.
        return "skipped"
    before = snapshot(subscription)
    if not subscription.cancel_at_period_end and subscription.auto_renewal is False:
        now = utcnow()
        subscription.status = SubscriptionStatus.EXPIRED
        subscription.ended_at = now
        subscription.next_billing_date = None
        subscription.updated_at = now
        db.flush()
        audit.record(
            db,
            action="SUBSCRIPTION_EXPIRED",
            entity_type="subscription",
            entity_id=subscription.id,
            entity_label=subscription.subscription_number,
            organization_id=subscription.organization_id,
            actor_label=actor_label,
            before=before,
            after={**snapshot(subscription), "reason": "auto_renewal disabled"},
        )
        return "ended"
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

    # Create next BillingCycle if not already present
    existing_bc = db.scalars(
        select(BillingCycle).where(
            BillingCycle.subscription_id == subscription.id,
            BillingCycle.period_start == subscription.current_period_start,
        )
    ).first()
    if existing_bc is None:
        max_cycle = db.scalar(
            select(func.max(BillingCycle.cycle_number)).where(
                BillingCycle.subscription_id == subscription.id
            )
        ) or 0
        bc = BillingCycle(
            organization_id=subscription.organization_id,
            subscription_id=subscription.id,
            cycle_number=max_cycle + 1,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            status=BillingCycleStatus.OPEN,
        )
        db.add(bc)
    db.flush()

    invoice = None
    if not period_invoice_exists(db, subscription):
        invoice = generate_period_invoice(db, subscription, actor_label=actor_label)

    outbox = OutboxEvent(
        organization_id=subscription.organization_id,
        event_type=DomainEventType.SUBSCRIPTION_RENEWED.value,
        aggregate_type="subscription",
        aggregate_id=subscription.id,
        payload={"subscription_number": subscription.subscription_number, "invoice_id": invoice.id if invoice else None},
        status=OutboxStatus.PENDING,
    )
    db.add(outbox)
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
    _emit(db, subscription, "subscription.renewed", invoice_id=invoice.id if invoice else None)
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
    "end_cancelled_trial",
    "renew_subscription",
    "is_renewal_due",
    "apply_plan_terms",
    "contracted_unit_price",
    "plan_tax_rate",
    "lock_subscription_row",
]

"""Control-center read models (contract §10): dashboard summary, action center, calendar, activity.

Everything is computed with SQL aggregates scoped to the organization; the only
Python loops are over the small "recent" lists.

Documented approximations
- revenue = Σ (amount - amount_refunded) of settled payments by paid_at.
- pipeline amounts: draft/paid use `total`, open buckets use `amount_due`.
- MRR (compute_mrr) = sum over ACTIVE + PAST_DUE subscriptions of the subscription's own
  unit price x quantity - discount, normalised to a month, plus every ACTIVE add-on item
  (snapshot unit price x quantity, normalised by the item's own interval); reported in the
  org's base currency with other currencies listed separately (never summed across currencies).
- Date ranges are organization-local business days ([local 00:00, local 00:00) in UTC).
- mrr_change_pct compares today's MRR with the MRR of subscriptions that were billing at
  the start of the previous month (created before it, not cancelled/ended before it).
- churn_rate = logo churn: customers billing at period start who cancelled during the
  period with nothing left billing / customers billing at period start.
- recovery.recovered_amount = settled payments in range from customers who also
  had a failed payment in the range (failed gateway attempts carry no allocation).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.billing_cycles import SubscriptionItem, SubscriptionItemStatus, SubscriptionItemType
from backend.app.services import timezones

from backend.app.core.exceptions import ValidationAppError
from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    ApprovalRequest,
    ApprovalStatus,
    AuditLog,
    AuditStatus,
    INTERVAL_MONTHS,
    Customer,
    CustomerStatus,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentAllocation,
    PaymentStatus,
    Plan,
    PricingModel,
    Quote,
    QuoteStatus,
    Subscription,
    SubscriptionStatus,
    User,
)
from backend.app.schemas.common_refs import customer_ref, iso_dt, money_str
from backend.app.services.invoice_service import SETTLED_PAYMENT_STATUSES
from backend.app.services.money import D, q2
from backend.app.services.pagination import PageParams, paginate
from backend.app.services.payment_service import serialize_payment
from backend.app.services.subscription_service import add_months, effective_unit_price

RANGE_KEYS = ("today", "7_days", "30_days", "3_months", "12_months")


# --- helpers ---------------------------------------------------------------------------------------


def _bounds(start: date, end: date, tz: Any) -> Tuple[datetime, datetime]:
    """[start 00:00, end+1 00:00) in the organization's timezone, as UTC instants."""
    lo, hi = timezones.range_bounds_utc(start, end, tz)
    return lo, hi


def _dec(value) -> Decimal:
    return q2(D(value if value is not None else 0))


def _pct_change(current: Decimal, previous: Decimal) -> Optional[str]:
    if previous is None or previous == 0:
        return None
    return money_str((current - previous) / previous * 100)


def resolve_range(range_key: str, today: Optional[date] = None) -> Tuple[date, date, date, date]:
    """Return (start, end, prev_start, prev_end) for a dashboard range."""
    today = today or timezones.utc_today()
    if range_key == "today":
        start = today
    elif range_key == "7_days":
        start = today - timedelta(days=6)
    elif range_key == "30_days":
        start = today - timedelta(days=29)
    elif range_key == "3_months":
        start = add_months(today, -3) + timedelta(days=1)
    elif range_key == "12_months":
        start = add_months(today, -12) + timedelta(days=1)
    else:
        raise ValidationAppError("Unknown range.", {"fields": {"range": f"must be one of {', '.join(RANGE_KEYS)}"}})
    length = (today - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length - 1)
    return start, today, prev_start, prev_end


def _month_label(value: date) -> str:
    return value.strftime("%b %Y")


# --- aggregate building blocks -----------------------------------------------------------------------------


def _revenue_between(db: Session, org_id: str, start: date, end: date, tz: Any = None) -> Decimal:
    lo, hi = _bounds(start, end, tz if tz is not None else timezones.org_tz_for_id(db, org_id))
    value = db.scalar(
        select(func.coalesce(func.sum(Payment.amount - Payment.amount_refunded), 0)).where(
            Payment.organization_id == org_id,
            Payment.status.in_(SETTLED_PAYMENT_STATUSES),
            Payment.paid_at >= lo,
            Payment.paid_at < hi,
        )
    )
    return _dec(value)


def _invoiced_between(db: Session, org_id: str, start: date, end: date, tz: Any = None) -> Decimal:
    lo, hi = _bounds(start, end, tz if tz is not None else timezones.org_tz_for_id(db, org_id))
    value = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.organization_id == org_id,
            Invoice.status != InvoiceStatus.VOID,
            Invoice.sent_at >= lo,
            Invoice.sent_at < hi,
        )
    )
    return _dec(value)


# Statuses whose subscriptions bill today. PAST_DUE still bills (the renewal is unpaid,
# not cancelled); trials, drafts and paused subscriptions do not.
MRR_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE)
# Statuses that can never have been billing at an earlier point in time.
_NEVER_BILLED_STATUSES = (
    SubscriptionStatus.DRAFT,
    SubscriptionStatus.PENDING_ACTIVATION,
    SubscriptionStatus.TRIALING,
    SubscriptionStatus.TRIAL_EXPIRED,
)


def _live_subscription_filters(org_id: str, as_of: Optional[datetime]) -> List[Any]:
    """Filters selecting subscriptions that were billing at `as_of` (now when None).

    History is reconstructed from created_at / cancelled_at / ended_at (there is no
    status history table): a subscription counts when it existed before `as_of`, was
    not cancelled or ended before it, and is not in a status that never bills.
    """
    filters: List[Any] = [Subscription.organization_id == org_id]
    if as_of is None:
        filters.append(Subscription.status.in_(list(MRR_STATUSES)))
        return filters
    filters.extend(
        [
            Subscription.created_at < as_of,
            or_(Subscription.cancelled_at.is_(None), Subscription.cancelled_at >= as_of),
            or_(Subscription.ended_at.is_(None), Subscription.ended_at >= as_of),
            Subscription.status.not_in(list(_NEVER_BILLED_STATUSES)),
        ]
    )
    return filters


def _primary_monthly_amount(subscription: Subscription, plan: Plan) -> Decimal:
    months = INTERVAL_MONTHS.get(plan.billing_interval)
    if not months:
        return Decimal("0")
    months *= max(1, int(plan.interval_count or 1))
    units = D(subscription.quantity or 1) if plan.pricing_model == PricingModel.PER_UNIT else Decimal("1")
    period_amount = effective_unit_price(subscription, plan) * units - D(subscription.discount_amount or 0)
    if period_amount <= 0:
        return Decimal("0")
    return period_amount / Decimal(months)


def addon_monthly_amount(item: SubscriptionItem) -> Decimal:
    """One ACTIVE add-on item's recurring amount normalised to a month.

    Priced exactly as generate_period_invoice bills it: the item's immutable price
    snapshot (else its own unit_price, else its plan's list price) x quantity for per-unit
    pricing (1 otherwise), over the snapshot's (else the item plan's) billing interval.
    Items carry no discount of their own. One-time items contribute nothing.
    """
    if item.status != SubscriptionItemStatus.ACTIVE or item.item_type != SubscriptionItemType.ADDON:
        return Decimal("0")
    snap = item.price_snapshot
    item_plan = item.plan
    interval = snap.billing_interval if snap is not None else (item_plan.billing_interval if item_plan else None)
    count = (snap.interval_count if snap is not None else (item_plan.interval_count if item_plan else 1)) or 1
    months = INTERVAL_MONTHS.get(interval) if interval is not None else None
    if not months:
        return Decimal("0")
    months *= max(1, int(count))
    pricing_model = snap.pricing_model if snap is not None else (item_plan.pricing_model if item_plan else PricingModel.FLAT)
    units = D(item.quantity or 1) if pricing_model == PricingModel.PER_UNIT else Decimal("1")
    if snap is not None:
        unit_amount = D(snap.unit_amount)
    elif item.unit_price is not None and D(item.unit_price) > 0:
        unit_amount = D(item.unit_price)
    else:
        unit_amount = D(item_plan.unit_amount if item_plan else 0)
    period_amount = unit_amount * units
    if period_amount <= 0:
        return Decimal("0")
    return period_amount / Decimal(months)


def subscription_monthly_amount(subscription: Subscription, plan: Plan) -> Decimal:
    """The subscription's contracted recurring amount, normalised to one month.

    Primary plan: the price agreed on the subscription (falling back to the plan list
    price when no override was stored) x quantity - discount, so negotiated prices and
    discounts are reflected. Plus every ACTIVE add-on item (e.g. the extra recurring lines
    of a converted multi-line quote), each normalised by its own interval. PLAN items are
    the primary line (already counted) and METERED items are usage, not recurring revenue.
    One-time plans/items contribute nothing.
    """
    amount = _primary_monthly_amount(subscription, plan)
    for item in subscription.subscription_items or []:
        amount += addon_monthly_amount(item)
    return amount


def compute_mrr(
    db: Session,
    org_id: str,
    as_of: Optional[datetime] = None,
    base_currency: Optional[str] = None,
) -> Dict[str, Any]:
    """The single MRR definition used by the dashboard, the AI assistant and reports.

    Returns {"currency", "mrr" (base currency), "by_currency" {cur: Decimal},
    "other_currencies" {cur: Decimal}, "subscription_count"}. Amounts in different
    currencies are never added together: the headline figure is the org's base
    currency and the rest are listed separately.
    """
    if base_currency is None:
        from backend.app.models import Organization

        org = db.get(Organization, org_id)
        base_currency = (org.default_currency if org else None) or "INR"
    base_currency = base_currency.upper()
    rows = db.execute(
        select(Subscription, Plan)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(*_live_subscription_filters(org_id, as_of))
        .options(
            selectinload(Subscription.subscription_items).selectinload(SubscriptionItem.price_snapshot),
            selectinload(Subscription.subscription_items).selectinload(SubscriptionItem.plan),
        )
    ).all()
    by_currency: Dict[str, Decimal] = {}
    counted = 0
    for subscription, plan in rows:
        amount = subscription_monthly_amount(subscription, plan)
        if not INTERVAL_MONTHS.get(plan.billing_interval) and amount <= 0:
            continue  # one-time plans (with no recurring add-ons) are not recurring revenue
        currency = (subscription.currency or plan.currency or base_currency).upper()
        by_currency[currency] = by_currency.get(currency, Decimal("0")) + amount
        counted += 1
    by_currency = {cur: q2(value) for cur, value in by_currency.items()}
    return {
        "currency": base_currency,
        "mrr": by_currency.get(base_currency, Decimal("0.00")),
        "by_currency": by_currency,
        "other_currencies": {cur: v for cur, v in by_currency.items() if cur != base_currency},
        "subscription_count": counted,
    }


def logo_churn(db: Session, org_id: str, lo: datetime, hi: datetime) -> Tuple[int, int, Optional[str]]:
    """Logo churn for [lo, hi).

    churned = customers billing at `lo` who cancelled during the period and have
    nothing left billing; base = customers billing at `lo`. Returns
    (churned, base, churn_rate_pct), the rate being None when the base is empty.
    """
    start_customers = set(
        db.scalars(select(Subscription.customer_id).where(*_live_subscription_filters(org_id, lo)).distinct())
    )
    if not start_customers:
        return 0, 0, None
    cancelled_customers = set(
        db.scalars(
            select(Subscription.customer_id)
            .where(
                Subscription.organization_id == org_id,
                Subscription.cancelled_at >= lo,
                Subscription.cancelled_at < hi,
                Subscription.customer_id.in_(start_customers),
            )
            .distinct()
        )
    )
    still_billing: set = set()
    if cancelled_customers:
        still_billing = set(
            db.scalars(
                select(Subscription.customer_id)
                .where(
                    Subscription.organization_id == org_id,
                    Subscription.customer_id.in_(cancelled_customers),
                    Subscription.status.in_(
                        [
                            SubscriptionStatus.ACTIVE,
                            SubscriptionStatus.PAST_DUE,
                            SubscriptionStatus.TRIALING,
                            SubscriptionStatus.PAUSED,
                        ]
                    ),
                )
                .distinct()
            )
        )
    churned = len(cancelled_customers - still_billing)
    rate = money_str(Decimal(churned) / Decimal(len(start_customers)) * 100)
    return churned, len(start_customers), rate


def _bucket(db: Session, org_id: str, statuses, amount_column) -> Dict[str, Any]:
    row = db.execute(
        select(func.count(), func.coalesce(func.sum(amount_column), 0)).where(
            Invoice.organization_id == org_id, Invoice.status.in_(list(statuses))
        )
    ).one()
    return {"count": int(row[0] or 0), "amount": money_str(_dec(row[1]))}


# --- dashboard summary ------------------------------------------------------------------------------------------


def dashboard_summary(db: Session, organization, range_key: str = "30_days") -> Dict[str, Any]:
    org_id = organization.id
    tz = timezones.resolve_tz(organization)
    today = timezones.org_today(organization)
    start, end, prev_start, prev_end = resolve_range(range_key, today)
    lo, hi = _bounds(start, end, tz)

    # --- metrics
    revenue = _revenue_between(db, org_id, start, end, tz)
    prev_revenue = _revenue_between(db, org_id, prev_start, prev_end, tz)
    outstanding = db.execute(
        select(func.count(), func.coalesce(func.sum(Invoice.amount_due), 0)).where(
            Invoice.organization_id == org_id, Invoice.status.in_(list(OPEN_INVOICE_STATUSES))
        )
    ).one()
    overdue = db.execute(
        select(func.count(), func.coalesce(func.sum(Invoice.amount_due), 0)).where(
            Invoice.organization_id == org_id,
            or_(
                Invoice.status == InvoiceStatus.OVERDUE,
                and_(Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]), Invoice.due_date < today),
            ),
        )
    ).one()
    active_customers = db.scalar(
        select(func.count()).select_from(Customer).where(Customer.organization_id == org_id, Customer.status == CustomerStatus.ACTIVE)
    )
    new_customers = db.scalar(
        select(func.count()).select_from(Customer).where(Customer.organization_id == org_id, Customer.created_at >= lo, Customer.created_at < hi)
    )
    past_due_subs = db.scalar(
        select(func.count()).select_from(Subscription).where(
            Subscription.organization_id == org_id, Subscription.status == SubscriptionStatus.PAST_DUE
        )
    )

    # --- revenue block
    base_currency = (organization.default_currency or "INR").upper()
    mrr_now = compute_mrr(db, org_id, base_currency=base_currency)
    mrr = mrr_now["mrr"]
    prev_month_start = timezones.day_start_utc(add_months(today.replace(day=1), -1), tz)
    prev_mrr = compute_mrr(db, org_id, as_of=prev_month_start, base_currency=base_currency)["mrr"]
    churned_customers, churn_base, churn_rate = logo_churn(db, org_id, lo, hi)
    trend: List[Dict[str, Any]] = []
    first_of_month = today.replace(day=1)
    for offset in range(11, -1, -1):
        month_start = add_months(first_of_month, -offset)
        month_end = add_months(month_start, 1) - timedelta(days=1)
        trend.append(
            {
                "label": _month_label(month_start),
                "period_start": month_start,
                "revenue": money_str(_revenue_between(db, org_id, month_start, month_end, tz)),
                "invoiced": money_str(_invoiced_between(db, org_id, month_start, month_end, tz)),
            }
        )

    # --- pipeline
    paid_row = db.execute(
        select(func.count(), func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.organization_id == org_id, Invoice.status == InvoiceStatus.PAID, Invoice.paid_at >= lo, Invoice.paid_at < hi
        )
    ).one()
    pipeline = {
        "draft": _bucket(db, org_id, [InvoiceStatus.DRAFT], Invoice.total),
        "sent": _bucket(db, org_id, [InvoiceStatus.SENT], Invoice.amount_due),
        "partially_paid": _bucket(db, org_id, [InvoiceStatus.PARTIALLY_PAID], Invoice.amount_due),
        "overdue": _bucket(db, org_id, [InvoiceStatus.OVERDUE], Invoice.amount_due),
        "paid_this_period": {"count": int(paid_row[0] or 0), "amount": money_str(_dec(paid_row[1]))},
    }

    # --- customer health (subscription statuses)
    health = {s.value: 0 for s in SubscriptionStatus}
    for status_value, count in db.execute(
        select(Subscription.status, func.count()).where(Subscription.organization_id == org_id).group_by(Subscription.status)
    ).all():
        key = status_value.value if hasattr(status_value, "value") else str(status_value)
        health[key] = int(count)
    cancelled_this_period = db.scalar(
        select(func.count()).select_from(Subscription).where(
            Subscription.organization_id == org_id,
            Subscription.status == SubscriptionStatus.CANCELLED,
            Subscription.cancelled_at >= lo,
            Subscription.cancelled_at < hi,
        )
    )

    # --- recovery
    failed_row = db.execute(
        select(func.count(), func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.organization_id == org_id, Payment.status == PaymentStatus.FAILED, Payment.created_at >= lo, Payment.created_at < hi
        )
    ).one()
    failed_customers = (
        select(Payment.customer_id)
        .where(
            Payment.organization_id == org_id,
            Payment.status == PaymentStatus.FAILED,
            Payment.customer_id.is_not(None),
            Payment.created_at >= lo,
            Payment.created_at < hi,
        )
        .distinct()
    )
    recovered = db.scalar(
        select(func.coalesce(func.sum(Payment.amount - Payment.amount_refunded), 0)).where(
            Payment.organization_id == org_id,
            Payment.status.in_(SETTLED_PAYMENT_STATUSES),
            Payment.paid_at >= lo,
            Payment.paid_at < hi,
            Payment.customer_id.in_(failed_customers),
        )
    )
    reminders_sent = db.scalar(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "INVOICE_REMINDER_SENT",
            AuditLog.created_at >= lo,
            AuditLog.created_at < hi,
        )
    )

    # --- recent lists
    recent_payments = db.scalars(
        select(Payment)
        .options(
            selectinload(Payment.customer),
            selectinload(Payment.allocations).selectinload(PaymentAllocation.invoice),
            selectinload(Payment.refunds),
        )
        .where(Payment.organization_id == org_id)
        .order_by(Payment.created_at.desc())
        .limit(8)
    ).all()
    recent_audit = db.scalars(
        select(AuditLog).where(AuditLog.organization_id == org_id).order_by(AuditLog.created_at.desc()).limit(10)
    ).all()

    return {
        "currency": organization.default_currency or "INR",
        "range": range_key,
        "period_start": start,
        "period_end": end,
        "metrics": {
            "total_revenue": money_str(revenue),
            "revenue_change_pct": _pct_change(revenue, prev_revenue),
            "outstanding_amount": money_str(_dec(outstanding[1])),
            "outstanding_count": int(outstanding[0] or 0),
            "overdue_count": int(overdue[0] or 0),
            "active_customers": int(active_customers or 0),
            "new_customers": int(new_customers or 0),
            "at_risk_amount": money_str(_dec(overdue[1])),
            "at_risk_count": int(overdue[0] or 0) + int(past_due_subs or 0),
        },
        "revenue": {
            "mrr": money_str(mrr),
            "arr": money_str(mrr * 12),
            "mrr_change_pct": _pct_change(mrr, prev_mrr),
            "mrr_currency": base_currency,
            "mrr_other_currencies": {cur: money_str(v) for cur, v in mrr_now["other_currencies"].items()},
            "trend": trend,
        },
        "pipeline": pipeline,
        "customer_health": {
            "active": health["active"],
            "trialing": health["trialing"],
            "past_due": health["past_due"],
            "paused": health["paused"],
            "cancelled_this_period": int(cancelled_this_period or 0),
            "churned_customers": churned_customers,
            "customers_at_period_start": churn_base,
            "churn_rate": churn_rate,
        },
        "recovery": {
            "failed_payments": int(failed_row[0] or 0),
            "failed_amount": money_str(_dec(failed_row[1])),
            "recovered_amount": money_str(_dec(recovered)),
            "reminders_sent": int(reminders_sent or 0),
        },
        "recent_transactions": [serialize_payment(p) for p in recent_payments],
        "activity": [activity_item(row) for row in recent_audit],
    }


# --- activity (derived from audit_logs) ------------------------------------------------------------------------------

CATEGORY_BY_ENTITY = {
    "invoice": "billing",
    "quote": "billing",
    "subscription": "billing",
    "customer": "customers",
    "payment": "payments",
    "refund": "payments",
}
ENTITIES_BY_CATEGORY: Dict[str, List[str]] = {
    "billing": ["invoice", "quote", "subscription"],
    "customers": ["customer"],
    "payments": ["payment", "refund"],
}
SYSTEM_ENTITIES = ["user", "organization", "membership", "product", "plan", "approval", "import", "webhook"]


def activity_category(entity_type: Optional[str]) -> str:
    return CATEGORY_BY_ENTITY.get((entity_type or "").lower(), "system")


def activity_severity(row: AuditLog) -> str:
    status = row.status.value if hasattr(row.status, "value") else str(row.status or "")
    if status == AuditStatus.DENIED.value:
        return "danger"
    if status == AuditStatus.WARNING.value:
        return "warning"
    action = (row.action or "").upper()
    if action.endswith("_PAID") or action.endswith("_CAPTURED") or action.endswith("_APPROVED"):
        return "success"
    return "normal"


def humanize_action(action: str) -> str:
    words = (action or "").lower().replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else "Activity"


def activity_item(row: AuditLog) -> Dict[str, Any]:
    label = row.entity_label or (row.entity_type or "").title()
    description = f"{label} - {row.actor_label}" if label else row.actor_label
    title = humanize_action(row.action)
    from backend.app.services import quote_service

    if row.entity_type == "quote" and quote_service.is_decision_action(row.action):
        # Say who decided: the customer on their link, or an admin override (with its reason).
        described = quote_service.describe_decision(row)
        title = f"Quote {described['title'][:1].lower()}{described['title'][1:]}"
        actor = described["actor_display"]
        description = f"{label} - {actor}" if label else actor
        if described["reason"]:
            description = f"{description} - Reason: {described['reason']}"
    return {
        "id": row.id,
        "title": title,
        "description": description,
        "timestamp": iso_dt(row.created_at),
        "category": activity_category(row.entity_type),
        "severity": activity_severity(row),
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
    }


def list_activity(db: Session, organization_id: str, params: PageParams, category: str = "all"):
    stmt = select(AuditLog).where(AuditLog.organization_id == organization_id)
    if category and category != "all":
        if category in ENTITIES_BY_CATEGORY:
            stmt = stmt.where(AuditLog.entity_type.in_(ENTITIES_BY_CATEGORY[category]))
        elif category == "system":
            stmt = stmt.where(AuditLog.entity_type.not_in(sum(ENTITIES_BY_CATEGORY.values(), [])))
        else:
            raise ValidationAppError("Unknown category.", {"fields": {"category": "must be all|billing|customers|payments|system"}})
    stmt = stmt.order_by(AuditLog.created_at.desc())
    return paginate(db, stmt, params)


# --- action center ----------------------------------------------------------------------------------------------------------

URGENCY_RANK = {"critical": 0, "high": 1, "medium": 2}


def action_center(db: Session, organization_id: str) -> Dict[str, Any]:
    today = timezones.org_today_for_id(db, organization_id)
    now = timezones.utc_now()
    items: List[Dict[str, Any]] = []

    overdue_invoices = db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .where(
            Invoice.organization_id == organization_id,
            or_(
                Invoice.status == InvoiceStatus.OVERDUE,
                and_(Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]), Invoice.due_date < today),
            ),
        )
        .order_by(Invoice.due_date.asc())
    ).all()
    for inv in overdue_invoices:
        days = max(0, (today - inv.due_date).days)
        items.append(
            {
                "id": f"overdue:{inv.id}",
                "category": "overdue",
                "title": f"Invoice {inv.invoice_number} is overdue",
                "description": f"{inv.customer.display_name} owes {inv.currency} {q2(inv.amount_due):,.2f}; due {inv.due_date.isoformat()}."
                + (f" {inv.reminder_count} reminder(s) sent." if inv.reminder_count else ""),
                "amount": money_str(inv.amount_due),
                "customer": customer_ref(inv.customer),
                "entity_type": "invoice",
                "entity_id": inv.id,
                "due_info": f"{days} day{'s' if days != 1 else ''} overdue",
                "urgency": "critical" if days > 14 else "high",
                "suggested_action": "send_reminder",
            }
        )

    failed_payments = db.scalars(
        select(Payment)
        .options(selectinload(Payment.customer))
        .where(
            Payment.organization_id == organization_id,
            Payment.status == PaymentStatus.FAILED,
            Payment.created_at >= now - timedelta(days=30),
        )
        .order_by(Payment.created_at.desc())
    ).all()
    for pay in failed_payments:
        created = iso_dt(pay.created_at) or now
        age = max(0, (now - created).days)
        items.append(
            {
                "id": f"failed_payment:{pay.id}",
                "category": "failed_payment",
                "title": f"Payment {pay.payment_number} failed",
                "description": pay.failure_reason or "The gateway did not capture this payment.",
                "amount": money_str(pay.amount),
                "customer": customer_ref(pay.customer),
                "entity_type": "payment",
                "entity_id": pay.id,
                "due_info": "Failed today" if age == 0 else f"Failed {age} day{'s' if age != 1 else ''} ago",
                "urgency": "high",
                "suggested_action": "retry_payment",
            }
        )

    trials = db.scalars(
        select(Subscription)
        .options(selectinload(Subscription.customer), selectinload(Subscription.plan))
        .where(
            Subscription.organization_id == organization_id,
            Subscription.status == SubscriptionStatus.TRIALING,
            Subscription.trial_end.is_not(None),
            Subscription.trial_end <= today + timedelta(days=7),
        )
        .order_by(Subscription.trial_end.asc())
    ).all()
    for sub in trials:
        days_left = (sub.trial_end - today).days
        items.append(
            {
                "id": f"expiring_trial:{sub.id}",
                "category": "expiring_trial",
                "title": f"Trial ending for {sub.customer.display_name}",
                "description": f"{sub.plan.name} trial ends on {sub.trial_end.isoformat()}.",
                "amount": None,
                "customer": customer_ref(sub.customer),
                "entity_type": "subscription",
                "entity_id": sub.id,
                "due_info": "Ends today" if days_left <= 0 else f"Ends in {days_left} day{'s' if days_left != 1 else ''}",
                "urgency": "high" if days_left <= 2 else "medium",
                "suggested_action": "convert_trial",
            }
        )

    stale_cutoff = now - timedelta(days=3)
    quotes = db.scalars(
        select(Quote)
        .options(selectinload(Quote.customer))
        .where(
            Quote.organization_id == organization_id,
            Quote.status == QuoteStatus.SENT,
            or_(
                Quote.sent_at <= stale_cutoff,
                and_(Quote.expiry_date.is_not(None), Quote.expiry_date <= today + timedelta(days=3)),
            ),
        )
        .order_by(Quote.sent_at.asc())
    ).all()
    for quote in quotes:
        if quote.expiry_date and quote.expiry_date <= today + timedelta(days=3):
            left = (quote.expiry_date - today).days
            due_info = "Expired" if left < 0 else ("Expires today" if left == 0 else f"Expires in {left} day{'s' if left != 1 else ''}")
        else:
            sent = iso_dt(quote.sent_at) or now
            due_info = f"Sent {max(0, (now - sent).days)} days ago, no response"
        items.append(
            {
                "id": f"pending_quote:{quote.id}",
                "category": "pending_quote",
                "title": f"Quote {quote.quote_number} awaiting response",
                "description": f"{quote.customer.display_name}: {quote.title or 'quote'} for {quote.currency} {q2(quote.total):,.2f}.",
                "amount": money_str(quote.total),
                "customer": customer_ref(quote.customer),
                "entity_type": "quote",
                "entity_id": quote.id,
                "due_info": due_info,
                "urgency": "medium",
                "suggested_action": "review_quote",
            }
        )

    approvals = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.organization_id == organization_id, ApprovalRequest.status == ApprovalStatus.PENDING)
        .order_by(ApprovalRequest.created_at.asc())
    ).all()
    for approval in approvals:
        created = iso_dt(approval.created_at) or now
        age = max(0, (now - created).days)
        payload = approval.payload or {}
        amount = payload.get("amount") or payload.get("total")
        items.append(
            {
                "id": f"pending_approval:{approval.id}",
                "category": "pending_approval",
                "title": approval.title,
                "description": approval.justification or f"{approval.type.value.replace('_', ' ').title()} request awaiting review.",
                "amount": money_str(amount) if amount not in (None, "") else None,
                "customer": None,
                "entity_type": approval.entity_type,
                "entity_id": approval.entity_id,
                "due_info": "Requested today" if age == 0 else f"Waiting {age} day{'s' if age != 1 else ''}",
                "urgency": "high" if age >= 3 else "medium",
                "suggested_action": "review_approval",
            }
        )

    items.sort(key=lambda i: (URGENCY_RANK[i["urgency"]], -D(i["amount"] or 0)))
    counts = {key: 0 for key in ("overdue", "failed_payment", "expiring_trial", "pending_quote", "pending_approval")}
    for item in items:
        counts[item["category"]] += 1
    return {"items": items, "counts": counts}


# --- calendar -----------------------------------------------------------------------------------------------------------------


def parse_month(month: Optional[str], today: Optional[date] = None) -> Tuple[date, date]:
    if not month:
        first = (today or timezones.utc_today()).replace(day=1)
    else:
        try:
            year, mon = month.split("-")
            first = date(int(year), int(mon), 1)
        except (ValueError, AttributeError):
            raise ValidationAppError("month must be YYYY-MM.", {"fields": {"month": "expected YYYY-MM"}})
    last = add_months(first, 1) - timedelta(days=1)
    return first, last


def calendar_events(db: Session, organization_id: str, month: Optional[str]) -> Dict[str, Any]:
    first, last = parse_month(month, timezones.org_today_for_id(db, organization_id))
    events: List[Dict[str, Any]] = []

    for inv in db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .where(Invoice.organization_id == organization_id, Invoice.status.in_(list(OPEN_INVOICE_STATUSES)), Invoice.due_date >= first, Invoice.due_date <= last)
        .order_by(Invoice.due_date)
    ).all():
        events.append(
            {
                "id": f"invoice_due:{inv.id}",
                "date": inv.due_date,
                "type": "invoice_due",
                "title": f"{inv.invoice_number} due - {inv.customer.display_name}",
                "customer": customer_ref(inv.customer),
                "amount": money_str(inv.amount_due),
                "entity_type": "invoice",
                "entity_id": inv.id,
                "status": inv.status.value,
            }
        )

    for sub in db.scalars(
        select(Subscription)
        .options(selectinload(Subscription.customer), selectinload(Subscription.plan))
        .where(
            Subscription.organization_id == organization_id,
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE]),
            Subscription.next_billing_date >= first,
            Subscription.next_billing_date <= last,
        )
        .order_by(Subscription.next_billing_date)
    ).all():
        events.append(
            {
                "id": f"subscription_renewal:{sub.id}",
                "date": sub.next_billing_date,
                "type": "subscription_renewal",
                "title": f"{sub.plan.name} renews - {sub.customer.display_name}",
                "customer": customer_ref(sub.customer),
                "amount": money_str(D(sub.plan.unit_amount) * (sub.quantity if sub.plan.pricing_model == PricingModel.PER_UNIT else 1)),
                "entity_type": "subscription",
                "entity_id": sub.id,
                "status": sub.status.value,
            }
        )

    for sub in db.scalars(
        select(Subscription)
        .options(selectinload(Subscription.customer), selectinload(Subscription.plan))
        .where(
            Subscription.organization_id == organization_id,
            Subscription.status == SubscriptionStatus.TRIALING,
            Subscription.trial_end >= first,
            Subscription.trial_end <= last,
        )
        .order_by(Subscription.trial_end)
    ).all():
        events.append(
            {
                "id": f"trial_ending:{sub.id}",
                "date": sub.trial_end,
                "type": "trial_ending",
                "title": f"Trial ends - {sub.customer.display_name} ({sub.plan.name})",
                "customer": customer_ref(sub.customer),
                "amount": None,
                "entity_type": "subscription",
                "entity_id": sub.id,
                "status": sub.status.value,
            }
        )

    for quote in db.scalars(
        select(Quote)
        .options(selectinload(Quote.customer))
        .where(Quote.organization_id == organization_id, Quote.status == QuoteStatus.SENT, Quote.expiry_date >= first, Quote.expiry_date <= last)
        .order_by(Quote.expiry_date)
    ).all():
        events.append(
            {
                "id": f"quote_expiry:{quote.id}",
                "date": quote.expiry_date,
                "type": "quote_expiry",
                "title": f"{quote.quote_number} expires - {quote.customer.display_name}",
                "customer": customer_ref(quote.customer),
                "amount": money_str(quote.total),
                "entity_type": "quote",
                "entity_id": quote.id,
                "status": quote.status.value,
            }
        )

    events.sort(key=lambda e: (e["date"], e["type"]))
    return {"month": first.strftime("%Y-%m"), "events": events}


__all__ = ["dashboard_summary", "action_center", "calendar_events", "list_activity", "activity_item", "resolve_range"]

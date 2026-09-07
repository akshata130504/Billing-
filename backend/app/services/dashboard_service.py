"""Control-center read models (contract §10): dashboard summary, action center, calendar, activity.

Everything is computed with SQL aggregates scoped to the organization; the only
Python loops are over the small "recent" lists.

Documented approximations
- revenue = Σ (amount - amount_refunded) of settled payments by paid_at.
- pipeline amounts: draft/paid use `total`, open buckets use `amount_due`.
- mrr_change_pct compares today's MRR with the MRR of subscriptions that existed at
  the start of the previous month (created_at before it and not cancelled before it).
- recovery.recovered_amount = settled payments in range from customers who also
  had a failed payment in the range (failed gateway attempts carry no allocation).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.exceptions import ValidationAppError
from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    ApprovalRequest,
    ApprovalStatus,
    AuditLog,
    AuditStatus,
    BillingInterval,
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
from backend.app.services.subscription_service import add_months

RANGE_KEYS = ("today", "7_days", "30_days", "3_months", "12_months")


# --- helpers ---------------------------------------------------------------------------------------


def _dt(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _bounds(start: date, end: date) -> Tuple[datetime, datetime]:
    """[start 00:00, end+1 00:00) in UTC."""
    return _dt(start), _dt(end + timedelta(days=1))


def _dec(value) -> Decimal:
    return q2(D(value if value is not None else 0))


def _pct_change(current: Decimal, previous: Decimal) -> Optional[str]:
    if previous is None or previous == 0:
        return None
    return money_str((current - previous) / previous * 100)


def resolve_range(range_key: str, today: Optional[date] = None) -> Tuple[date, date, date, date]:
    """Return (start, end, prev_start, prev_end) for a dashboard range."""
    today = today or date.today()
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


def _revenue_between(db: Session, org_id: str, start: date, end: date) -> Decimal:
    lo, hi = _bounds(start, end)
    value = db.scalar(
        select(func.coalesce(func.sum(Payment.amount - Payment.amount_refunded), 0)).where(
            Payment.organization_id == org_id,
            Payment.status.in_(SETTLED_PAYMENT_STATUSES),
            Payment.paid_at >= lo,
            Payment.paid_at < hi,
        )
    )
    return _dec(value)


def _invoiced_between(db: Session, org_id: str, start: date, end: date) -> Decimal:
    lo, hi = _bounds(start, end)
    value = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.organization_id == org_id,
            Invoice.status != InvoiceStatus.VOID,
            Invoice.sent_at >= lo,
            Invoice.sent_at < hi,
        )
    )
    return _dec(value)


def _mrr(db: Session, org_id: str, *extra_filters) -> Decimal:
    """Σ recurring amount grouped by months-per-period, divided in Python (exact Decimal; no SQL division)."""
    months = case(
        (Plan.billing_interval == BillingInterval.MONTHLY, 1),
        (Plan.billing_interval == BillingInterval.QUARTERLY, 3),
        (Plan.billing_interval == BillingInterval.SEMIANNUAL, 6),
        (Plan.billing_interval == BillingInterval.YEARLY, 12),
        else_=0,
    ) * case((Plan.interval_count > 0, Plan.interval_count), else_=1)
    units = case((Plan.pricing_model == PricingModel.PER_UNIT, Subscription.quantity), else_=1)
    rows = db.execute(
        select(months, func.coalesce(func.sum(Plan.unit_amount * units), 0))
        .select_from(Subscription)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(Subscription.organization_id == org_id, months > 0, *extra_filters)
        .group_by(months)
    ).all()
    total = Decimal("0")
    for period_months, amount in rows:
        if period_months:
            total += D(amount) / Decimal(int(period_months))
    return q2(total)


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
    today = date.today()
    start, end, prev_start, prev_end = resolve_range(range_key, today)
    lo, hi = _bounds(start, end)
    now = datetime.now(timezone.utc)

    # --- metrics
    revenue = _revenue_between(db, org_id, start, end)
    prev_revenue = _revenue_between(db, org_id, prev_start, prev_end)
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
    mrr = _mrr(db, org_id, Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE]))
    prev_month_start = _dt(add_months(today.replace(day=1), -1))
    prev_mrr = _mrr(
        db,
        org_id,
        Subscription.created_at < prev_month_start,
        or_(Subscription.cancelled_at.is_(None), Subscription.cancelled_at >= prev_month_start),
        Subscription.status != SubscriptionStatus.TRIALING,
    )
    trend: List[Dict[str, Any]] = []
    first_of_month = today.replace(day=1)
    for offset in range(11, -1, -1):
        month_start = add_months(first_of_month, -offset)
        month_end = add_months(month_start, 1) - timedelta(days=1)
        trend.append(
            {
                "label": _month_label(month_start),
                "period_start": month_start,
                "revenue": money_str(_revenue_between(db, org_id, month_start, month_end)),
                "invoiced": money_str(_invoiced_between(db, org_id, month_start, month_end)),
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
            "trend": trend,
        },
        "pipeline": pipeline,
        "customer_health": {
            "active": health["active"],
            "trialing": health["trialing"],
            "past_due": health["past_due"],
            "paused": health["paused"],
            "cancelled_this_period": int(cancelled_this_period or 0),
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
    return {
        "id": row.id,
        "title": humanize_action(row.action),
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
    today = date.today()
    now = datetime.now(timezone.utc)
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


def parse_month(month: Optional[str]) -> Tuple[date, date]:
    if not month:
        first = date.today().replace(day=1)
    else:
        try:
            year, mon = month.split("-")
            first = date(int(year), int(mon), 1)
        except (ValueError, AttributeError):
            raise ValidationAppError("month must be YYYY-MM.", {"fields": {"month": "expected YYYY-MM"}})
    last = add_months(first, 1) - timedelta(days=1)
    return first, last


def calendar_events(db: Session, organization_id: str, month: Optional[str]) -> Dict[str, Any]:
    first, last = parse_month(month)
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

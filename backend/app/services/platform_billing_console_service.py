"""Read-only views of Rooman's OWN plan billing for the platform console (api/v1/endpoints/platform_billing.py).

Everything here is the application's stored state - platform_subscriptions, platform_checkout_attempts and the
platform webhook ledger - never a Razorpay call and never a tenant's payments (those live in other tables and are
not read here). Nothing is changed: no approve, retry, replay or cancel.

Shown: organization id and name (directory metadata), plan, amounts and periods, statuses, Razorpay object ids,
and short failure / outcome summaries the application wrote itself. Never shown: keys, secrets, signatures,
webhook payloads (the ledger never stores them), customer contact details or card / bank data.

Review queue: every finding that must not be applied automatically - from the Checkout callback
(PAYMENT_NEEDS_REVIEW), a signed webhook or the scheduled reconciliation - is persisted on the checkout attempt by
platform_payment_service._review (review_reason = latest finding, review_flagged_at = first flagged; migration 0041).
The queue lists those attempts, webhook ledger `needs_review` rows whose subscription has no flagged attempt (e.g.
rows recorded before 0041), and attempts whose stored state needs attention: `unknown` (Razorpay's answer to the
create call was lost) and `authorized` for longer than STUCK_AUTHORIZED_AFTER.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from backend.app.core.plan_catalog import catalog
from backend.app.models import Organization, PlatformCheckoutAttempt, PlatformSubscription, PlatformWebhookEvent
from backend.app.models import PlatformSubscriptionState as S
from backend.app.services import platform_subscription_service as subs

MAX_PAGE_SIZE = 100
STUCK_AUTHORIZED_AFTER = timedelta(hours=24)

# Subscription filters: stored state, plus "cancellation_scheduled" (active with cancel_at_period_end) and "paid"
# (the default: every plan row that is not a trial).
SUBSCRIPTION_FILTERS = ("paid", "active", "cancellation_scheduled", "past_due", "cancelled", "expired", "trialing", "all")
CHECKOUT_FILTERS = ("open", "created", "pending", "unknown", "authorized", "completed", "failed", "expired", "all")
WEBHOOK_FILTERS = ("processed", "ignored", "needs_review", "all")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def page_meta(total: int, page: int, page_size: int) -> Dict[str, int]:
    return {"total": total, "page": page, "page_size": page_size,
            "total_pages": max(1, math.ceil(total / page_size)) if total else 0}


def _paged(db: Session, stmt, count_stmt, page: int, page_size: int):
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    total = int(db.scalar(count_stmt) or 0)
    rows = db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).all()
    return rows, total, page_size


def _plan_name(code: Optional[str]) -> Optional[str]:
    plan = catalog().plan(code) if code else None
    return plan.name if plan else None


def _is_sandbox(code: Optional[str]) -> bool:
    plan = catalog().plan(code) if code else None
    return bool(plan and plan.is_sandbox)


def _org_ids(db: Session, organization_query: Optional[str]) -> Optional[List[str]]:
    """Organizations whose id equals, or whose name contains, the query (None: no filter)."""
    if not organization_query:
        return None
    q = organization_query.strip()
    return list(db.scalars(select(Organization.id).where(or_(
        Organization.id == q, func.lower(Organization.name).contains(q.lower())))))


# --- subscriptions ------------------------------------------------------------------------------------------


def list_subscriptions(db: Session, *, status: str = "paid", organization: Optional[str] = None, page: int = 1,
                       page_size: int = 25, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = _aware(now) or _utcnow()
    # The checkout that started this Razorpay subscription carries the amount actually charged.
    attempt = PlatformCheckoutAttempt
    stmt = (select(PlatformSubscription, Organization.name, attempt.amount_minor, attempt.currency)
            .join(Organization, Organization.id == PlatformSubscription.organization_id)
            .outerjoin(attempt, and_(attempt.provider_subscription_id == PlatformSubscription.provider_subscription_id,
                                     PlatformSubscription.provider_subscription_id.isnot(None))))
    conditions = []
    if status == "paid":
        conditions.append(PlatformSubscription.state != S.TRIALING.value)
    elif status == "cancellation_scheduled":
        conditions += [PlatformSubscription.state == S.ACTIVE.value, PlatformSubscription.cancel_at_period_end.is_(True)]
    elif status == "active":
        conditions += [PlatformSubscription.state == S.ACTIVE.value, PlatformSubscription.cancel_at_period_end.isnot(True)]
    elif status != "all":
        conditions.append(PlatformSubscription.state == status)
    ids = _org_ids(db, organization)
    if ids is not None:
        conditions.append(PlatformSubscription.organization_id.in_(ids or [""]))
    stmt = stmt.where(*conditions).order_by(PlatformSubscription.updated_at.desc(), PlatformSubscription.id)
    count = select(func.count()).select_from(PlatformSubscription).where(*conditions)
    rows, total, page_size = _paged(db, stmt, count, page, page_size)

    items = []
    for sub, org_name, amount_minor, currency in rows:
        access = subs.evaluate(sub, now)
        items.append({
            "organization_id": sub.organization_id, "organization_name": org_name,
            "plan_code": sub.plan_code, "plan_name": _plan_name(sub.plan_code), "sandbox": _is_sandbox(sub.plan_code),
            "state": sub.state, "effective_state": access.state, "writable": access.writable,
            "cancel_at_period_end": bool(sub.cancel_at_period_end),
            "billing_interval": sub.billing_interval, "billing_interval_count": sub.billing_interval_count,
            "current_period_start": _aware(sub.current_period_start), "current_period_end": _aware(sub.current_period_end),
            "grace_period_end": _aware(sub.grace_period_end), "cancelled_at": _aware(sub.cancelled_at),
            "trial_ends_at": _aware(sub.trial_ends_at),
            "amount_minor": amount_minor, "currency": currency,
            "provider_subscription_id": sub.provider_subscription_id, "provider_mode": sub.provider_mode,
            "provider_paid_count": sub.provider_paid_count, "updated_at": _aware(sub.updated_at),
        })
    return {"items": items, **page_meta(total, page, page_size)}


# --- checkout attempts ----------------------------------------------------------------------------------------


def _flagged_subscription_ids(db: Session, subscription_ids: List[str]) -> set:
    ids = [s for s in subscription_ids if s]
    if not ids:
        return set()
    return set(db.scalars(select(PlatformWebhookEvent.provider_subscription_id).where(
        PlatformWebhookEvent.status == "needs_review", PlatformWebhookEvent.provider_subscription_id.in_(ids))))


def _attempt_item(a: PlatformCheckoutAttempt, org_name: Optional[str], flagged: set, now: datetime) -> Dict[str, Any]:
    authorized_at = _aware(a.authorized_at)
    return {
        "id": a.id, "organization_id": a.organization_id, "organization_name": org_name,
        "plan_code": a.plan_code, "plan_name": _plan_name(a.plan_code), "sandbox": _is_sandbox(a.plan_code),
        "amount_minor": a.amount_minor, "currency": a.currency, "billing_interval": a.billing_interval,
        "billing_interval_count": a.billing_interval_count, "seat_limit": a.seat_limit, "mode": a.mode,
        "status": a.status, "provider_subscription_id": a.provider_subscription_id,
        "provider_payment_id": a.provider_payment_id, "created_at": _aware(a.created_at),
        "expires_at": _aware(a.expires_at), "authorized_at": authorized_at, "completed_at": _aware(a.completed_at),
        "last_error": (a.last_error or None) and a.last_error[:200],
        "webhook_review": bool(a.provider_subscription_id and a.provider_subscription_id in flagged),
        "review_reason": a.review_reason, "review_flagged_at": _aware(a.review_flagged_at),
        "stuck": a.status == "unknown" or (a.status == "authorized" and authorized_at is not None
                                           and now - authorized_at >= STUCK_AUTHORIZED_AFTER),
    }


def list_checkout_attempts(db: Session, *, status: str = "all", mode: Optional[str] = None,
                           organization: Optional[str] = None, page: int = 1, page_size: int = 25,
                           now: Optional[datetime] = None) -> Dict[str, Any]:
    from backend.app.models.platform_billing import OPEN_CHECKOUT_STATUSES

    now = _aware(now) or _utcnow()
    conditions = []
    if status == "open":
        conditions.append(PlatformCheckoutAttempt.status.in_(OPEN_CHECKOUT_STATUSES))
    elif status != "all":
        conditions.append(PlatformCheckoutAttempt.status == status)
    if mode:
        conditions.append(PlatformCheckoutAttempt.mode == mode)
    ids = _org_ids(db, organization)
    if ids is not None:
        conditions.append(PlatformCheckoutAttempt.organization_id.in_(ids or [""]))
    stmt = (select(PlatformCheckoutAttempt, Organization.name)
            .outerjoin(Organization, Organization.id == PlatformCheckoutAttempt.organization_id)
            .where(*conditions).order_by(PlatformCheckoutAttempt.created_at.desc(), PlatformCheckoutAttempt.id))
    count = select(func.count()).select_from(PlatformCheckoutAttempt).where(*conditions)
    rows, total, page_size = _paged(db, stmt, count, page, page_size)
    flagged = _flagged_subscription_ids(db, [a.provider_subscription_id for a, _ in rows])
    return {"items": [_attempt_item(a, name, flagged, now) for a, name in rows], **page_meta(total, page, page_size)}


# --- webhook ledger --------------------------------------------------------------------------------------------


def _event_item(e: PlatformWebhookEvent, org_name: Optional[str]) -> Dict[str, Any]:
    return {
        "id": e.id, "event_id": e.event_id, "event_type": e.event_type, "mode": e.mode, "status": e.status,
        "outcome": e.outcome, "provider_subscription_id": e.provider_subscription_id,
        "provider_payment_id": e.provider_payment_id, "organization_id": e.organization_id,
        "organization_name": org_name, "event_created_at": _aware(e.event_created_at),
        "received_at": _aware(e.received_at),
    }


def list_webhook_events(db: Session, *, status: str = "all", event_type: Optional[str] = None,
                        organization: Optional[str] = None, page: int = 1, page_size: int = 25) -> Dict[str, Any]:
    conditions = []
    if status != "all":
        conditions.append(PlatformWebhookEvent.status == status)
    if event_type:
        conditions.append(PlatformWebhookEvent.event_type == event_type)
    ids = _org_ids(db, organization)
    if ids is not None:
        conditions.append(PlatformWebhookEvent.organization_id.in_(ids or [""]))
    stmt = (select(PlatformWebhookEvent, Organization.name)
            .outerjoin(Organization, Organization.id == PlatformWebhookEvent.organization_id)
            .where(*conditions).order_by(PlatformWebhookEvent.received_at.desc(), PlatformWebhookEvent.id))
    count = select(func.count()).select_from(PlatformWebhookEvent).where(*conditions)
    rows, total, page_size = _paged(db, stmt, count, page, page_size)
    return {"items": [_event_item(e, name) for e, name in rows], **page_meta(total, page, page_size)}


# --- review queue -----------------------------------------------------------------------------------------------


REVIEW_SOURCES = {
    "checkout_review": "A payment for this checkout could not be applied automatically (callback, webhook or reconciliation).",
    "webhook_needs_review": "A signed webhook could not be applied automatically (webhook ledger).",
    "checkout_unknown": "Razorpay's answer to creating this checkout was lost; it is reconciled on the next checkout.",
    "checkout_authorized_stuck": "Razorpay holds the customer's authorization but the first charge was never confirmed.",
}
REVIEW_FILTERS = ("open", "resolved", "all")


def review_queue(db: Session, *, status: str = "open", organization: Optional[str] = None, page: int = 1,
                 page_size: int = 25, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Review work, newest first. `checkout_review` items are stored review CASES (migration 0043) and can be
    resolved; webhook ledger `needs_review` rows without a case and stuck checkouts are state-derived signals that
    clear themselves when the stored state changes (shown with the open items only). Read-only."""
    from backend.app.models import PlatformPaymentReview
    from backend.app.services.platform_review_service import case_fields

    now = _aware(now) or _utcnow()
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    ids = _org_ids(db, organization)

    def org_filter(column):
        return [column.in_(ids or [""])] if ids is not None else []

    case_query = (select(PlatformPaymentReview, Organization.name, PlatformCheckoutAttempt.status)
                  .outerjoin(Organization, Organization.id == PlatformPaymentReview.organization_id)
                  .outerjoin(PlatformCheckoutAttempt, PlatformCheckoutAttempt.id == PlatformPaymentReview.checkout_attempt_id)
                  .where(*org_filter(PlatformPaymentReview.organization_id)))
    if status in ("open", "resolved"):
        case_query = case_query.where(PlatformPaymentReview.status == status)
    cases = db.execute(case_query).all()

    def base(source, detected, org_id, org_name, **kw) -> Dict[str, Any]:
        item = {"source": source, "explanation": REVIEW_SOURCES[source], "detected_at": detected,
                "organization_id": org_id, "organization_name": org_name, "case_id": None, "case_status": "open",
                "resolvable": False, "first_reason": None, "review_reason": None, "finding_count": None,
                "flagged_at": None, "last_seen_at": None, "resolution_category": None, "resolution_note": None,
                "resolution_ticket_ref": None, "resolved_at": None, "resolved_by_email": None,
                "resolved_by_role": None, "outcome": None, "event_type": None, "checkout_attempt_id": None,
                "checkout_status": None, "provider_subscription_id": None, "provider_payment_id": None, "mode": None}
        item.update(kw)
        return item

    items: List[Tuple[datetime, Dict[str, Any]]] = []
    for case, name, attempt_status in cases:
        fields = case_fields(case)
        sort_key = _aware(case.resolved_at) if case.status == "resolved" else _aware(case.last_seen_at)
        items.append((sort_key, base(
            "checkout_review", _aware(case.opened_at), case.organization_id, name, resolvable=case.status == "open",
            outcome=(case.latest_reason or "").split(":", 1)[0] or None, checkout_attempt_id=case.checkout_attempt_id,
            checkout_status=attempt_status, provider_subscription_id=case.provider_subscription_id, mode=case.mode,
            **fields)))

    if status in ("open", "all"):
        with_cases = set(db.scalars(select(PlatformPaymentReview.provider_subscription_id)
                                    .where(PlatformPaymentReview.provider_subscription_id.isnot(None))))
        events = [(e, name) for e, name in db.execute(
            select(PlatformWebhookEvent, Organization.name)
            .outerjoin(Organization, Organization.id == PlatformWebhookEvent.organization_id)
            .where(PlatformWebhookEvent.status == "needs_review", *org_filter(PlatformWebhookEvent.organization_id))).all()
            if e.provider_subscription_id not in with_cases]  # covered by the checkout's case
        open_attempts = set(db.scalars(select(PlatformPaymentReview.checkout_attempt_id)
                                       .where(PlatformPaymentReview.status == "open")))
        stuck = [(a, name) for a, name in db.execute(
            select(PlatformCheckoutAttempt, Organization.name)
            .outerjoin(Organization, Organization.id == PlatformCheckoutAttempt.organization_id)
            .where(*org_filter(PlatformCheckoutAttempt.organization_id),
                   or_(PlatformCheckoutAttempt.status == "unknown",
                       and_(PlatformCheckoutAttempt.status == "authorized",
                            PlatformCheckoutAttempt.authorized_at <= now - STUCK_AUTHORIZED_AFTER)))).all()
            if a.id not in open_attempts]
        for e, name in events:
            items.append((_aware(e.received_at), base(
                "webhook_needs_review", _aware(e.received_at), e.organization_id, name, outcome=e.outcome,
                event_type=e.event_type, provider_subscription_id=e.provider_subscription_id,
                provider_payment_id=e.provider_payment_id, mode=e.mode)))
        for a, name in stuck:
            source = "checkout_unknown" if a.status == "unknown" else "checkout_authorized_stuck"
            detected = _aware(a.authorized_at) if a.status == "authorized" else _aware(a.updated_at)
            items.append((detected, base(
                source, detected, a.organization_id, name, outcome=(a.last_error or a.status)[:200],
                checkout_attempt_id=a.id, checkout_status=a.status, provider_subscription_id=a.provider_subscription_id,
                provider_payment_id=a.provider_payment_id, mode=a.mode)))

    items.sort(key=lambda pair: pair[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    return {"items": [entry for _, entry in items[start:start + page_size]], **page_meta(total, page, page_size),
            "untracked_sources": []}


# --- email delivery (platform_notifications, migration 0044) ----------------------------------------------------


NOTIFICATION_STATUS_FILTERS = ("pending", "sent", "failed", "superseded", "all")

# The delivery job stores a short category in last_error (platform_notification_service._error_class), never a
# server reply or an exception message. Only these known codes are shown; anything else is reported as
# "unclassified" so an unexpected value can never leak through this view.
SAFE_ERROR_CODES = {
    "smtp_timeout": "The SMTP server did not answer in time",
    "smtp_unreachable": "The SMTP server could not be reached",
    "smtp_tls": "The secure (TLS) connection to the SMTP server failed",
    "smtp_auth": "The SMTP server refused Rooman's sign-in",
    "smtp_rejected": "The SMTP server rejected the recipient or the message",
    "smtp_error": "The SMTP server reported an error",
    "smtp_not_configured": "Outgoing email (SMTP) is not configured on the server",
    "no_longer_applicable": "Not sent: no longer true when its turn came",
    "superseded_by_later_event": "Not sent: replaced by a later lifecycle email",
}
UNCLASSIFIED_ERROR = ("unclassified", "An unexpected error occurred while sending")


def _safe_error(value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None
    if value in SAFE_ERROR_CODES:
        return value, SAFE_ERROR_CODES[value]
    return UNCLASSIFIED_ERROR  # includes error_<ExceptionName>: no exception details in the console


def mask_recipient(address: Optional[str]) -> Optional[str]:
    """A hint, not the address: the first character of the local part and the domain ("o***@example.test"). Enough
    to tell an organization's recipients apart and to spot a domain that rejects mail; the full address stays in the
    database for the delivery job only."""
    if not address or "@" not in address:
        return None
    local, _, domain = address.rpartition("@")
    return f"{local[:1]}***@{domain}" if local else f"***@{domain}"


def _notification_item(n, org_name: Optional[str]) -> Dict[str, Any]:
    error_code, error_label = _safe_error(n.last_error)
    retryable = n.status == "pending"
    return {
        "id": n.id, "kind": n.kind, "status": n.status, "attempts": int(n.attempts or 0),
        "organization_id": n.organization_id, "organization_name": org_name,
        "recipient_hint": mask_recipient(n.recipient),
        "created_at": _aware(n.created_at), "updated_at": _aware(n.updated_at), "sent_at": _aware(n.sent_at),
        "next_attempt_at": _aware(n.next_attempt_at) if retryable else None,
        "error_code": error_code, "error_label": error_label,
    }


def list_notifications(db: Session, *, status: str = "all", kind: Optional[str] = None,
                       organization: Optional[str] = None, page: int = 1, page_size: int = 25) -> Dict[str, Any]:
    """Rooman subscription lifecycle emails, newest activity first, one page at a time (LIMIT / OFFSET plus a COUNT,
    never the whole table). Selected columns only: the email subject and bodies and the full recipient address are
    not read. `status_counts` (one GROUP BY, same kind / organization filters) summarizes delivery health.
    `sent` means Rooman's SMTP server accepted the message - not that it reached or was read in an inbox."""
    from backend.app.models import PlatformNotification as N

    conditions = []
    if kind:
        conditions.append(N.kind == kind)
    ids = _org_ids(db, organization)
    if ids is not None:
        conditions.append(N.organization_id.in_(ids or [""]))
    status_conditions = conditions + ([N.status == status] if status != "all" else [])
    columns = (N.id, N.kind, N.status, N.attempts, N.organization_id, N.recipient, N.created_at, N.updated_at,
               N.sent_at, N.next_attempt_at, N.last_error)
    stmt = (select(*columns, Organization.name.label("organization_name"))
            .outerjoin(Organization, Organization.id == N.organization_id)
            .where(*status_conditions).order_by(N.updated_at.desc(), N.id))
    count = select(func.count()).select_from(N).where(*status_conditions)
    rows, total, page_size = _paged(db, stmt, count, page, page_size)
    counts = dict(db.execute(select(N.status, func.count()).where(*conditions).group_by(N.status)).all())
    return {
        "items": [_notification_item(row, row.organization_name) for row in rows],
        **page_meta(total, page, page_size),
        "status_counts": {s: int(counts.get(s, 0)) for s in NOTIFICATION_STATUS_FILTERS if s != "all"},
    }

"""Rooman subscription lifecycle emails (migration 0044, `platform_notifications`).

Queueing - always in the caller's transaction, flush only (the caller commits):
    subscription_activated     platform_payment_service._first_payment, after the verified first payment
    renewal_payment_received   platform_receipt_service.record_verified_payment, when it creates a NEW verified
                               renewal receipt (never from the paid-cycle count, an authorization, a pending / failed
                               payment or a mismatch: those create no receipt row)
    payment_past_due           platform_subscription_service.mark_past_due / settle (period ended unpaid)
    access_expired             settle: the grace period ended -> expired (read-only)
    cancellation_scheduled     schedule_cancellation (Owner, or Razorpay reporting the subscription cancelled)
    cancelled_immediately      cancel_now
    cancellation_effective     settle: a scheduled cancellation took effect at the period end

A rolled-back change takes its emails with it; nothing is sent before the commit. One row per (event, recipient):
UNIQUE (event_key, recipient) with INSERT ... ON CONFLICT DO NOTHING, so the callback, webhook and reconciliation
reporting the same event queue it once. Keys are namespaced "<kind>:<entity>:<id>[:<time>]" (a CHECK enforces the
kind prefix). A terminal email (expired / cancelled / ended) supersedes the same subscription's still-pending
past-due or scheduled-cancellation email, so one transition never produces two contradictory emails.

Recipients: the organization's active Owners plus its Billing email (Settings -> Organization), each address once.
Content: plan, dates (organization's time zone), the verified amount for payments, next steps and a link to
Settings -> Subscription (sign-in required; receipts there are for Owner / Admin / Finance). No Razorpay or payment
ids, payment-method details, webhook data or secrets. Receipts are never attached and never called tax invoices.

Delivery - `deliver_due` (scheduler job `platform_notifications`): one row at a time, locked FOR UPDATE SKIP LOCKED
while it is sent through Rooman's server SMTP settings (`send_email` without a tenant SMTP config - the same sender
as the trial emails). Just before sending it re-checks that the email is still true (`_still_applies`); if not the
row is `superseded`. SMTP failure: attempts + 1 and a backoff; after MAX_ATTEMPTS it is `failed`. Retrying re-sends the
stored email only - no payment, subscription or entitlement code runs here.

Terminal failure (`_record_terminal_failure` / `_alert_terminal_failure`): the pending -> failed change and an
append-only platform audit entry PLATFORM_NOTIFICATION_FAILED are committed together; only AFTER that commit one
operational alert is sent through core/alerts.send_alert (webhook when ALERT_WEBHOOK_URL is set; always an ERROR
log line, which Sentry also picks up when enabled). A failed row is never selected again, so the transition - and
its alert - happens once per notification however often the scheduler runs; the alert's dedup_key (notification id
+ attempts) also suppresses an in-process repeat. Alert and log carry the notification id, kind, organization id,
attempts and the allow-listed error category only - never the recipient, subject, bodies, SMTP settings or an
exception message. An unavailable alert service is logged and ignored: the row stays failed and the job goes on. Delivery is at least once:
a crash after the SMTP server accepted a message but before the row was committed can send that one email again.
"""
from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from backend.app.core.logging import logger
from backend.app.core.tenant_context import tenant_context
from backend.app.models import (
    MemberRole,
    Membership,
    MembershipStatus,
    Organization,
    PlatformNotification,
    PlatformSubscription,
    User,
)
from backend.app.models.base import new_uuid
from backend.app.models.platform_billing import PlatformSubscriptionState as S
from backend.app.services.email import EmailDeliveryError, frontend_url, send_email

SUBSCRIPTION_ACTIVATED = "subscription_activated"
RENEWAL_PAYMENT_RECEIVED = "renewal_payment_received"
PAYMENT_PAST_DUE = "payment_past_due"
ACCESS_EXPIRED = "access_expired"
CANCELLATION_SCHEDULED = "cancellation_scheduled"
CANCELLED_IMMEDIATELY = "cancelled_immediately"
CANCELLATION_EFFECTIVE = "cancellation_effective"

# Emails about something that is going to happen; a terminal email makes them obsolete.
PROVISIONAL_KINDS = (PAYMENT_PAST_DUE, CANCELLATION_SCHEDULED)
# Emails about something that happened: still true later, but not worth sending once this old.
FACT_MAX_AGE = timedelta(days=7)

MAX_ATTEMPTS = 8
BACKOFF_SECONDS = (60, 300, 900, 3600, 3 * 3600, 6 * 3600, 12 * 3600)
BATCH_SIZE = 50

SUBSCRIPTION_PATH = "settings/subscription"
RECEIPT_LINE = ("A payment receipt is available under Settings > Subscription for Owners, Admins and Finance members "
                "of your organization. It is a payment receipt, not a GST tax invoice.")
READ_ONLY_LINE = ("Your data stays safe and viewable, but changes are paused until a plan is active again.")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _iso(value: Optional[datetime]) -> str:
    value = _aware(value)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if value else "-"


# --- recipients and formatting ------------------------------------------------------------------------------


def recipients(db: Session, org: Organization) -> List[Tuple[str, Optional[str]]]:
    """(address, name) for the organization's active Owners and its Billing email; each address once
    (case-insensitive), lower-cased so the unique (event, recipient) key cannot be dodged by letter case."""
    with tenant_context(org.id):
        rows = db.execute(
            select(User.full_name, User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == org.id, Membership.status == MembershipStatus.ACTIVE,
                   Membership.role == MemberRole.OWNER)
            .order_by(User.email)
        ).all()
    found: Dict[str, Tuple[str, Optional[str]]] = {}
    for name, email in rows:
        address = (email or "").strip().lower()
        if address and address not in found:
            found[address] = (address, (name or "").strip() or None)
    billing = (org.email or "").strip().lower()
    if billing and billing not in found:
        found[billing] = (billing, None)
    return list(found.values())


def _zone(org: Organization):
    try:
        return ZoneInfo(org.timezone or "Asia/Kolkata")
    except Exception:  # noqa: BLE001 - unknown zone name or no zone data: UTC
        return timezone.utc


def _when(value: Optional[datetime], org: Organization) -> str:
    value = _aware(value)
    if value is None:
        return "-"
    local = value.astimezone(_zone(org))
    return local.strftime("%d %b %Y, %I:%M %p ") + (local.tzname() or "UTC")


def _money(amount_minor: Optional[int], currency: Optional[str]) -> str:
    value = (amount_minor or 0) / 100
    return f"₹{value:,.2f}" if (currency or "INR") == "INR" else f"{currency} {value:,.2f}"


def _plan_name(plan_code: Optional[str], snapshot: Optional[str] = None) -> str:
    if snapshot:
        return snapshot
    from backend.app.core.plan_catalog import catalog

    plan = catalog().plan(plan_code) if plan_code else None
    return plan.name if plan else (plan_code or "your")


def _compose(name: Optional[str], title: str, paragraphs: List[str], button: str, path: str) -> Tuple[str, str]:
    """(text, html) in the style of the trial emails. Paragraphs are plain text (escaped for HTML)."""
    from backend.app.services.platform_trial_service import _card

    link = frontend_url(path)
    hello = f"Hello {name}," if name else "Hello,"
    text = hello + "\n\n" + "\n\n".join(paragraphs) + f"\n\n{button}: {link}\n\n— Rooman Billing"
    page = _card(title, hello, [html.escape(p) for p in paragraphs], button, link)
    return text, page


Builder = Callable[[Optional[str]], Tuple[str, str, str]]


def _builder(subject: str, title: str, paragraphs: List[str], button: str = "View subscription",
             path: str = SUBSCRIPTION_PATH) -> Builder:
    def build(name: Optional[str]) -> Tuple[str, str, str]:
        text, page = _compose(name, title, paragraphs, button, path)
        return subject, text, page

    return build


# --- queueing (caller's transaction) ------------------------------------------------------------------------


def _insert(db: Session):
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert


def _queue(db: Session, *, kind: str, key: str, org: Organization, sub: Optional[PlatformSubscription],
           reference_at: Optional[datetime], build: Builder) -> int:
    """Queue one email per recipient (flush only). Returns how many rows were new; an event already queued for a
    recipient is skipped by the unique key (never an error that could abort the business transaction)."""
    if not key.startswith(kind + ":") or len(key) > 200:
        raise ValueError(f"notification key {key!r} is not namespaced by {kind!r}")
    to = recipients(db, org)
    if not to:
        logger.warning("Platform notification %s for organization %s: no Owner or Billing email", kind, org.id)
        return 0
    now, insert, queued = _utcnow(), _insert(db), 0
    for address, name in to:
        subject, text, page = build(name)
        stmt = insert(PlatformNotification).values(
            id=new_uuid(), organization_id=org.id, platform_subscription_id=sub.id if sub is not None else None,
            kind=kind, event_key=key, reference_at=_aware(reference_at), recipient=address[:255], subject=subject[:255],
            text_body=text, html_body=page, status="pending", attempts=0, next_attempt_at=None, last_error=None,
            sent_at=None, created_at=now, updated_at=now,
        ).on_conflict_do_nothing(index_elements=["event_key", "recipient"])
        queued += db.execute(stmt).rowcount or 0
    return queued


def _supersede_provisional(db: Session, sub: PlatformSubscription) -> None:
    db.execute(
        update(PlatformNotification)
        .where(PlatformNotification.platform_subscription_id == sub.id, PlatformNotification.status == "pending",
               PlatformNotification.kind.in_(PROVISIONAL_KINDS))
        .values(status="superseded", last_error="superseded_by_later_event", updated_at=_utcnow())
        .execution_options(synchronize_session=False)
    )


def subscription_activated(db: Session, attempt, sub: PlatformSubscription, receipt=None) -> int:
    """After the first payment was verified (captured, exact amount and currency) and the plan activated."""
    org = db.get(Organization, attempt.organization_id)
    plan = _plan_name(sub.plan_code, getattr(receipt, "plan_name", None))
    amount = _money(receipt.amount_minor if receipt is not None else attempt.amount_minor,
                    receipt.currency if receipt is not None else attempt.currency)
    lines = [f"We have received and verified your payment of {amount} for the {plan} plan of \"{org.name}\". "
             f"Your plan is active.",
             f"The current billing period ends on {_when(sub.current_period_end, org)}; the plan renews automatically "
             "through Razorpay.",
             RECEIPT_LINE]
    if attempt.mode == "test":
        lines.append("This was a Razorpay Test Mode payment: no real money was charged.")
    return _queue(db, kind=SUBSCRIPTION_ACTIVATED, key=f"{SUBSCRIPTION_ACTIVATED}:checkout:{attempt.id}", org=org,
                  sub=sub, reference_at=sub.current_period_start,
                  build=_builder(f"Payment confirmed - your Rooman Billing {plan} plan is active",
                                 f"Your {plan} plan is active", lines))


def renewal_payment_received(db: Session, payment) -> int:
    """A NEW verified renewal receipt (platform_payments row of kind 'renewal')."""
    org = db.get(Organization, payment.organization_id)
    sub = db.scalars(select(PlatformSubscription).where(PlatformSubscription.organization_id == org.id)).first()
    plan = _plan_name(payment.plan_code, payment.plan_name)
    lines = [f"We have received and verified your renewal payment of {_money(payment.amount_minor, payment.currency)} "
             f"for the {plan} plan of \"{org.name}\"."]
    if payment.period_start and payment.period_end:
        lines.append(f"It covers the billing period from {_when(payment.period_start, org)} to "
                     f"{_when(payment.period_end, org)}.")
    lines.append(RECEIPT_LINE)
    if payment.mode == "test":
        lines.append("This was a Razorpay Test Mode payment: no real money was charged.")
    return _queue(db, kind=RENEWAL_PAYMENT_RECEIVED, key=f"{RENEWAL_PAYMENT_RECEIVED}:payment:{payment.id}", org=org,
                  sub=sub, reference_at=payment.paid_at,
                  build=_builder(f"Payment received - your Rooman Billing {plan} plan has been renewed",
                                 "Renewal payment received", lines))


def payment_past_due(db: Session, org: Organization, sub: PlatformSubscription) -> int:
    """The renewal was not confirmed: access continues until grace_period_end. Never claims a payment failed or
    succeeded - only that it could not be confirmed."""
    plan, deadline = _plan_name(sub.plan_code), _when(sub.grace_period_end, org)
    lines = [f"We have not been able to confirm the renewal payment for the {plan} plan of \"{org.name}\".",
             f"Your organization keeps full access until {deadline}.",
             "Razorpay may retry the charge. Please make sure the payment method used for this subscription is valid "
             "and has sufficient funds. If the payment is confirmed, you do not need to do anything else.",
             f"If no payment is confirmed by {deadline}, your organization becomes read-only. {READ_ONLY_LINE}"]
    return _queue(db, kind=PAYMENT_PAST_DUE,
                  key=f"{PAYMENT_PAST_DUE}:subscription:{sub.id}:{_iso(sub.grace_period_end)}", org=org, sub=sub,
                  reference_at=sub.grace_period_end,
                  build=_builder("Action needed: we could not confirm your Rooman Billing renewal payment",
                                 "Renewal payment not confirmed", lines))


def access_expired(db: Session, org: Organization, sub: PlatformSubscription) -> int:
    """Grace ended without a confirmed payment: expired, read-only. (A scheduled cancellation never gets here: it
    ends as cancellation_effective, so the two cannot both be sent for one transition.)"""
    _supersede_provisional(db, sub)
    plan = _plan_name(sub.plan_code)
    lines = [f"The grace period for the {plan} plan of \"{org.name}\" ended on {_when(sub.grace_period_end, org)} "
             "without a confirmed payment, so the plan has expired and your organization is now read-only.",
             READ_ONLY_LINE,
             "To continue making changes, choose a plan in Settings > Subscription."]
    return _queue(db, kind=ACCESS_EXPIRED, key=f"{ACCESS_EXPIRED}:subscription:{sub.id}:{_iso(sub.grace_period_end)}",
                  org=org, sub=sub, reference_at=sub.grace_period_end,
                  build=_builder("Your Rooman Billing plan has expired - your organization is now read-only",
                                 "Your plan has expired", lines, button="View plans"))


def cancellation_scheduled(db: Session, org: Organization, sub: PlatformSubscription) -> int:
    plan, ends = _plan_name(sub.plan_code), _when(sub.current_period_end, org)
    lines = [f"The {plan} plan of \"{org.name}\" is scheduled to cancel at the end of its current billing period, "
             f"on {ends}. Your plan is still active today and nothing more will be charged.",
             f"You keep full access until {ends}. After that your organization becomes read-only. {READ_ONLY_LINE}"]
    return _queue(db, kind=CANCELLATION_SCHEDULED,
                  key=f"{CANCELLATION_SCHEDULED}:subscription:{sub.id}:{_iso(sub.current_period_end)}", org=org,
                  sub=sub, reference_at=sub.current_period_end,
                  build=_builder(f"Your Rooman Billing plan is scheduled to cancel on {ends}",
                                 "Cancellation scheduled", lines))


def cancelled_immediately(db: Session, org: Organization, sub: PlatformSubscription) -> int:
    _supersede_provisional(db, sub)
    plan = _plan_name(sub.plan_code)
    lines = [f"The {plan} plan of \"{org.name}\" was cancelled with immediate effect on "
             f"{_when(sub.cancelled_at, org)}. Your organization is now read-only.",
             READ_ONLY_LINE,
             "To continue making changes, choose a plan in Settings > Subscription."]
    return _queue(db, kind=CANCELLED_IMMEDIATELY,
                  key=f"{CANCELLED_IMMEDIATELY}:subscription:{sub.id}:{_iso(sub.cancelled_at)}", org=org, sub=sub,
                  reference_at=sub.cancelled_at,
                  build=_builder("Your Rooman Billing plan has been cancelled", "Plan cancelled", lines,
                                 button="View plans"))


def cancellation_effective(db: Session, org: Organization, sub: PlatformSubscription) -> int:
    _supersede_provisional(db, sub)
    plan = _plan_name(sub.plan_code)
    lines = [f"As scheduled, the {plan} plan of \"{org.name}\" ended on {_when(sub.cancelled_at, org)}. "
             "Your organization is now read-only.",
             READ_ONLY_LINE,
             "To continue making changes, choose a plan in Settings > Subscription."]
    return _queue(db, kind=CANCELLATION_EFFECTIVE,
                  key=f"{CANCELLATION_EFFECTIVE}:subscription:{sub.id}:{_iso(sub.cancelled_at)}", org=org, sub=sub,
                  reference_at=sub.cancelled_at,
                  build=_builder("Your Rooman Billing plan has ended as scheduled", "Your plan has ended", lines,
                                 button="View plans"))


# --- delivery (scheduler) -----------------------------------------------------------------------------------


def _same(a: Optional[datetime], b: Optional[datetime]) -> bool:
    a, b = _aware(a), _aware(b)
    return a is not None and b is not None and abs((a - b).total_seconds()) < 1


def _still_applies(db: Session, n: PlatformNotification, now: datetime) -> bool:
    """False when the email would no longer be true (or is too old to be useful) at send time."""
    if n.kind not in PROVISIONAL_KINDS and now - _aware(n.created_at) > FACT_MAX_AGE:
        return False
    if n.kind in (SUBSCRIPTION_ACTIVATED, RENEWAL_PAYMENT_RECEIVED):
        return True  # a verified payment stays verified
    sub = db.get(PlatformSubscription, n.platform_subscription_id) if n.platform_subscription_id else None
    if sub is None:
        return False
    ref = _aware(n.reference_at)
    if n.kind == PAYMENT_PAST_DUE:
        return sub.state == S.PAST_DUE.value and _same(sub.grace_period_end, ref) and now < ref
    if n.kind == ACCESS_EXPIRED:
        return sub.state == S.EXPIRED.value
    if n.kind == CANCELLATION_SCHEDULED:
        return (sub.state == S.ACTIVE.value and bool(sub.cancel_at_period_end)
                and _same(sub.current_period_end, ref) and now < ref)
    if n.kind in (CANCELLED_IMMEDIATELY, CANCELLATION_EFFECTIVE):
        return sub.state == S.CANCELLED.value and _same(sub.cancelled_at, ref)
    return False


def _error_class(exc: BaseException) -> str:
    if isinstance(exc, EmailDeliveryError):
        return f"smtp_{exc.reason}"[:120]  # the short category only, never the server's reply
    return f"error_{type(exc).__name__}"[:120]


def safe_error_category(value: Optional[str]) -> str:
    """The allow-listed error category of a stored last_error (shared with the console view), else unclassified."""
    from backend.app.services.platform_billing_console_service import SAFE_ERROR_CODES, UNCLASSIFIED_ERROR

    return value if value in SAFE_ERROR_CODES else UNCLASSIFIED_ERROR[0]


def _record_terminal_failure(db: Session, n: PlatformNotification) -> Dict[str, object]:
    """In the same transaction as status = failed: an append-only platform audit entry (it survives any later
    retry workflow). Returns the safe facts for the post-commit alert."""
    from backend.app.services import platform_audit

    facts = {"notification_id": n.id, "kind": n.kind, "organization_id": n.organization_id,
             "attempts": int(n.attempts or 0), "error_category": safe_error_category(n.last_error)}
    platform_audit.record(
        db, action=platform_audit.PLATFORM_NOTIFICATION_FAILED, result=platform_audit.FAILURE,
        organization=db.get(Organization, n.organization_id), target_type="platform_notification", target_id=n.id,
        details={k: v for k, v in facts.items() if k != "notification_id"},
    )
    return facts


def _alert_terminal_failure(facts: Dict[str, object]) -> None:
    """One operational alert per terminal failure (after commit). Never raises: if alerting is unavailable the safe
    facts are still in the log and the audit entry, and the scheduler carries on."""
    logger.error("Platform notification %s (%s) for organization %s failed after %s attempts: %s",
                 facts["notification_id"], facts["kind"], facts["organization_id"], facts["attempts"],
                 facts["error_category"])
    try:
        from backend.app.core import alerts

        alerts.send_alert(
            "platform_notification.failed",
            "A Rooman subscription email could not be delivered after all retries",
            dict(facts), severity="error",
            dedup_key=f"platform_notification.failed:{facts['notification_id']}:{facts['attempts']}",
        )
    except Exception as exc:  # noqa: BLE001 - alerting must never break delivery
        logger.warning("Platform notification %s: failure alert could not be sent (%s)", facts["notification_id"],
                       type(exc).__name__)


def deliver_due(db: Session, now: Optional[datetime] = None, limit: int = BATCH_SIZE) -> Dict[str, int]:
    """Send due pending emails, one locked row at a time; commit after each. Never raises for a row."""
    now = _aware(now) or _utcnow()
    counts: Counter = Counter()
    ids = db.scalars(
        select(PlatformNotification.id)
        .where(PlatformNotification.status == "pending",
               or_(PlatformNotification.next_attempt_at.is_(None), PlatformNotification.next_attempt_at <= now))
        .order_by(PlatformNotification.created_at, PlatformNotification.id)
        .limit(limit)
    ).all()
    db.rollback()
    for notification_id in ids:
        terminal = None
        try:
            n = db.execute(
                select(PlatformNotification)
                .where(PlatformNotification.id == notification_id, PlatformNotification.status == "pending")
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            due = _aware(n.next_attempt_at) if n is not None else None
            if n is None or (due is not None and due > now):
                db.rollback()  # sent, superseded or held by another worker meanwhile
                continue
            if not _still_applies(db, n, now):
                n.status, n.last_error, n.updated_at = "superseded", "no_longer_applicable", now
                db.commit()
                counts["superseded"] += 1
                continue
            error = None
            try:
                if not send_email(to=n.recipient, subject=n.subject, text_body=n.text_body, html_body=n.html_body):
                    error = "smtp_not_configured"
            except Exception as exc:  # noqa: BLE001 - every delivery problem is retried
                error = _error_class(exc)
            n.attempts = int(n.attempts or 0) + 1
            n.updated_at = now
            if error is None:
                n.status, n.sent_at, n.last_error, n.next_attempt_at = "sent", _utcnow(), None, None
                counts["sent"] += 1
            elif n.attempts >= MAX_ATTEMPTS:
                n.status, n.last_error, n.next_attempt_at = "failed", error, None
                terminal = _record_terminal_failure(db, n)
                counts["failed"] += 1
            else:
                n.last_error = error
                n.next_attempt_at = now + timedelta(seconds=BACKOFF_SECONDS[min(n.attempts, len(BACKOFF_SECONDS)) - 1])
                counts["retry_scheduled"] += 1
            db.commit()
            if terminal is not None:  # only once the failed state is committed
                _alert_terminal_failure(terminal)
                terminal = None
        except Exception:  # noqa: BLE001
            db.rollback()
            counts["errors"] += 1
            logger.exception("Platform notification %s could not be processed", notification_id)
    return dict(counts)


def run_delivery(db: Session, now: Optional[datetime] = None) -> Dict[str, int]:
    """Scheduler entry point: deliver due emails, record a heartbeat, log a summary when anything happened."""
    from backend.app.core.tenant_context import system_context
    from backend.app.services import scheduler

    with system_context():
        started_at = _utcnow()
        counts = deliver_due(db, now)
        scheduler._record_heartbeat(db, started_at=started_at, counts=counts, errors=counts.get("errors", 0),
                                    job_name=scheduler.PLATFORM_NOTIFY_JOB_NAME)
        if counts:
            logger.info("Platform notifications: %s", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        return counts

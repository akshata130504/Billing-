"""Scheduled reconciliation of Rooman plan checkouts and paid subscriptions with Razorpay.

Webhooks can arrive late or never, and the browser may close before the Checkout callback. This job makes
the lifecycle converge anyway by periodically re-reading Razorpay's AUTHORITATIVE state through the SAME
code the callback and the webhook use (`platform_payment_service.sync_provider_subscription`). Nothing in
this module decides that a payment is valid; it only chooses what to re-check:

1. Checkout attempts that may have been paid: 'created' and 'authorized' attempts, plus 'expired' ones
   for RECHECK_EXPIRED_WINDOW (the checkout service expires them locally without asking Razorpay, so a
   payment made at the last minute is still found). When no callback or webhook ever named the payment, its
   id is looked up from the subscription's paid invoice (`platform_razorpay.find_subscription_payment`);
   the shared sync then fetches that payment and activates ONLY with an active subscription, paid_count >= 1
   and a CAPTURED payment of exactly the checkout's amount and currency, for a plan still on sale on the
   checkout's terms. An authorization alone leaves the attempt 'authorized' (no access). An unpaid
   'created' attempt past its expiry is marked 'expired' (what the checkout service would do anyway).
2. Paid subscriptions (active / past_due) with a Razorpay subscription in the current key mode: the shared
   sync applies newly paid cycles by COUNT (`provider_paid_count`, so re-runs never extend twice),
   pending / halted -> past_due, cancelled / completed -> cancellation at period end or now.
3. `platform_subscription_service.settle` for every active / past_due subscription AFTER step 2, so a
   renewal Razorpay already charged is applied before time-based states (past_due, expired, cancelled)
   are recorded.

Safety:
- One item per transaction; each item takes the row locks the webhook takes (attempt, then organization /
  subscription), so a concurrent webhook and this job serialize instead of racing.
- Decisions use Razorpay's state read AFTER the attempt row is locked, applied by count / guarded
  transitions, so a re-run, a duplicate webhook or an out-of-order read never re-applies, resurrects a
  cancelled plan or overwrites newer state (stale Razorpay subscriptions are ignored by the shared sync).
- Only rows of the CURRENT key mode are read (test and live never mix); other-mode rows are counted, not touched.
- Razorpay unavailable / timeout -> that item is rolled back and retried on the next run. A 4xx from
  Razorpay, a mismatch or a payment that cannot be applied -> left as is and reported for review (the shared
  sync logs and alerts it); never approved automatically.
- One run at a time: APScheduler max_instances=1 plus a PostgreSQL advisory lock of its own (other
  processes skip). Each run records a heartbeat row `platform_reconciliation` with its counts.
- Logs carry ids, outcomes and counts only - never keys, secrets, signatures, emails or names.
- Rooman's account only (platform_razorpay); tenant payments and tenant Razorpay keys are never touched.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models import PlatformCheckoutAttempt, PlatformSubscription, PlatformSubscriptionState as S
from backend.app.services import (
    platform_payment_service as payments,
    platform_razorpay as provider,
    platform_subscription_service as subs,
    razorpay_gateway,
)

RECHECK_EXPIRED_WINDOW = timedelta(hours=48)
PAID_STATES = (S.ACTIVE.value, S.PAST_DUE.value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _key_mode() -> Optional[str]:
    """'test' / 'live' for Rooman's configured keys, or None when they are not configured."""
    if not razorpay_gateway.rooman_account_credentials().configured:
        return None
    return provider.mode()


# --- what to look at ------------------------------------------------------------------------------------


def checkout_candidates(db: Session, mode: str, now: datetime, limit: int) -> List[str]:
    stmt = (
        select(PlatformCheckoutAttempt.id)
        .where(PlatformCheckoutAttempt.mode == mode, PlatformCheckoutAttempt.provider_subscription_id.isnot(None))
        .where(or_(
            PlatformCheckoutAttempt.status.in_(("created", "authorized")),
            and_(PlatformCheckoutAttempt.status == "expired",
                 PlatformCheckoutAttempt.expires_at >= now - RECHECK_EXPIRED_WINDOW),
        ))
        .order_by(PlatformCheckoutAttempt.created_at)
        .limit(limit)
    )
    return list(db.scalars(stmt))


def subscription_candidates(db: Session, mode: str, limit: int) -> List[str]:
    stmt = (
        select(PlatformSubscription.organization_id)
        .where(PlatformSubscription.state.in_(PAID_STATES), PlatformSubscription.provider_subscription_id.isnot(None),
               PlatformSubscription.provider_mode == mode)
        .order_by(PlatformSubscription.current_period_end)
        .limit(limit)
    )
    return list(db.scalars(stmt))


def settle_candidates(db: Session, limit: int) -> List[str]:
    stmt = (
        select(PlatformSubscription.organization_id)
        .where(PlatformSubscription.state.in_(PAID_STATES))
        .order_by(PlatformSubscription.current_period_end)
        .limit(limit)
    )
    return list(db.scalars(stmt))


# --- one item each ---------------------------------------------------------------------------------------


def reconcile_checkout(db: Session, attempt_id: str, now: Optional[datetime] = None) -> str:
    """Re-check one checkout attempt with Razorpay. Commits; returns the outcome."""
    now = _aware(now) or _utcnow()
    attempt = db.get(PlatformCheckoutAttempt, attempt_id)
    if attempt is None or not attempt.provider_subscription_id:
        return "skipped"
    subscription_id = attempt.provider_subscription_id
    # Razorpay's paid invoice first: a payment id stored from an earlier callback may be a failed or
    # merely authorized payment that a later retry replaced. Either way the shared sync verifies it.
    try:
        payment_id = provider.find_subscription_payment(subscription_id) or attempt.provider_payment_id
    except provider.ProviderUnavailable as exc:
        raise payments.RetryLater(str(exc)) from exc
    result = payments.sync_provider_subscription(db, subscription_id, payment_id=payment_id, now=now)
    outcome = result.outcome
    # The shared sync locked and refreshed this same row. Unpaid and past its checkout window: expire it,
    # exactly as the checkout service does when the next checkout starts (a later payment is still found).
    if outcome == "not_paid" and attempt.status == "created" and now >= _aware(attempt.expires_at):
        attempt.status, attempt.last_error = "expired", "not paid before the checkout expired"
        outcome = "expired"
    db.commit()
    return outcome


def reconcile_subscription(db: Session, organization_id: str, now: Optional[datetime] = None) -> str:
    """Re-read the organization's current Razorpay subscription and apply it (renewals, failures, cancellation)."""
    sub = db.scalars(select(PlatformSubscription).where(PlatformSubscription.organization_id == organization_id)).first()
    if sub is None or not sub.provider_subscription_id:
        return "skipped"
    result = payments.sync_provider_subscription(db, sub.provider_subscription_id, now=_aware(now) or _utcnow())
    db.commit()
    return result.outcome


def settle_subscription(db: Session, organization_id: str, now: Optional[datetime] = None) -> str:
    sub = db.scalars(select(PlatformSubscription).where(PlatformSubscription.organization_id == organization_id)).first()
    before = sub.state if sub is not None else None
    sub = subs.settle(db, organization_id, now=_aware(now) or _utcnow())
    db.commit()
    after = sub.state if sub is not None else None
    return f"settled_{after}" if after != before else "no_change"


def _item(db: Session, counts: Counter, kind: str, item_id: str, fn: Callable[[], str]) -> None:
    try:
        outcome = fn()
    except payments.RetryLater:
        db.rollback()
        counts["retry_later"] += 1
        logger.warning("Platform reconciliation: %s %s deferred, Razorpay unavailable", kind, item_id)
        return
    except provider.ProviderRejected:
        db.rollback()
        counts["provider_rejected"] += 1
        logger.error("Platform reconciliation: Razorpay refused the lookup for %s %s; left for review", kind, item_id)
        return
    except Exception as exc:  # noqa: BLE001 - one bad row never stops the run
        db.rollback()
        counts["errors"] += 1
        logger.exception("Platform reconciliation: %s %s failed (%s)", kind, item_id, type(exc).__name__)
        _alert("platform.reconciliation_item_failed", {"kind": kind, "id": item_id, "error_type": type(exc).__name__},
               dedup_key=f"platform.reconciliation_item_failed:{kind}:{item_id}")
        return
    counts[f"{kind}_{outcome}"] += 1
    if outcome not in ("no_change", "not_paid", "pending", "skipped"):
        logger.info("Platform reconciliation: %s %s -> %s", kind, item_id, outcome)


def _alert(event: str, details: Dict[str, str], dedup_key: str) -> None:
    try:
        from backend.app.core.alerts import send_alert

        send_alert(event, "Rooman plan reconciliation needs attention", details, severity="error", dedup_key=dedup_key)
    except Exception:  # noqa: BLE001 - alerting never breaks the job
        logger.warning("Platform reconciliation: could not send alert %s", event)


# --- the run ----------------------------------------------------------------------------------------------


def reconcile(db: Session, now: Optional[datetime] = None) -> Dict[str, int]:
    """One reconciliation pass (no lock / heartbeat: see run_reconciliation). Returns counts by outcome."""
    now = _aware(now) or _utcnow()
    limit = int(settings.PLATFORM_RECONCILE_BATCH_SIZE)
    counts: Counter = Counter()
    try:
        mode = _key_mode()
    except Exception:  # noqa: BLE001 - e.g. malformed keys: nothing can be read, settle still runs
        mode = None
    if mode is None:
        counts["razorpay_not_configured"] += 1
    else:
        counts["other_mode_checkouts"] = db.query(PlatformCheckoutAttempt).filter(
            PlatformCheckoutAttempt.mode != mode, PlatformCheckoutAttempt.status.in_(("created", "authorized"))).count()
        for attempt_id in checkout_candidates(db, mode, now, limit):
            _item(db, counts, "checkout", attempt_id, lambda a=attempt_id: reconcile_checkout(db, a, now))
        for org_id in subscription_candidates(db, mode, limit):
            _item(db, counts, "subscription", org_id, lambda o=org_id: reconcile_subscription(db, o, now))
    for org_id in settle_candidates(db, limit):
        _item(db, counts, "settle", org_id, lambda o=org_id: settle_subscription(db, o, now))
    return {k: int(v) for k, v in counts.items() if v}


def run_reconciliation(db: Session, now: Optional[datetime] = None) -> Dict[str, int]:
    """The scheduled entry point: one run at a time (advisory lock), a heartbeat row and a summary log line."""
    from backend.app.core.tenant_context import system_context
    from backend.app.services import scheduler

    with system_context():
        started_at = _utcnow()
        acquired, lock_conn = scheduler._acquire_run_lock(db, scheduler.PLATFORM_RECONCILE_LOCK_KEY)
        if not acquired:
            logger.info("Platform reconciliation skipped: another run holds its lock")
            return {"skipped_locked": 1}
        try:
            counts = reconcile(db, now)
            errors = counts.get("errors", 0)
            scheduler._record_heartbeat(db, started_at=started_at, counts=counts, errors=errors,
                                        job_name=scheduler.PLATFORM_RECONCILE_JOB_NAME)
            logger.info("Platform reconciliation: %s", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing to do")
            return counts
        finally:
            scheduler._release_run_lock(lock_conn, scheduler.PLATFORM_RECONCILE_LOCK_KEY)

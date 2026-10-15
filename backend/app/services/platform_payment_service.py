"""Turn VERIFIED Razorpay subscription state into the organization's paid plan. The one place where a
payment for a Rooman plan changes access: the Checkout callback (api/v1/endpoints/subscription_checkout.py)
and the platform webhook (api/v1/endpoints/platform_webhooks.py) both call `sync_provider_subscription`.

Nothing the browser or an event says is trusted on its own. For the subscription named by an
authenticated callback or a signed event this module:
1. locks the checkout attempt that created that Razorpay Subscription (unknown -> nothing happens);
2. requires the attempt's mode to be the current mode of Rooman's keys (test and live never mix);
3. FETCHES the subscription (and the payment, when one is named) from Razorpay with Rooman's keys and
   checks it is ours: same provider plan, our checkout reference and organization in its notes, quantity 1;
4. decides from Razorpay's current state, not from the event name - so a duplicate or out-of-order event
   only re-applies the latest state, and paid cycles are applied by COUNT (`provider_paid_count`), once.

First payment (Razorpay docs: an immediate-start subscription stays `created` until the first charge
and is `active` after it; the authentication charge IS the first month's fee and is not refunded):
activation needs subscription `active` with `paid_count` >= 1 AND a `captured` payment for exactly the
attempt's amount and currency. A signature, an authorization, `authenticated`, or an `authorized` payment
is not enough: the attempt becomes 'authorized' and the organization stays read-only. Activation re-reads
the catalog: the plan must still be on sale (published, or a sandbox test plan while the sandbox is allowed -
Test Mode only) with the same billing terms as when checkout started; then
`platform_subscription_service.activate` grants exactly that plan's modules and seat limit.

Later events (attempt 'completed'): each newly paid cycle -> `renew`; `pending` / `halted` -> `mark_past_due`
(grace policy); `cancelled` / `completed` -> paid access continues to the end of the current period
(`schedule_cancellation`), or ends now when the renewal was never paid (`cancel_now`). A payment arriving
after access already ended, a changed plan, a suspended organization or any mismatch is NOT applied
automatically: it is reported for review. Refunds and proration are not decided here.

Flush only: the caller commits, so the attempt, the lifecycle change and the entitlements land together
or not at all. `RetryLater` means Razorpay could not be read; the caller rolls back and the work is redone
on the next callback / webhook retry.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import AppException, ConflictError
from backend.app.core.logging import logger
from backend.app.core.plan_catalog import catalog
from backend.app.models import PlatformCheckoutAttempt, PlatformSubscription, PlatformSubscriptionState as S
from backend.app.services import platform_razorpay as provider, platform_subscription_service as subs

# Outcomes. Processed: activated, pending, not_paid, renewed, past_due, cancellation_scheduled, cancelled,
# no_change. Ignored: unknown_subscription, stale_subscription. For review: mismatch, needs_review.
REVIEW_OUTCOMES = ("mismatch", "needs_review")
IGNORED_OUTCOMES = ("unknown_subscription", "stale_subscription")


class RetryLater(Exception):
    """Razorpay could not be read (timeout, 5xx). Roll back and retry; nothing was applied."""


@dataclass
class SyncResult:
    outcome: str
    organization_id: Optional[str] = None
    attempt_id: Optional[str] = None
    detail: str = ""

    @property
    def active(self) -> bool:
        return self.outcome in ("activated", "already_active", "renewed")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _from_unix(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _notes(entity: Dict[str, Any]) -> Dict[str, Any]:
    notes = entity.get("notes")
    return notes if isinstance(notes, dict) else {}


REVIEW_REASON_MAX = 300


def review_reason_text(outcome: str, detail: str) -> str:
    """The stored / displayed review reason: application text only, one line, bounded."""
    text = f"{outcome}: {detail}"
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    return " ".join(text.split())[:REVIEW_REASON_MAX]


def _review(attempt: PlatformCheckoutAttempt, outcome: str, detail: str) -> SyncResult:
    """Report a finding that must not be applied automatically. Persisted on the checkout attempt (the caller
    commits: the callback, the webhook and reconciliation all do), logged, and alerted. The LATEST reason is kept;
    the first flag time is never moved, so repeated runs do not reset it."""
    attempt.review_reason = review_reason_text(outcome, detail)
    if attempt.review_flagged_at is None:
        attempt.review_flagged_at = _utcnow()
    # The review case (migration 0043): updates the open case, or opens a new one after a resolution. The attempt
    # is always the caller's locked, session-bound row; the caller commits.
    from sqlalchemy.orm import object_session

    from backend.app.services import platform_review_service

    session = object_session(attempt)
    if session is not None:
        platform_review_service.record_finding(session, attempt, attempt.review_reason)
    logger.error("Platform payment for organization %s (checkout %s) needs review: %s",
                 attempt.organization_id, attempt.id, detail)
    try:
        from backend.app.core.alerts import send_alert

        send_alert("platform.payment_needs_review", "A Rooman plan payment needs review",
                   {"organization_id": attempt.organization_id, "checkout_attempt_id": attempt.id, "reason": detail},
                   severity="error", dedup_key=f"platform.payment_needs_review:{attempt.id}:{detail}")
    except Exception:  # noqa: BLE001 - alerting never blocks payment processing
        pass
    return SyncResult(outcome, attempt.organization_id, attempt.id, detail)


def _locked_attempt(db: Session, provider_subscription_id: str) -> Optional[PlatformCheckoutAttempt]:
    return db.scalars(
        select(PlatformCheckoutAttempt).where(PlatformCheckoutAttempt.provider_subscription_id == provider_subscription_id)
        .with_for_update().execution_options(populate_existing=True)
    ).first()


def sync_provider_subscription(db: Session, provider_subscription_id: str, *, payment_id: Optional[str] = None,
                               now: Optional[datetime] = None) -> SyncResult:
    """Apply Razorpay's current state of `provider_subscription_id` (see the module docstring)."""
    now = now or _utcnow()
    mode = provider.mode()  # Rooman's keys only; raises when they are not configured
    attempt = _locked_attempt(db, provider_subscription_id)
    if attempt is None:
        return SyncResult("unknown_subscription", detail="no checkout created this subscription")
    if attempt.mode != mode:
        return _review(attempt, "mismatch", f"checkout is {attempt.mode} mode, keys are {mode} mode")

    try:
        remote = provider.fetch_subscription(provider_subscription_id)
        payment = provider.fetch_payment(payment_id) if payment_id else None
    except provider.ProviderUnavailable as exc:
        raise RetryLater(str(exc)) from exc
    except provider.ProviderRejected:
        return _review(attempt, "mismatch", "Razorpay does not know this subscription or payment")

    notes = _notes(remote)
    if (remote.get("plan_id") != attempt.provider_plan_id
            or notes.get("checkout_attempt_id") != attempt.id
            or notes.get("organization_id") != attempt.organization_id
            or int(remote.get("quantity") or 1) != 1):
        return _review(attempt, "mismatch", "subscription does not belong to this checkout")

    if attempt.status != "completed":
        result = _first_payment(db, attempt, remote, payment, payment_id, mode, now)
    else:
        result = _later_events(db, attempt, remote, now)
    if attempt.status == "completed" and result.outcome not in REVIEW_OUTCOMES + IGNORED_OUTCOMES:
        _record_receipts(db, attempt, remote)
    return result


def _record_receipts(db: Session, attempt: PlatformCheckoutAttempt, remote: Dict[str, Any]) -> None:
    """Receipts for paid cycles not recorded yet (platform_receipt_service). Never blocks the lifecycle: if Razorpay
    cannot be read, the receipts wait for the next callback / webhook / reconciliation run."""
    from backend.app.services import platform_receipt_service as receipts

    try:
        problems = receipts.record_missing_cycles(db, attempt, remote)
    except (provider.ProviderUnavailable, provider.ProviderRejected) as exc:
        logger.warning("Receipts for checkout %s deferred: Razorpay %s", attempt.id, type(exc).__name__)
        return
    for problem in problems:
        _review(attempt, "needs_review", problem)


def _first_payment(db: Session, attempt: PlatformCheckoutAttempt, remote: Dict[str, Any],
                   payment: Optional[Dict[str, Any]], payment_id: Optional[str], mode: str, now: datetime) -> SyncResult:
    status = str(remote.get("status") or "")
    paid_count = int(remote.get("paid_count") or 0)
    captured = payment is not None and payment.get("status") == "captured"
    if captured and (int(payment.get("amount") or -1) != attempt.amount_minor
                     or str(payment.get("currency") or "").upper() != attempt.currency):
        return _review(attempt, "mismatch", "captured payment amount or currency differs from the checkout")

    if not (status == "active" and paid_count >= 1 and captured):
        if status in ("cancelled", "expired", "completed") and paid_count == 0:
            attempt.status, attempt.last_error = "failed", f"subscription {status} before any payment"
            db.flush()
            return SyncResult("not_paid", attempt.organization_id, attempt.id, f"subscription {status}")
        if status in ("cancelled", "completed") and paid_count >= 1:
            return _review(attempt, "needs_review", f"first cycle paid but subscription already {status}")
        # Razorpay holds the customer's authorization (or already charged) but the payment that proves the
        # first charge has not been verified here yet: wait for it, with no access.
        authorized = status in ("authenticated", "active") or (
            payment is not None and payment.get("status") in ("authorized", "captured"))
        if authorized and attempt.status != "authorized":
            attempt.status, attempt.authorized_at = "authorized", now
            if payment_id:
                attempt.provider_payment_id = payment_id
            db.flush()
        if not authorized and attempt.status != "authorized":
            return SyncResult("not_paid", attempt.organization_id, attempt.id, "no payment yet")
        return SyncResult("pending", attempt.organization_id, attempt.id, "first charge not confirmed yet")

    # Verified first payment. The purchase must still be what the catalog sells.
    from backend.app.services.platform_checkout_service import billing_fingerprint

    plan = catalog().plan(attempt.plan_code)
    if plan is None or not subs.plan_on_sale(plan) or billing_fingerprint(plan) != attempt.fingerprint:
        return _review(attempt, "needs_review", "plan is no longer sold on the terms of this checkout")
    if plan.is_sandbox and (attempt.mode != "test" or mode != "test"):
        # Unreachable through checkout (a sandbox plan is only ever sold in Test Mode); never activate one otherwise.
        return _review(attempt, "mismatch", "sandbox test plan outside Test Mode")
    start = _from_unix(remote.get("current_start")) or now
    try:
        sub = subs.activate(db, attempt.organization_id, plan.code, now=min(start, now))
    except ConflictError as exc:
        return _review(attempt, "needs_review", f"activation refused: {exc.details.get('code') or exc.message}")
    sub.provider_subscription_id, sub.provider_mode, sub.provider_paid_count = attempt.provider_subscription_id, mode, 1
    attempt.status, attempt.completed_at = "completed", now
    attempt.provider_payment_id = payment_id or attempt.provider_payment_id
    db.flush()
    # The receipt for the payment just verified (captured, exact amount and currency: checked above).
    from backend.app.services import platform_receipt_service as receipts

    receipt = receipts.record_verified_payment(db, attempt, payment, kind="initial", cycle_number=1,
                                               period_start=_from_unix(remote.get("current_start")),
                                               period_end=_from_unix(remote.get("current_end")))
    # Only here - after the first payment was verified and the plan activated - is "payment confirmed" emailed.
    from backend.app.services import platform_notification_service as notifications

    notifications.subscription_activated(db, attempt, sub, receipt)
    result = SyncResult("activated", attempt.organization_id, attempt.id)
    if paid_count > 1:  # processed late: later cycles were already paid
        later = _later_events(db, attempt, remote, now)
        if later.outcome in REVIEW_OUTCOMES:
            return later
    return result


def _locked_subscription(db: Session, organization_id: str) -> Optional[PlatformSubscription]:
    return db.scalars(
        select(PlatformSubscription).where(PlatformSubscription.organization_id == organization_id)
        .with_for_update().execution_options(populate_existing=True)
    ).first()


def _later_events(db: Session, attempt: PlatformCheckoutAttempt, remote: Dict[str, Any], now: datetime) -> SyncResult:
    org_id = attempt.organization_id
    sub = _locked_subscription(db, org_id)
    if sub is None or sub.provider_subscription_id != attempt.provider_subscription_id:
        # An older Razorpay subscription of this organization: it no longer drives the plan.
        return SyncResult("stale_subscription", org_id, attempt.id, "not the current subscription")
    status = str(remote.get("status") or "")
    paid_count = int(remote.get("paid_count") or 0)
    outcome = "no_change"

    applied = int(sub.provider_paid_count or 0)
    if paid_count > applied:
        for _ in range(paid_count - applied):
            try:
                subs.renew(db, org_id, now=now)
            except ConflictError as exc:
                return _review(attempt, "needs_review",
                               f"paid cycle not applied: {exc.details.get('code') or exc.message}")
            sub = _locked_subscription(db, org_id)
            sub.provider_paid_count = int(sub.provider_paid_count or 0) + 1
            db.flush()
        outcome = "renewed"

    access = subs.evaluate(sub, now)
    if status in ("pending", "halted"):
        if sub.state == S.ACTIVE.value and access.writable and outcome != "renewed":
            subs.mark_past_due(db, org_id, now=now)
            outcome = "past_due"
    elif status in ("cancelled", "completed"):
        if sub.state == S.ACTIVE.value and access.state == S.ACTIVE.value and not sub.cancel_at_period_end:
            subs.schedule_cancellation(db, org_id, now=now)  # the paid period runs out, nothing more is charged
            outcome = "cancellation_scheduled"
        elif sub.state in (S.ACTIVE.value, S.PAST_DUE.value) and access.state == S.PAST_DUE.value:
            subs.cancel_now(db, org_id, now=now)  # the renewal was never paid: access ends
            outcome = "cancelled"
    return SyncResult(outcome, org_id, attempt.id)


# --- Checkout callback -----------------------------------------------------------------------------------


class PaymentVerificationError(AppException):
    def __init__(self, message: str, code: str, status_code: int = 400):
        super().__init__(message, code=code, status_code=status_code)


CALLBACK_MESSAGES = {
    "active": "Payment confirmed. Your plan is active.",
    "pending": "Razorpay has your authorization; we are waiting for it to confirm the first payment. Your plan "
               "starts as soon as it does.",
    "not_paid": "No completed payment was found for this checkout. Nothing was charged for the plan yet.",
}


def verify_checkout_callback(db: Session, organization_id: str, *, payment_id: str, subscription_id: str,
                             signature: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The browser's Checkout result for `organization_id` (from the authenticated session). Commits."""
    attempt = db.scalars(
        select(PlatformCheckoutAttempt).where(
            PlatformCheckoutAttempt.organization_id == organization_id,
            PlatformCheckoutAttempt.provider_subscription_id == subscription_id,
        ).with_for_update().execution_options(populate_existing=True)
    ).first()
    if attempt is None:  # another organization's subscription, or none we created
        db.rollback()
        raise PaymentVerificationError("This checkout was not found.", "CHECKOUT_NOT_FOUND", 404)
    if attempt.status == "completed":
        db.rollback()
        return {"status": "active", "message": CALLBACK_MESSAGES["active"], "plan_code": attempt.plan_code}
    # The signature is checked against OUR stored subscription id, never the browser's.
    if not provider.verify_checkout_signature(payment_id, attempt.provider_subscription_id, signature):
        db.rollback()
        logger.warning("Checkout callback with an invalid signature for organization %s", organization_id)
        raise PaymentVerificationError("The payment could not be verified.", "PAYMENT_SIGNATURE_INVALID", 400)
    try:
        result = sync_provider_subscription(db, attempt.provider_subscription_id, payment_id=payment_id, now=now)
    except RetryLater:
        db.rollback()
        raise PaymentVerificationError("We could not confirm the payment with Razorpay right now. If you were "
                                       "charged, your plan will be activated automatically.", "PAYMENT_CONFIRMATION_DELAYED", 503)
    db.commit()
    if result.outcome in REVIEW_OUTCOMES:
        raise PaymentVerificationError("This payment needs a manual check by Rooman before the plan can start. "
                                       "Nothing has been changed on your account.", "PAYMENT_NEEDS_REVIEW", 409)
    status = "active" if result.active else ("pending" if result.outcome == "pending" else "not_paid")
    return {"status": status, "message": CALLBACK_MESSAGES[status], "plan_code": attempt.plan_code}

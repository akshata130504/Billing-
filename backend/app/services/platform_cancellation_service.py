"""Owner self-service cancellation of the organization's paid Rooman plan, with Rooman's Razorpay account.

Razorpay (https://razorpay.com/docs/api/payments/subscriptions/cancel-subscription/):
- POST /v1/subscriptions/{id}/cancel, `cancel_at_cycle_end` true (stays active until the current cycle ends,
  then `cancelled`) or false (`cancelled` now);
- ONE cancel per subscription (a second is refused), only while it is active / authenticated, and there is
  NO API to undo it ("Once cancelled, you cannot renew or reactivate it"). `cancel_scheduled_changes`
  undoes pending plan *updates*, not cancellations, and `resume` applies to *paused* subscriptions, which
  this application never creates. So neither "undo a scheduled cancellation" nor "resume" is offered.

The two modes and their access (the lifecycle functions in platform_subscription_service, unchanged):
- at_period_end -> `schedule_cancellation`: paid access continues until current_period_end, then the
  organization is read-only (`settle` records `cancelled`). Only while the paid period is running.
- immediately   -> `cancel_now` (the existing immediate policy): access ends now and the organization is
  read-only at once. No refund is computed here; nothing more is charged. Also allowed while past_due.

Nothing changes locally until Razorpay CONFIRMS: a 2xx answer for this subscription (for `immediately`
with status `cancelled`), or - when Razorpay refuses because the subscription is already cancelled there
(a retry after a timeout, or a cancellation made in the Razorpay dashboard) - a fresh read showing it
`cancelled`. A timeout changes nothing and says so; repeating the same request is safe (Razorpay refuses a
second cancel, so no duplicate or contradictory cancellation can reach it). While a cancellation is
scheduled, "cancel now" is refused: Razorpay would not accept a second cancel.

Ordering: the checkout attempt row of the subscription is locked first, as the webhook and the scheduled
reconciliation do, so the three never interleave. Their handling stays consistent: an immediately cancelled
row is never re-read or revived (`_later_events` / reconciliation skip `cancelled`), a scheduled one stays
`active` + cancel_at_period_end until `settle` records `cancelled`, and a renewal charged despite a scheduled
cancellation is refused by `renew` and reported for review.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import AppException
from backend.app.core.logging import logger
from backend.app.models import PlatformCheckoutAttempt, PlatformSubscription, PlatformSubscriptionState as S
from backend.app.services import platform_razorpay as provider, platform_subscription_service as subs, razorpay_gateway

AT_PERIOD_END = "at_period_end"
IMMEDIATELY = "immediately"
MODES = (AT_PERIOD_END, IMMEDIATELY)


class CancellationError(AppException):
    def __init__(self, message: str, code: str, status_code: int = 409):
        super().__init__(message, code=code, status_code=status_code)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _result(status: str, sub: PlatformSubscription, already: bool) -> Dict[str, Any]:
    if status == "scheduled":
        effective = _aware(sub.current_period_end)
        message = "Your plan is cancelled at the end of the current billing period. It keeps working until then."
    else:
        effective = _aware(sub.cancelled_at) or _utcnow()
        message = ("Your plan is cancelled. Your organization's data is safe and stays viewable; choose a plan "
                   "again to continue making changes.")
    return {"status": status, "effective_at": effective, "already": already, "message": message}


def _locked_subscription(db: Session, organization_id: str) -> Optional[PlatformSubscription]:
    return db.scalars(
        select(PlatformSubscription).where(PlatformSubscription.organization_id == organization_id)
        .with_for_update().execution_options(populate_existing=True)
    ).first()


def _remote_is_cancelled(subscription_id: str) -> bool:
    try:
        return str(provider.fetch_subscription(subscription_id).get("status") or "") == "cancelled"
    except provider.ProviderUnavailable:
        raise _unconfirmed()
    except provider.ProviderRejected:
        return False


def _unconfirmed() -> CancellationError:
    return CancellationError(
        "We could not confirm the cancellation with Razorpay. Nothing has changed yet; please try again in a moment.",
        "CANCELLATION_UNCONFIRMED", 503)


def cancel_subscription(db: Session, organization_id: str, mode: str, *, requested_by: Optional[str] = None,
                        now: Optional[datetime] = None) -> Dict[str, Any]:
    """Cancel the organization's paid plan (`mode` in MODES). Commits on success; raises CancellationError."""
    if mode not in MODES:
        raise CancellationError("Unknown cancellation option.", "INVALID_CANCELLATION_MODE", 422)
    now = _aware(now) or _utcnow()

    sub = db.scalars(select(PlatformSubscription).where(PlatformSubscription.organization_id == organization_id)).first()
    if sub is not None and sub.state == S.CANCELLED.value:
        return _result("cancelled", sub, already=True)
    if sub is None or not sub.provider_subscription_id or sub.state not in (S.ACTIVE.value, S.PAST_DUE.value):
        raise CancellationError("Your organization has no paid plan to cancel.", "NO_PAID_SUBSCRIPTION")
    if not razorpay_gateway.rooman_account_credentials().configured:
        raise CancellationError("Cancellation is not available right now. Please try again later.",
                                "CANCELLATION_NOT_AVAILABLE", 503)
    if sub.provider_mode != provider.mode():
        raise CancellationError("This plan cannot be cancelled here right now. Please contact Rooman support.",
                                "CANCELLATION_NOT_AVAILABLE")

    # Same lock order as the webhook and reconciliation: the attempt first, then the subscription.
    attempt = db.scalars(
        select(PlatformCheckoutAttempt).where(PlatformCheckoutAttempt.provider_subscription_id == sub.provider_subscription_id)
        .with_for_update().execution_options(populate_existing=True)
    ).first()
    sub = _locked_subscription(db, organization_id)
    if attempt is None or sub is None or sub.provider_subscription_id != attempt.provider_subscription_id:
        db.rollback()
        raise CancellationError("This plan cannot be cancelled here right now. Please contact Rooman support.",
                                "CANCELLATION_NOT_AVAILABLE")
    subscription_id = sub.provider_subscription_id

    # Decided on the state as it is now (another request may have finished while we waited for the lock).
    if sub.state == S.CANCELLED.value:
        db.rollback()
        return _result("cancelled", sub, already=True)
    if sub.cancel_at_period_end:
        db.rollback()
        if mode == AT_PERIOD_END:
            return _result("scheduled", sub, already=True)
        raise CancellationError(
            "A cancellation is already scheduled for the end of this billing period, and Razorpay accepts only one "
            "cancellation per subscription. Your plan keeps working until then.", "CANCELLATION_ALREADY_SCHEDULED")
    access = subs.evaluate(sub, now)
    if mode == AT_PERIOD_END and access.state != S.ACTIVE.value:
        db.rollback()
        raise CancellationError("A cancellation at the end of the period is only possible while the paid period is "
                                "running. You can cancel immediately instead.", "NOT_IN_PAID_PERIOD")
    if mode == IMMEDIATELY and not access.paid:
        db.rollback()
        raise CancellationError("Your organization has no paid plan to cancel.", "NO_PAID_SUBSCRIPTION")

    # Razorpay first; local state only after it confirms.
    try:
        remote = provider.cancel_subscription(subscription_id, at_cycle_end=(mode == AT_PERIOD_END))
        status = str(remote.get("status") or "")
        confirmed = status == "cancelled" if mode == IMMEDIATELY else True
        if not confirmed:  # a 2xx that does not show the cancellation: read again before believing either way
            confirmed = _remote_is_cancelled(subscription_id)
    except provider.ProviderUnavailable:
        db.rollback()
        logger.warning("Plan cancellation for organization %s unconfirmed: Razorpay unavailable", organization_id)
        raise _unconfirmed()
    except CancellationError:  # the confirming re-read could not reach Razorpay
        db.rollback()
        raise
    except provider.ProviderRejected:
        # Already cancelled there (a retry after a timeout, or the Razorpay dashboard)? Then reflect it.
        try:
            confirmed = _remote_is_cancelled(subscription_id)
        except CancellationError:
            db.rollback()
            raise
        if not confirmed:
            db.rollback()
            logger.warning("Plan cancellation for organization %s refused by Razorpay", organization_id)
            raise CancellationError("Razorpay could not cancel this plan right now. Nothing has changed; please try "
                                    "again in a few minutes or contact Rooman support.", "CANCELLATION_REFUSED")
        status = "cancelled"
    if not confirmed:
        db.rollback()
        logger.error("Plan cancellation for organization %s: Razorpay answered without cancelling", organization_id)
        raise _unconfirmed()

    if mode == IMMEDIATELY:
        sub = subs.cancel_now(db, organization_id, now=now)
        result = _result("cancelled", sub, already=False)
    else:
        # Razorpay keeps the subscription active until the cycle ends (or, if it already shows it cancelled,
        # the paid period still runs out - the same rule the webhook applies).
        sub = subs.schedule_cancellation(db, organization_id, now=now)
        result = _result("scheduled", sub, already=False)
    db.commit()
    logger.info("Plan cancellation for organization %s: %s (requested by user %s, Razorpay status %s)",
                organization_id, result["status"], requested_by or "-", status or "-")
    return result

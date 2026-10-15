"""The organization's paid Rooman plan: lifecycle, billing periods and what it allows.

One row per organization in `platform_subscriptions` (models/platform_billing.py), shared with the
free trial (platform_trial_service). Plans come from the catalog (core/plan_catalog.py): this module
stores a plan CODE and the billing interval of the current period, never prices, modules or seats.

Access is derived on every request from the stored row and the clock (`evaluate`), exactly like the
trial: nothing waits for a scheduler, and a row is never trusted just because its state says
'active' - an unknown plan or an incomplete or inconsistent period gives no access at all.

    stored state   effective state (now)                                          writes allowed
    -------------  -------------------------------------------------------------  --------------
    (no row)       none: organizations that predate trials, unchanged            yes
    trialing       trialing until trial_ends_at, then trial_expired               until trial end
    active         active until current_period_end (also when cancel_at_period_end is set);
                   then cancelled (cancel_at_period_end) or past_due until current_period_end
                   + PLATFORM_SUBSCRIPTION_GRACE_DAYS, then expired               while active/past_due
    past_due       past_due until grace_period_end, then expired                  until grace end
    cancelled      cancelled                                                       no
    expired        expired                                                         no
    anything else  invalid                                                         no

All boundaries are half-open: at exactly trial_ends_at / current_period_end / grace_period_end the
earlier state is over. Without write access the organization is read-only, as after a trial: its
data stays viewable (api/deps.py `_check_trial`). Organization lifecycle (suspension, deletion) and
module entitlements are checked separately and first; a subscription never bypasses them.

The transition functions below change the row (flush only; the caller commits) and refuse anything
not in TRANSITIONS. They take no payment and are not exposed through the API directly: verified payments
(platform_payment_service: callback, webhook, reconciliation) and Razorpay-confirmed Owner cancellations
(platform_cancellation_service: `schedule_cancellation` / `cancel_now`) call them. `undo_scheduled_cancellation`
has no caller on purpose: Razorpay cannot undo a cancellation, so offering it would contradict Razorpay. `activate` is the only place a paid plan grants modules and seats, through
the existing entitlement mechanism (organizations.module_access='entitled' + organization_entitlements).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, FrozenSet, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import ConflictError, NotFoundError
from backend.app.core.plan_catalog import Catalog, CatalogPlan, catalog, plan_modules
from backend.app.core.tenant_context import tenant_context
from backend.app.models import Organization, OrganizationStatus, PlatformSubscription, PlatformSubscriptionState as S
from backend.app.models.subscription_access import ModuleAccess
from backend.app.services import org_access, platform_audit
from backend.app.services.subscription_service import add_months

NONE = "none"  # no row: the organization predates trials (effective state only)
INVALID = "invalid"  # a row that cannot be trusted (effective state only)

TRIAL_EXPIRED_CODE = "TRIAL_EXPIRED"
INACTIVE_CODE = "SUBSCRIPTION_INACTIVE"

# Stored state -> stored states it may move to. None = no row yet.
TRANSITIONS: Dict[Optional[str], FrozenSet[str]] = {
    None: frozenset({S.ACTIVE.value}),
    S.TRIALING.value: frozenset({S.ACTIVE.value}),
    S.ACTIVE.value: frozenset({S.ACTIVE.value, S.PAST_DUE.value, S.CANCELLED.value}),
    S.PAST_DUE.value: frozenset({S.ACTIVE.value, S.CANCELLED.value, S.EXPIRED.value}),
    S.CANCELLED.value: frozenset({S.ACTIVE.value}),
    S.EXPIRED.value: frozenset({S.ACTIVE.value}),
}


@dataclass(frozen=True)
class SubscriptionAccess:
    state: str  # effective state (see the table above)
    writable: bool
    code: Optional[str] = None  # why writes are refused: TRIAL_EXPIRED or SUBSCRIPTION_INACTIVE
    access_until: Optional[datetime] = None  # when the current write access ends, if it does
    plan_code: Optional[str] = None
    cancel_at_period_end: bool = False

    @property
    def paid(self) -> bool:
        return self.state in (S.ACTIVE.value, S.PAST_DUE.value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def grace_period() -> timedelta:
    return timedelta(days=max(0, int(settings.PLATFORM_SUBSCRIPTION_GRACE_DAYS)))


def period_end(start: datetime, interval: str, interval_count: int, anchor_day: Optional[int] = None) -> datetime:
    """End of a billing period that starts at `start` (UTC, same time of day). Calendar months, with the
    day clamped to short months; `anchor_day` keeps e.g. the 31st across them."""
    start = _aware(start)
    months = int(interval_count) * (12 if interval == "year" else 1)
    if interval not in ("month", "year") or months < 1:
        raise ValueError(f"unsupported billing interval {interval!r} x {interval_count!r}")
    day = add_months(start.date(), months, anchor_day=anchor_day or start.day)
    return datetime.combine(day, start.timetz())


# --- evaluation ----------------------------------------------------------------------------------------


def _paid_row_is_valid(sub: PlatformSubscription, cat: Catalog) -> bool:
    start, end = _aware(sub.current_period_start), _aware(sub.current_period_end)
    return (
        bool(sub.plan_code) and cat.plan(sub.plan_code) is not None  # retired plans still exist
        and sub.billing_interval in ("month", "year")
        and isinstance(sub.billing_interval_count, int) and 1 <= sub.billing_interval_count <= 12
        and start is not None and end is not None and end > start
    )


def evaluate(sub: Optional[PlatformSubscription], now: Optional[datetime] = None,
             cat: Optional[Catalog] = None) -> SubscriptionAccess:
    """The effective state of `sub` at `now` and whether the organization may change data."""
    now = _aware(now) or _utcnow()
    if sub is None:
        return SubscriptionAccess(state=NONE, writable=True)
    state = sub.state
    if state == S.TRIALING.value:
        ends = _aware(sub.trial_ends_at)
        if ends is None:
            return SubscriptionAccess(state=INVALID, writable=False, code=INACTIVE_CODE)
        if now < ends:
            return SubscriptionAccess(state=state, writable=True, access_until=ends)
        return SubscriptionAccess(state=S.TRIAL_EXPIRED.value, writable=False, code=TRIAL_EXPIRED_CODE)
    if state not in (S.ACTIVE.value, S.PAST_DUE.value, S.CANCELLED.value, S.EXPIRED.value):
        return SubscriptionAccess(state=INVALID, writable=False, code=INACTIVE_CODE)
    if not _paid_row_is_valid(sub, cat or catalog()):
        return SubscriptionAccess(state=INVALID, writable=False, code=INACTIVE_CODE, plan_code=sub.plan_code)

    plan_code, flag = sub.plan_code, bool(sub.cancel_at_period_end)
    ended = SubscriptionAccess(state=S.EXPIRED.value, writable=False, code=INACTIVE_CODE, plan_code=plan_code)
    period_ends = _aware(sub.current_period_end)
    if state == S.ACTIVE.value:
        if now < period_ends:
            return SubscriptionAccess(state=state, writable=True, access_until=period_ends, plan_code=plan_code,
                                      cancel_at_period_end=flag)
        if flag:
            return SubscriptionAccess(state=S.CANCELLED.value, writable=False, code=INACTIVE_CODE, plan_code=plan_code)
        # The period ended without a recorded renewal: the same grace as a failed renewal.
        grace_ends = period_ends + grace_period()
        if now < grace_ends:
            return SubscriptionAccess(state=S.PAST_DUE.value, writable=True, access_until=grace_ends, plan_code=plan_code)
        return ended
    if state == S.PAST_DUE.value:
        grace_ends = _aware(sub.grace_period_end)
        if grace_ends is None:
            return SubscriptionAccess(state=INVALID, writable=False, code=INACTIVE_CODE, plan_code=plan_code)
        if now < grace_ends:
            return SubscriptionAccess(state=state, writable=True, access_until=grace_ends, plan_code=plan_code)
        return ended
    if state == S.CANCELLED.value:
        return SubscriptionAccess(state=state, writable=False, code=INACTIVE_CODE, plan_code=plan_code)
    return ended


def get_subscription(db: Session, organization_id: str) -> Optional[PlatformSubscription]:
    return db.scalars(
        select(PlatformSubscription).where(PlatformSubscription.organization_id == organization_id)
    ).first()


def access_for(db: Session, organization_id: str, now: Optional[datetime] = None) -> SubscriptionAccess:
    return evaluate(get_subscription(db, organization_id), now)


def summary(db: Session, organization_id: str, now: Optional[datetime] = None) -> Optional[Dict[str, object]]:
    """The paid plan for /auth/me, or None while there is none (no row, or still the trial row)."""
    sub = get_subscription(db, organization_id)
    if sub is None or sub.state == S.TRIALING.value:
        return None
    access = evaluate(sub, now)
    plan = catalog().plan(sub.plan_code) if sub.plan_code else None
    return {
        "state": access.state,
        "plan_code": sub.plan_code,
        "sandbox": bool(plan and plan.is_sandbox),  # a Test Mode sandbox plan, not a commercial one
        "billing_interval": sub.billing_interval,
        "billing_interval_count": sub.billing_interval_count,
        "current_period_start": _aware(sub.current_period_start),
        "current_period_end": _aware(sub.current_period_end),
        "cancel_at_period_end": bool(sub.cancel_at_period_end),
        "grace_period_end": access.access_until if access.state == S.PAST_DUE.value else None,
        "writable": access.writable,
    }


# --- transitions ---------------------------------------------------------------------------------------


def _locked(db: Session, organization_id: str) -> tuple[Organization, Optional[PlatformSubscription]]:
    org = db.scalars(select(Organization).where(Organization.id == organization_id).with_for_update()).first()
    if org is None:
        raise NotFoundError("Organization not found.")
    sub = db.scalars(
        select(PlatformSubscription).where(PlatformSubscription.organization_id == organization_id)
        .with_for_update().execution_options(populate_existing=True)
    ).first()
    return org, sub


def _move(sub: Optional[PlatformSubscription], to: str) -> None:
    current = sub.state if sub is not None else None
    if to not in TRANSITIONS.get(current, frozenset()):
        raise ConflictError(
            f"A subscription cannot go from {current or 'none'} to {to}.",
            {"code": "INVALID_SUBSCRIPTION_TRANSITION", "from": current, "to": to},
        )


def plan_on_sale(plan: Optional[CatalogPlan]) -> bool:
    """Published plans; and sandbox test plans, only while platform_razorpay.sandbox_readiness() allows them
    (explicit flag, local environment, Test Mode keys). Drafts are not approved for sale and retired plans
    are no longer sold - no exception for them."""
    if plan is None:
        return False
    if plan.is_published:
        return True
    if plan.is_sandbox:
        from backend.app.services import platform_razorpay

        return platform_razorpay.sandbox_readiness() is None
    return False


def sellable_plan(plan_code: str) -> CatalogPlan:
    plan = catalog().plan(plan_code)
    if plan is None or not plan_on_sale(plan):
        raise ConflictError("This plan is not available.", {"code": "PLAN_NOT_AVAILABLE", "plan_code": plan_code})
    return plan


def _audit(db: Session, org: Organization, action: str, sub: PlatformSubscription, **details) -> None:
    platform_audit.record(
        db, action=action, result=platform_audit.SUCCESS, organization=org,
        target_type="platform_subscription", target_id=sub.id,
        details={"plan_code": sub.plan_code, "state": sub.state, **details},
    )


def _notify(kind: str, db: Session, org: Organization, sub: PlatformSubscription) -> None:
    """Queue the customer email for this transition in the same transaction (platform_notification_service)."""
    from backend.app.services import platform_notification_service as notifications

    getattr(notifications, kind)(db, org, sub)


def _start_period(sub: PlatformSubscription, plan: CatalogPlan, start: datetime, anchor_day: Optional[int] = None) -> None:
    sub.plan_code = plan.code
    sub.billing_interval = plan.price.interval
    sub.billing_interval_count = plan.price.interval_count
    sub.current_period_start = start
    sub.current_period_end = period_end(start, plan.price.interval, plan.price.interval_count, anchor_day)
    sub.grace_period_end = None


def activate(db: Session, organization_id: str, plan_code: str, now: Optional[datetime] = None) -> PlatformSubscription:
    """Start a paid plan now: from the trial (running or ended), with no row at all, or after a
    cancelled / expired one. Grants the plan's modules and seat limit. Refused for a plan that is not
    on sale (`plan_on_sale`: published, or a sandbox test plan while the sandbox is allowed), an organization that is not ACTIVE, one that already has a paid plan, or one with more
    members than the plan's seats."""
    now = _aware(now) or _utcnow()
    plan = sellable_plan(plan_code)
    org, sub = _locked(db, organization_id)
    if (org.status or OrganizationStatus.ACTIVE) != OrganizationStatus.ACTIVE:
        raise ConflictError("Only an active organization can start a plan.", {"code": "ORGANIZATION_NOT_ACTIVE"})
    if evaluate(sub, now).paid:
        # Still paid (active, or past_due within its grace): that needs renew / recovery, not a new plan.
        # Judged on the effective state, so a row whose access has ended but was never settled (the
        # stored state still says active / past_due) can start a new plan.
        raise ConflictError("This organization already has a paid plan.", {"code": "SUBSCRIPTION_ALREADY_ACTIVE"})
    _move(sub, S.ACTIVE.value)
    used = org_access.seats_used(db, org.id)
    if used > plan.seat_limit:
        raise ConflictError(
            f"The {plan.name} plan allows {plan.seat_limit} user seat(s); your organization has {used} members "
            "and invitations.",
            {"code": "SEATS_EXCEED_PLAN", "seat_limit": plan.seat_limit, "seats_used": used},
        )
    previous = sub.state if sub is not None else None
    if sub is None:
        sub = PlatformSubscription(organization_id=org.id, reminders_sent=[])
        db.add(sub)
    sub.state = S.ACTIVE.value
    _start_period(sub, plan, now)
    sub.cancel_at_period_end = False
    sub.cancelled_at = None

    # The plan's modules and seats, through the existing entitlement mechanism (org_access).
    from backend.app.services.subscription_request_service import _replace_entitlements

    with tenant_context(org.id):
        org.module_access = ModuleAccess.ENTITLED.value
        org.seat_limit = plan.seat_limit
        _replace_entitlements(db, org, sorted(plan_modules(plan)), source="plan", staff_id=None)
    db.flush()
    _audit(db, org, platform_audit.PLATFORM_SUBSCRIPTION_ACTIVATED, sub, previous_state=previous,
           current_period_end=sub.current_period_end.isoformat(), seat_limit=plan.seat_limit)
    return sub


def renew(db: Session, organization_id: str, now: Optional[datetime] = None) -> PlatformSubscription:
    """The next billing period of the same plan, starting where the current one ends. Only while the
    subscription still has access (active, or past_due within its grace); a plan that is no longer
    published is not renewed."""
    now = _aware(now) or _utcnow()
    org, sub = _locked(db, organization_id)
    access = evaluate(sub, now)
    if sub is None or not access.writable or access.state not in (S.ACTIVE.value, S.PAST_DUE.value):
        raise ConflictError("Only an active or past-due subscription can be renewed.",
                            {"code": "INVALID_SUBSCRIPTION_TRANSITION", "state": access.state})
    if sub.cancel_at_period_end:
        raise ConflictError("This subscription is set to cancel at the end of its period.",
                            {"code": "CANCELLATION_SCHEDULED"})
    plan = sellable_plan(sub.plan_code)
    _move(sub, S.ACTIVE.value)
    old_start, old_end = _aware(sub.current_period_start), _aware(sub.current_period_end)
    sub.state = S.ACTIVE.value
    # max(start day, end day) keeps an end-of-month anchor (e.g. the 31st) across short months.
    _start_period(sub, plan, old_end, anchor_day=max(old_start.day, old_end.day))
    db.flush()
    _audit(db, org, platform_audit.PLATFORM_SUBSCRIPTION_RENEWED, sub,
           current_period_end=sub.current_period_end.isoformat())
    return sub


def mark_past_due(db: Session, organization_id: str, now: Optional[datetime] = None) -> PlatformSubscription:
    """A renewal payment failed: access continues until grace_period_end (current_period_end + grace)."""
    now = _aware(now) or _utcnow()
    org, sub = _locked(db, organization_id)
    if sub is None or sub.state != S.ACTIVE.value or not evaluate(sub, now).writable:
        raise ConflictError("Only an active subscription can become past due.",
                            {"code": "INVALID_SUBSCRIPTION_TRANSITION", "from": sub.state if sub else None})
    _move(sub, S.PAST_DUE.value)
    sub.state = S.PAST_DUE.value
    sub.grace_period_end = _aware(sub.current_period_end) + grace_period()
    db.flush()
    _audit(db, org, platform_audit.PLATFORM_SUBSCRIPTION_PAST_DUE, sub, grace_period_end=sub.grace_period_end.isoformat())
    _notify("payment_past_due", db, org, sub)
    return sub


def _active_now(sub: Optional[PlatformSubscription], now: datetime) -> PlatformSubscription:
    if sub is None or sub.state != S.ACTIVE.value or evaluate(sub, now).state != S.ACTIVE.value:
        raise ConflictError("Only an active subscription within its paid period can do this.",
                            {"code": "INVALID_SUBSCRIPTION_TRANSITION", "state": evaluate(sub, now).state})
    return sub


def schedule_cancellation(db: Session, organization_id: str, now: Optional[datetime] = None) -> PlatformSubscription:
    """Cancel at the end of the paid period: access continues until current_period_end."""
    now = _aware(now) or _utcnow()
    org, sub = _locked(db, organization_id)
    sub = _active_now(sub, now)
    sub.cancel_at_period_end = True
    db.flush()
    _audit(db, org, platform_audit.PLATFORM_SUBSCRIPTION_CANCELLATION_SCHEDULED, sub,
           current_period_end=_aware(sub.current_period_end).isoformat())
    _notify("cancellation_scheduled", db, org, sub)
    return sub


def undo_scheduled_cancellation(db: Session, organization_id: str, now: Optional[datetime] = None) -> PlatformSubscription:
    now = _aware(now) or _utcnow()
    org, sub = _locked(db, organization_id)
    sub = _active_now(sub, now)
    if not sub.cancel_at_period_end:
        raise ConflictError("No cancellation is scheduled.", {"code": "NO_CANCELLATION_SCHEDULED"})
    sub.cancel_at_period_end = False
    db.flush()
    _audit(db, org, platform_audit.PLATFORM_SUBSCRIPTION_CANCELLATION_UNDONE, sub)
    return sub


def cancel_now(db: Session, organization_id: str, now: Optional[datetime] = None) -> PlatformSubscription:
    """End paid access immediately (no refund logic here)."""
    now = _aware(now) or _utcnow()
    org, sub = _locked(db, organization_id)
    _move(sub, S.CANCELLED.value)
    sub.state = S.CANCELLED.value
    sub.cancelled_at = now
    db.flush()
    _audit(db, org, platform_audit.PLATFORM_SUBSCRIPTION_CANCELLED, sub, immediate=True)
    _notify("cancelled_immediately", db, org, sub)
    return sub


def settle(db: Session, organization_id: str, now: Optional[datetime] = None) -> Optional[PlatformSubscription]:
    """Record the state time has already produced (access never waits for this): an ended period
    with a scheduled cancellation -> cancelled; without one -> past_due (grace from the period end);
    a grace period that has ended -> expired. Returns the row; unchanged when nothing is due."""
    now = _aware(now) or _utcnow()
    org, sub = _locked(db, organization_id)
    if sub is None or not _paid_row_is_valid(sub, catalog()):
        return sub
    period_ends = _aware(sub.current_period_end)
    if sub.state == S.ACTIVE.value and now >= period_ends:
        if sub.cancel_at_period_end:
            _move(sub, S.CANCELLED.value)
            sub.state, sub.cancelled_at = S.CANCELLED.value, period_ends
            db.flush()
            _audit(db, org, platform_audit.PLATFORM_SUBSCRIPTION_CANCELLED, sub, immediate=False)
            _notify("cancellation_effective", db, org, sub)
            return sub
        _move(sub, S.PAST_DUE.value)
        sub.state, sub.grace_period_end = S.PAST_DUE.value, period_ends + grace_period()
        db.flush()
        _audit(db, org, platform_audit.PLATFORM_SUBSCRIPTION_PAST_DUE, sub,
               grace_period_end=sub.grace_period_end.isoformat())
        _notify("payment_past_due", db, org, sub)
    if sub.state == S.PAST_DUE.value and sub.grace_period_end is not None and now >= _aware(sub.grace_period_end):
        _move(sub, S.EXPIRED.value)
        sub.state = S.EXPIRED.value
        db.flush()
        _audit(db, org, platform_audit.PLATFORM_SUBSCRIPTION_EXPIRED, sub)
        _notify("access_expired", db, org, sub)  # supersedes this subscription's pending past-due email
    return sub

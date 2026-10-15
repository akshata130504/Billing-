"""What an organization may use right now: trial state, product modules and seats.

Self-service organizations go PENDING_APPROVAL -> (Platform Administrator approves) ACTIVE with
module_access 'trial' and a trial_ends_at -> after the trial, only the subscription screen until a
subscription request is approved (module_access 'entitled'). The trial is a phase of an ACTIVE
organization, so the platform lifecycle (suspend / reactivate / deletion) applies unchanged.

The backend is authoritative. Trial expiry is computed from organizations.trial_ends_at (UTC) on
every request. Module access comes only from the organization's status, module_access and
organization_entitlements rows - never from the Visual Editor or anything the browser sends.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, FrozenSet, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.entitlements import registry
from backend.app.core.exceptions import ConflictError
from backend.app.core.tenant_context import system_context, tenant_context
from backend.app.models import Membership, MembershipStatus, Organization, OrganizationStatus
from backend.app.models.base import utcnow
from backend.app.models.subscription_access import ModuleAccess, OrganizationEntitlement

SEAT_STATUSES = (MembershipStatus.ACTIVE, MembershipStatus.INVITED)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def in_trial_phase(org: Organization) -> bool:
    """An approved self-service organization that has no approved subscription yet."""
    status = org.status or OrganizationStatus.ACTIVE
    if status in (OrganizationStatus.TRIAL, OrganizationStatus.TRIAL_EXPIRED):  # rows from before trial-as-phase
        return True
    return status == OrganizationStatus.ACTIVE and (org.module_access or "") == ModuleAccess.TRIAL.value


def effective_status(org: Organization, now: Optional[datetime] = None) -> OrganizationStatus:
    """The status access decisions use: the stored lifecycle status, except that an organization in
    its trial phase is TRIAL until trial_ends_at and TRIAL_EXPIRED from then on (fails closed when
    no end is recorded)."""
    status = org.status or OrganizationStatus.ACTIVE
    if in_trial_phase(org):
        ends = _aware(org.trial_ends_at)
        if ends is None or (now or utcnow()) >= ends:
            return OrganizationStatus.TRIAL_EXPIRED
        return OrganizationStatus.TRIAL
    return status


def is_unrestricted(org: Organization) -> bool:
    return (org.module_access or ModuleAccess.UNRESTRICTED.value) == ModuleAccess.UNRESTRICTED.value


def entitled_modules(db: Session, org: Organization, now: Optional[datetime] = None) -> FrozenSet[str]:
    """Module keys this organization may use. Base modules are always included."""
    reg = registry()
    if is_unrestricted(org) or effective_status(org, now) == OrganizationStatus.TRIAL:
        return reg.all_keys  # pre-entitlement organizations, and every module during the trial
    with tenant_context(org.id):
        rows = db.scalars(
            select(OrganizationEntitlement.module_key).where(OrganizationEntitlement.organization_id == org.id)
        ).all()
    return reg.base_keys | (frozenset(rows) & reg.optional_keys)


def module_entitled(db: Session, organization_id: Optional[str], module_key: str,
                    now: Optional[datetime] = None) -> bool:
    """Whether the organization may use `module_key` right now (base modules always).

    For unattended work (scheduler, outbox, inbound webhooks) that has no request context: reads the
    organization's current columns from the database, never a possibly stale identity-map object."""
    if module_key in registry().base_keys:
        return True
    if not organization_id:
        return False
    row = db.execute(
        select(Organization.status, Organization.module_access, Organization.trial_ends_at)
        .where(Organization.id == organization_id)
    ).first()
    if row is None:
        return False
    probe = SimpleNamespace(id=organization_id, status=row.status, module_access=row.module_access,
                            trial_ends_at=row.trial_ends_at)
    return module_key in entitled_modules(db, probe, now)  # type: ignore[arg-type]


def seats_used(db: Session, organization_id: str) -> int:
    return int(db.scalar(
        select(func.count(Membership.id)).where(
            Membership.organization_id == organization_id, Membership.status.in_(SEAT_STATUSES)
        )
    ) or 0)


def ensure_seat_available(db: Session, org: Organization, *, already_counted: bool = False) -> None:
    """Refuse adding a member (an invitation, or reactivating one) beyond the seat limit.

    `already_counted`: the membership already holds a seat (re-inviting an invited member, or
    accepting an invitation), so it needs room for itself only, not one more.
    """
    if org.seat_limit is None:
        return
    used = seats_used(db, org.id)
    needed = used if already_counted else used + 1
    if needed > int(org.seat_limit):
        raise ConflictError(
            f"Your subscription allows {org.seat_limit} user seat(s) and all are in use. "
            "Deactivate a member or ask Rooman for more seats.",
            {"code": "SEAT_LIMIT_REACHED", "seat_limit": int(org.seat_limit), "seats_used": used},
        )


def access_summary(db: Session, org: Organization, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The organization's access, for /auth/me and the SPA (the API enforces it separately)."""
    now = now or utcnow()
    status = effective_status(org, now)
    modules = sorted(entitled_modules(db, org, now))
    nav: List[str] = list(registry().core_nav_items)
    for key in modules:
        nav.extend(registry().by_key[key].nav_items)
    return {
        "status": status.value,
        "trial_started_at": org.trial_started_at,
        "trial_ends_at": org.trial_ends_at,
        "module_access": org.module_access or ModuleAccess.UNRESTRICTED.value,
        "modules": modules,
        "nav_items": sorted(set(nav)),
        "seat_limit": org.seat_limit,
        "seats_used": seats_used(db, org.id),
    }


def expire_due_trials(db: Session, now: Optional[datetime] = None) -> int:
    """Write one ORGANIZATION_TRIAL_EXPIRED platform audit row per organization whose trial has ended.

    Access already ends at trial_ends_at on every request; this only records it. The lifecycle
    status is NOT changed (the organization stays ACTIVE, so suspend / reactivate keep working).
    Returns how many organizations were recorded (the caller commits).
    """
    from backend.app.models.platform import PlatformAuditLog
    from backend.app.services import platform_audit

    now = now or utcnow()
    with system_context():
        recorded = select(PlatformAuditLog.organization_id).where(
            PlatformAuditLog.action == platform_audit.ORGANIZATION_TRIAL_EXPIRED,
            PlatformAuditLog.organization_id.is_not(None),
        )
        due = db.scalars(
            select(Organization).where(
                Organization.status == OrganizationStatus.ACTIVE,
                Organization.module_access == ModuleAccess.TRIAL.value,
                Organization.trial_ends_at.is_not(None),
                Organization.trial_ends_at <= now,
                Organization.id.not_in(recorded),
            )
        ).all()
        for org in due:
            platform_audit.record(
                db, action=platform_audit.ORGANIZATION_TRIAL_EXPIRED, result=platform_audit.SUCCESS,
                organization=org, target_type="organization", target_id=org.id,
                details={"trial_ends_at": _aware(org.trial_ends_at).isoformat() if org.trial_ends_at else None},
            )
    return len(due)

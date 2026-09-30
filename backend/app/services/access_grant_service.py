"""Tenant access grants: the only way platform staff read tenant data (design sections 6-7, 11-12).

Lifecycle:  pending --(tenant Owner approves | emergency: a DIFFERENT Administrator approves)-->
            approved --(staff enters, step-up)--> active --> expired | revoked
            pending --> denied | cancelled | expired (never decided in time)

Rules enforced here (and by the route layer and database constraints):
- Only Support and Administrators request normal grants; only Administrators request emergency
  grants, and the approver must be another active Administrator (no single-person bypass).
- Scopes are read-only (core/grant_scopes); READ_METADATA is always included. Durations are 5-240
  minutes (default 60); emergency grants at most 60 minutes. No renewal: a longer window means a
  new request and a new approval.
- Every tenant-API request under a grant re-validates this row, the staff member, their platform
  session and the token's jti; anything off ends access on that request.
- Every event is written to the platform audit AND mirrored into the tenant's own audit log,
  attributed to the platform staff member (never to a tenant user). Each request made under a
  grant is recorded in both.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.alerts import send_alert
from backend.app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError, ValidationAppError
from backend.app.core.grant_scopes import SCOPE_LABELS, required_scope
from backend.app.core.security import create_grant_token, decode_grant_token
from backend.app.models import Membership, MemberRole, MembershipStatus, Organization, OrganizationStatus, User
from backend.app.models.access_grants import OPEN_STATUSES, GrantScope, GrantStatus, TenantAccessGrant
from backend.app.models.base import utcnow
from backend.app.models.platform import PlatformRole, PlatformSession, PlatformStaff
from backend.app.services import audit, platform_audit, platform_auth_service
from backend.app.services.platform_org_service import Actor

logger = logging.getLogger("rooman_billing.access_grants")

DEFAULT_MINUTES = 60
MAX_MINUTES = 240
EMERGENCY_MAX_MINUTES = 60
MIN_MINUTES = 5
MIN_REASON = 20
REVIEW_DUE_DAYS = 7  # "within 5 working days" (design section 12)

ADMIN = PlatformRole.PLATFORM_ADMINISTRATOR
SUPPORT = PlatformRole.PLATFORM_SUPPORT
REQUEST_ROLES = frozenset({ADMIN, SUPPORT})

# Platform audit events (design section 10)
REQUESTED = "ACCESS_GRANT_REQUESTED"
APPROVED = "ACCESS_GRANT_APPROVED"
DENIED = "ACCESS_GRANT_DENIED"
CANCELLED = "ACCESS_GRANT_CANCELLED"
ENTERED = "ACCESS_GRANT_ENTERED"
EXITED = "ACCESS_GRANT_EXITED"
REVOKED = "ACCESS_GRANT_REVOKED"
EXPIRED = "ACCESS_GRANT_EXPIRED"
DATA_ACCESSED = "TENANT_DATA_ACCESSED"
ACCESS_DENIED = "TENANT_ACCESS_DENIED"
EMERGENCY_REQUESTED = "EMERGENCY_ACCESS_REQUESTED"
EMERGENCY_APPROVED = "EMERGENCY_ACCESS_APPROVED"
EMERGENCY_REVIEWED = "EMERGENCY_ACCESS_REVIEWED"

# Tenant-visible audit actions (design section 11)
T_REQUESTED = "PLATFORM_ACCESS_REQUESTED"
T_APPROVED = "PLATFORM_ACCESS_APPROVED"
T_DENIED = "PLATFORM_ACCESS_DENIED"
T_CANCELLED = "PLATFORM_ACCESS_CANCELLED"
T_STARTED = "PLATFORM_ACCESS_STARTED"
T_ENDED = "PLATFORM_ACCESS_ENDED"
T_REVOKED = "PLATFORM_ACCESS_REVOKED"
T_EXPIRED = "PLATFORM_ACCESS_EXPIRED"
T_VIEWED = "PLATFORM_DATA_VIEWED"
T_REFUSED = "PLATFORM_ACCESS_REFUSED"


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


@dataclass
class GrantPrincipal:
    """What the tenant API knows about a request made under a grant."""

    grant: TenantAccessGrant
    staff: PlatformStaff
    organization: Organization
    scopes: Tuple[str, ...]
    route_scope: Optional[str] = None

    @property
    def actor_label(self) -> str:
        return f"Rooman Platform Support - {self.staff.full_name}"


# --- helpers -------------------------------------------------------------------------------------------


def _clean(text: Optional[str]) -> str:
    return " ".join((text or "").split())


def _normalise_scopes(requested: Sequence[str]) -> List[str]:
    valid = {s.value for s in GrantScope}
    unknown = [s for s in requested if s not in valid]
    if unknown:
        raise ValidationAppError("Unknown or unsupported scope requested.", {"scopes": unknown})
    scopes = {GrantScope.READ_METADATA.value, *requested}
    return [s.value for s in GrantScope if s.value in scopes]  # stable order


def _org(db: Session, organization_id: str) -> Organization:
    org = db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found.")
    return org


def _grant(db: Session, grant_id: str, *, lock: bool = False) -> TenantAccessGrant:
    stmt = select(TenantAccessGrant).where(TenantAccessGrant.id == grant_id)
    grant = db.scalars(stmt.with_for_update() if lock else stmt).first()
    if grant is None:
        raise NotFoundError("Access grant not found.")
    return grant


def _tenant_after(grant: TenantAccessGrant, staff: Optional[PlatformStaff], **extra) -> Dict[str, Any]:
    return {
        "actor_type": "platform_support",
        "platform_staff_id": grant.requested_by_staff_id,
        "platform_staff_name": staff.full_name if staff else None,
        "platform_role": staff.role.value if staff and staff.role else None,
        "access_grant_id": grant.id,
        "scopes": grant.scopes,
        "reason": grant.reason,
        "ticket_ref": grant.ticket_ref,
        "expires_at": _aware(grant.expires_at).isoformat() if grant.expires_at else None,
        "emergency": bool(grant.is_emergency),
        "status": grant.status,
        **extra,
    }


def _record(db: Session, grant: TenantAccessGrant, *, platform_action: str, tenant_action: str,
            actor: Optional[Actor], result: str = platform_audit.SUCCESS, tenant_actor_label: Optional[str] = None,
            reason: Optional[str] = None, details: Optional[Dict[str, Any]] = None,
            tenant_actor_user: Optional[User] = None, ip: Optional[str] = None, user_agent: Optional[str] = None) -> None:
    """Write the platform row and the tenant-visible mirror row for one grant event."""
    org = db.get(Organization, grant.organization_id)
    requester = db.get(PlatformStaff, grant.requested_by_staff_id)
    platform_audit.record(
        db, action=platform_action, result=result, staff=actor.staff if actor else None,
        email=None if actor else (tenant_actor_user.email if tenant_actor_user else "system"),
        session_id=actor.session_id if actor else None, ip_address=(actor.ip_address if actor else ip),
        user_agent=(actor.user_agent if actor else user_agent), organization=org, target_type="access_grant",
        target_id=grant.id, reason=reason or grant.reason, ticket_ref=grant.ticket_ref,
        details={"scopes": grant.scopes, "status": grant.status, "emergency": bool(grant.is_emergency), **(details or {})},
    )
    label = tenant_actor_label or (tenant_actor_user.full_name if tenant_actor_user else None) or (
        f"Rooman Platform Support - {requester.full_name}" if requester else "Rooman Platform"
    )
    audit.record(
        db, action=tenant_action, entity_type="platform_access_grant", entity_id=grant.id,
        entity_label=f"Platform access by {requester.full_name if requester else 'platform staff'}",
        organization_id=grant.organization_id, actor_label=label,
        status=audit.AuditStatus.SUCCESS if result == platform_audit.SUCCESS else audit.AuditStatus.DENIED,
        after=_tenant_after(grant, requester, **(details or {})),
        ip_address=(actor.ip_address if actor else ip), user_agent=(actor.user_agent if actor else user_agent),
    )


def _expire_if_due(db: Session, grant: TenantAccessGrant, now: Optional[datetime] = None) -> bool:
    """Lazily mark an elapsed grant expired (audited once). Returns True when it is expired now."""
    now = now or utcnow()
    if grant.status in (GrantStatus.APPROVED.value, GrantStatus.ACTIVE.value) and grant.expires_at and _aware(grant.expires_at) <= now:
        grant.status = GrantStatus.EXPIRED.value
        grant.current_token_jti = None
        _record(db, grant, platform_action=EXPIRED, tenant_action=T_EXPIRED, actor=None,
                tenant_actor_label="Rooman Platform (automatic)", details={"requests": grant.request_count})
        return True
    if grant.status == GrantStatus.PENDING.value and _aware(grant.created_at) + timedelta(hours=72) <= now:
        grant.status = GrantStatus.EXPIRED.value  # never decided; a fresh request is needed
        _record(db, grant, platform_action=EXPIRED, tenant_action=T_EXPIRED, actor=None,
                tenant_actor_label="Rooman Platform (automatic)", details={"undecided": True})
        return True
    return grant.status == GrantStatus.EXPIRED.value


def sweep_expired(db: Session, grants: Sequence[TenantAccessGrant]) -> None:
    now = utcnow()
    if any(_expire_if_due(db, g, now) for g in list(grants)):
        db.commit()


def _owner_emails(db: Session, organization_id: str) -> List[str]:
    return list(db.scalars(
        select(User.email).join(Membership, Membership.user_id == User.id).where(
            Membership.organization_id == organization_id, Membership.status == MembershipStatus.ACTIVE,
            Membership.role == MemberRole.OWNER, User.is_active.is_(True),
        )
    ))


@dataclass
class OwnerNotice:
    """An email to the tenant's Owners about a grant event, sent after the request (best effort)."""

    to: List[str]
    subject: str
    body: str

    def send(self) -> None:
        if not self.to:
            return
        try:
            from backend.app.services.email import send_email

            send_email(to=self.to, subject=self.subject, text_body=self.body)
        except Exception:  # never fail the platform action because email is unavailable
            logger.warning("Could not email tenant owners about a platform access grant", exc_info=True)


def _notice(db: Session, grant: TenantAccessGrant, headline: str) -> OwnerNotice:
    org = db.get(Organization, grant.organization_id)
    staff = db.get(PlatformStaff, grant.requested_by_staff_id)
    areas = ", ".join(SCOPE_LABELS.get(GrantScope(s), s) for s in grant.scopes)
    body = (
        f"{headline}\n\nOrganization: {org.name if org else grant.organization_id}\n"
        f"Rooman platform staff: {staff.full_name if staff else 'unknown'}\n"
        f"Access (read-only): {areas}\nReason: {grant.reason}\nTicket: {grant.ticket_ref}\n"
        f"Duration: {grant.requested_duration_minutes} minutes"
        + ("\nThis is an EMERGENCY access approved by a second Rooman Platform Administrator." if grant.is_emergency else "")
        + "\n\nReview, approve, deny or revoke it in Rooman Billing: Settings > Security > Platform access."
    )
    return OwnerNotice(to=_owner_emails(db, grant.organization_id), subject=f"Rooman Billing: {headline}", body=body)


def to_dict(db: Session, grant: TenantAccessGrant) -> Dict[str, Any]:
    staff = db.get(PlatformStaff, grant.requested_by_staff_id)
    approver_staff = db.get(PlatformStaff, grant.approved_by_staff_id) if grant.approved_by_staff_id else None
    approver_user = db.get(User, grant.approved_by_user_id) if grant.approved_by_user_id else None
    org = db.get(Organization, grant.organization_id)
    review_due = None
    if grant.is_emergency and grant.approved_at and not grant.reviewed_at:
        review_due = _aware(grant.approved_at) + timedelta(days=REVIEW_DUE_DAYS)
    return {
        "id": grant.id, "organization_id": grant.organization_id, "organization_name": org.name if org else None,
        "status": grant.status, "scopes": list(grant.scopes), "reason": grant.reason, "ticket_ref": grant.ticket_ref,
        "requested_duration_minutes": grant.requested_duration_minutes, "is_emergency": bool(grant.is_emergency),
        "requested_by": {"id": staff.id, "full_name": staff.full_name, "email": staff.email, "role": staff.role.value} if staff else None,
        "approved_by": (
            {"kind": "platform_staff", "id": approver_staff.id, "full_name": approver_staff.full_name} if approver_staff
            else {"kind": "tenant_user", "id": approver_user.id, "full_name": approver_user.full_name} if approver_user else None
        ),
        "created_at": grant.created_at, "approved_at": grant.approved_at, "first_used_at": grant.first_used_at,
        "last_entered_at": grant.last_entered_at, "expires_at": grant.expires_at, "revoked_at": grant.revoked_at,
        "revoked_by_kind": grant.revoked_by_kind, "revoke_reason": grant.revoke_reason, "denied_at": grant.denied_at,
        "denied_reason": grant.denied_reason, "request_count": grant.request_count, "reviewed_at": grant.reviewed_at,
        "review_notes": grant.review_notes, "review_due_at": review_due,
        "review_overdue": bool(review_due and review_due <= utcnow()),
    }


# --- platform side ----------------------------------------------------------------------------------------


def _create(db: Session, actor: Actor, *, organization_id: str, scopes: Sequence[str], duration_minutes: int,
            reason: str, ticket_ref: str, emergency: bool) -> TenantAccessGrant:
    reason, ticket_ref = _clean(reason), _clean(ticket_ref)
    if len(reason) < MIN_REASON:
        raise ValidationAppError(f"Give a reason of at least {MIN_REASON} characters.")
    if len(ticket_ref) < 2:
        raise ValidationAppError("A ticket or incident reference is required.")
    limit = EMERGENCY_MAX_MINUTES if emergency else MAX_MINUTES
    if not MIN_MINUTES <= int(duration_minutes) <= limit:
        raise ValidationAppError(f"Duration must be between {MIN_MINUTES} and {limit} minutes.")
    org = _org(db, organization_id)
    if org.status == OrganizationStatus.DELETED:
        raise ConflictError("This organization has been deleted.")
    grant = TenantAccessGrant(
        organization_id=org.id, requested_by_staff_id=actor.staff.id, status=GrantStatus.PENDING.value,
        scopes=_normalise_scopes(scopes), reason=reason[:2000], ticket_ref=ticket_ref[:100],
        requested_duration_minutes=int(duration_minutes), is_emergency=emergency, created_at=utcnow(), request_count=0,
    )
    db.add(grant)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflictError("You already have an open access request or grant for this organization.")
    return grant


def request_grant(db: Session, actor: Actor, *, organization_id: str, scopes: Sequence[str],
                  duration_minutes: int = DEFAULT_MINUTES, reason: str, ticket_ref: str) -> Tuple[Dict[str, Any], OwnerNotice]:
    if actor.role not in REQUEST_ROLES:
        raise ForbiddenError("Your platform role cannot request tenant access.")
    grant = _create(db, actor, organization_id=organization_id, scopes=scopes, duration_minutes=duration_minutes,
                    reason=reason, ticket_ref=ticket_ref, emergency=False)
    _record(db, grant, platform_action=REQUESTED, tenant_action=T_REQUESTED, actor=actor)
    notice = _notice(db, grant, "Rooman platform support has requested access to your organization")
    db.commit()
    return to_dict(db, grant), notice


def request_emergency(db: Session, actor: Actor, *, organization_id: str, scopes: Sequence[str],
                      duration_minutes: int, reason: str, ticket_ref: str) -> Dict[str, Any]:
    if actor.role != ADMIN:
        raise ForbiddenError("Only Platform Administrators can request emergency access.")
    grant = _create(db, actor, organization_id=organization_id, scopes=scopes, duration_minutes=duration_minutes,
                    reason=reason, ticket_ref=ticket_ref, emergency=True)
    _record(db, grant, platform_action=EMERGENCY_REQUESTED, tenant_action=T_REQUESTED, actor=actor)
    db.commit()
    send_alert("platform.emergency_access.requested", "Emergency tenant access requested - a second Platform Administrator must approve",
               {"grant_id": grant.id, "organization_id": grant.organization_id, "requested_by": actor.staff.email,
                "ticket_ref": grant.ticket_ref}, severity="warning", dedup_key=f"emergency-requested:{grant.id}")
    return to_dict(db, grant)


def approve_emergency(db: Session, actor: Actor, grant_id: str) -> Tuple[Dict[str, Any], OwnerNotice]:
    grant = _grant(db, grant_id, lock=True)
    if not grant.is_emergency:
        raise ConflictError("Only emergency requests are approved by platform staff; normal requests need the tenant Owner.")
    if actor.role != ADMIN:
        raise ForbiddenError("Only Platform Administrators can approve emergency access.")
    if grant.requested_by_staff_id == actor.staff.id:
        _record(db, grant, platform_action=EMERGENCY_APPROVED, tenant_action=T_REFUSED, actor=actor,
                result=platform_audit.DENIED, details={"refused": "self-approval"})
        db.commit()
        raise ForbiddenError("A different Platform Administrator must approve emergency access.")
    if _expire_if_due(db, grant):
        db.commit()
        raise ConflictError("This request has expired.")
    if grant.status != GrantStatus.PENDING.value:
        raise ConflictError(f"This request is {grant.status}.")
    now = utcnow()
    grant.status = GrantStatus.APPROVED.value
    grant.approved_at = now
    grant.approved_by_staff_id = actor.staff.id
    grant.expires_at = now + timedelta(minutes=grant.requested_duration_minutes)
    _record(db, grant, platform_action=EMERGENCY_APPROVED, tenant_action=T_APPROVED, actor=actor,
            tenant_actor_label=f"Rooman Platform Administrator - {actor.staff.full_name} (emergency approval)")
    notice = _notice(db, grant, "EMERGENCY Rooman platform access to your organization was approved")
    db.commit()
    send_alert("platform.emergency_access.approved", "Emergency tenant access APPROVED",
               {"grant_id": grant.id, "organization_id": grant.organization_id, "approved_by": actor.staff.email,
                "expires_at": grant.expires_at.isoformat()}, severity="critical", dedup_key=f"emergency-approved:{grant.id}")
    return to_dict(db, grant), notice


def review_emergency(db: Session, actor: Actor, grant_id: str, notes: str) -> Dict[str, Any]:
    if actor.role != ADMIN:
        raise ForbiddenError("Only Platform Administrators record emergency reviews.")
    notes = _clean(notes)
    if len(notes) < MIN_REASON:
        raise ValidationAppError(f"Write a review of at least {MIN_REASON} characters.")
    grant = _grant(db, grant_id, lock=True)
    if not grant.is_emergency or grant.approved_at is None:
        raise ConflictError("Only approved emergency grants are reviewed.")
    if grant.reviewed_at is not None:
        raise ConflictError("This emergency access has already been reviewed.")
    grant.reviewed_at, grant.reviewed_by_staff_id, grant.review_notes = utcnow(), actor.staff.id, notes[:4000]
    _record(db, grant, platform_action=EMERGENCY_REVIEWED, tenant_action="PLATFORM_ACCESS_REVIEWED", actor=actor,
            reason=notes[:500])
    db.commit()
    return to_dict(db, grant)


def list_grants(db: Session, actor: Actor, *, status: Optional[str] = None, organization_id: Optional[str] = None,
                emergency: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Support sees its own requests; Administrators see all (design section 9)."""
    stmt = select(TenantAccessGrant)
    if actor.role != ADMIN:
        stmt = stmt.where(TenantAccessGrant.requested_by_staff_id == actor.staff.id)
    if organization_id:
        stmt = stmt.where(TenantAccessGrant.organization_id == organization_id)
    if emergency is not None:
        stmt = stmt.where(TenantAccessGrant.is_emergency.is_(emergency))
    rows = db.scalars(stmt.order_by(TenantAccessGrant.created_at.desc()).limit(200)).all()
    sweep_expired(db, rows)
    if status:
        rows = [r for r in rows if r.status == status]
    return [to_dict(db, r) for r in rows]


def get_for_staff(db: Session, actor: Actor, grant_id: str) -> Dict[str, Any]:
    grant = _grant(db, grant_id)
    if actor.role != ADMIN and grant.requested_by_staff_id != actor.staff.id:
        raise NotFoundError("Access grant not found.")
    sweep_expired(db, [grant])
    return to_dict(db, grant)


def cancel(db: Session, actor: Actor, grant_id: str) -> Dict[str, Any]:
    grant = _grant(db, grant_id, lock=True)
    if grant.requested_by_staff_id != actor.staff.id:
        raise NotFoundError("Access grant not found.")
    if grant.status != GrantStatus.PENDING.value:
        raise ConflictError("Only a pending request can be cancelled; revoke an approved grant instead.")
    grant.status = GrantStatus.CANCELLED.value
    _record(db, grant, platform_action=CANCELLED, tenant_action=T_CANCELLED, actor=actor)
    db.commit()
    return to_dict(db, grant)


def revoke_by_staff(db: Session, actor: Actor, grant_id: str, reason: str) -> Tuple[Dict[str, Any], Optional[OwnerNotice]]:
    grant = _grant(db, grant_id, lock=True)
    if actor.role != ADMIN and grant.requested_by_staff_id != actor.staff.id:
        raise NotFoundError("Access grant not found.")
    if grant.status not in (GrantStatus.PENDING.value, GrantStatus.APPROVED.value, GrantStatus.ACTIVE.value):
        raise ConflictError(f"This grant is already {grant.status}.")
    was_used = grant.first_used_at is not None
    grant.status = GrantStatus.REVOKED.value
    grant.revoked_at, grant.revoked_by_kind, grant.revoked_by_id = utcnow(), "platform_staff", actor.staff.id
    grant.revoke_reason = _clean(reason)[:300] or None
    grant.current_token_jti = None
    _record(db, grant, platform_action=REVOKED, tenant_action=T_REVOKED, actor=actor, reason=grant.revoke_reason,
            details={"requests": grant.request_count})
    notice = _notice(db, grant, "Rooman platform access to your organization has ended") if was_used else None
    db.commit()
    return to_dict(db, grant), notice


def enter(db: Session, actor: Actor, grant_id: str) -> Dict[str, Any]:
    """Issue a short grant token for the tenant API (route requires a fresh step-up)."""
    grant = _grant(db, grant_id, lock=True)
    if grant.requested_by_staff_id != actor.staff.id:
        raise NotFoundError("Access grant not found.")
    if _expire_if_due(db, grant):
        db.commit()
        raise ConflictError("This grant has expired. Request access again if it is still needed.")
    if grant.status not in (GrantStatus.APPROVED.value, GrantStatus.ACTIVE.value):
        raise ConflictError(f"This grant is {grant.status}; only an approved grant can be entered.")
    org = _org(db, grant.organization_id)
    token, jti = create_grant_token(
        staff_id=actor.staff.id, organization_id=org.id, grant_id=grant.id, scopes=list(grant.scopes),
        platform_session_id=actor.session_id, grant_expires_at=_aware(grant.expires_at),
    )
    now = utcnow()
    first = grant.first_used_at is None
    grant.status = GrantStatus.ACTIVE.value
    grant.first_used_at = grant.first_used_at or now
    grant.last_entered_at = now
    grant.current_token_jti = jti
    _record(db, grant, platform_action=ENTERED, tenant_action=T_STARTED, actor=actor, details={"first_entry": first})
    db.commit()
    token_expiry = jwt.decode(token, options={"verify_signature": False})["exp"]
    return {
        "grant": to_dict(db, grant), "token": token,
        "token_expires_at": datetime.fromtimestamp(token_expiry, tz=timezone.utc),
        "organization": {"id": org.id, "name": org.name},
    }


# --- tenant side ------------------------------------------------------------------------------------------


def list_for_organization(db: Session, organization_id: str) -> List[Dict[str, Any]]:
    rows = db.scalars(select(TenantAccessGrant).where(TenantAccessGrant.organization_id == organization_id)
                      .order_by(TenantAccessGrant.created_at.desc()).limit(200)).all()
    sweep_expired(db, rows)
    return [to_dict(db, r) for r in rows]


def _tenant_grant(db: Session, organization_id: str, grant_id: str) -> TenantAccessGrant:
    grant = _grant(db, grant_id, lock=True)
    if grant.organization_id != organization_id:  # never another tenant's grant
        raise NotFoundError("Access grant not found.")
    return grant


def owner_approve(db: Session, organization_id: str, user: User, grant_id: str, *, ip: Optional[str], ua: Optional[str]):
    grant = _tenant_grant(db, organization_id, grant_id)
    if grant.is_emergency:
        raise ConflictError("Emergency access is approved by Rooman; you can revoke it at any time.")
    if _expire_if_due(db, grant):
        db.commit()
        raise ConflictError("This request has expired.")
    if grant.status != GrantStatus.PENDING.value:
        raise ConflictError(f"This request is {grant.status}.")
    now = utcnow()
    grant.status = GrantStatus.APPROVED.value
    grant.approved_at, grant.approved_by_user_id = now, user.id
    grant.expires_at = now + timedelta(minutes=grant.requested_duration_minutes)
    _record(db, grant, platform_action=APPROVED, tenant_action=T_APPROVED, actor=None, tenant_actor_user=user, ip=ip,
            user_agent=ua)
    db.commit()
    return to_dict(db, grant)


def owner_deny(db: Session, organization_id: str, user: User, grant_id: str, reason: Optional[str], *, ip, ua):
    grant = _tenant_grant(db, organization_id, grant_id)
    if grant.status != GrantStatus.PENDING.value:
        raise ConflictError(f"This request is {grant.status}.")
    grant.status = GrantStatus.DENIED.value
    grant.denied_at, grant.denied_by_user_id = utcnow(), user.id
    grant.denied_reason = _clean(reason)[:300] or None
    _record(db, grant, platform_action=DENIED, tenant_action=T_DENIED, actor=None, tenant_actor_user=user,
            reason=grant.denied_reason, ip=ip, user_agent=ua)
    db.commit()
    return to_dict(db, grant)


def tenant_revoke(db: Session, organization_id: str, user: User, grant_id: str, reason: Optional[str], *, ip, ua):
    grant = _tenant_grant(db, organization_id, grant_id)
    if grant.status not in (GrantStatus.APPROVED.value, GrantStatus.ACTIVE.value, GrantStatus.PENDING.value):
        raise ConflictError(f"This grant is already {grant.status}.")
    grant.status = GrantStatus.REVOKED.value
    grant.revoked_at, grant.revoked_by_kind, grant.revoked_by_id = utcnow(), "tenant_user", user.id
    grant.revoke_reason = _clean(reason)[:300] or None
    grant.current_token_jti = None
    _record(db, grant, platform_action=REVOKED, tenant_action=T_REVOKED, actor=None, tenant_actor_user=user,
            reason=grant.revoke_reason, details={"requests": grant.request_count}, ip=ip, user_agent=ua)
    db.commit()
    return to_dict(db, grant)


def active_grants_for_banner(db: Session, organization_id: str) -> List[Dict[str, Any]]:
    rows = db.scalars(select(TenantAccessGrant).where(
        TenantAccessGrant.organization_id == organization_id,
        TenantAccessGrant.status.in_([s.value for s in (GrantStatus.APPROVED, GrantStatus.ACTIVE)]),
    )).all()
    sweep_expired(db, rows)
    return [to_dict(db, r) for r in rows if r.status in (GrantStatus.APPROVED.value, GrantStatus.ACTIVE.value)]


# --- per-request authentication under a grant ---------------------------------------------------------------


def authenticate(db: Session, token: str, *, method: str, route_template: Optional[str],
                 path_params: Dict[str, Any], ip: Optional[str], ua: Optional[str], enforce_scope: bool = True) -> GrantPrincipal:
    """Validate a grant token and the request against the live grant. Every failure is a 401/403
    and, once the grant is known, is audited on both sides."""
    try:
        payload = decode_grant_token(token)
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Platform access has expired.")
    except jwt.PyJWTError:
        raise UnauthorizedError("Platform access token is invalid.")
    grant = db.get(TenantAccessGrant, payload["gid"])
    if grant is None or grant.organization_id != payload["org"] or grant.requested_by_staff_id != payload["sub"]:
        raise UnauthorizedError("Platform access token is invalid.")
    if _expire_if_due(db, grant):
        db.commit()
        raise UnauthorizedError("Platform access has expired.")
    if grant.status not in (GrantStatus.APPROVED.value, GrantStatus.ACTIVE.value) or grant.current_token_jti != payload["jti"]:
        raise UnauthorizedError("Platform access has ended.")
    staff = db.get(PlatformStaff, grant.requested_by_staff_id)
    session = db.get(PlatformSession, payload["psid"])
    if staff is None or not staff.is_active or not platform_auth_service._session_usable(session, staff, utcnow()):
        raise UnauthorizedError("Platform access has ended.")
    org = _org(db, grant.organization_id)
    principal = GrantPrincipal(grant=grant, staff=staff, organization=org, scopes=tuple(grant.scopes))
    if not enforce_scope:
        return principal
    scope = required_scope(method, route_template)
    ids = {k: str(v)[:64] for k, v in (path_params or {}).items()}
    if scope is None or scope.value not in grant.scopes:
        detail = {"method": method, "route": route_template, "needed": scope.value if scope else None, "ids": ids}
        _record(db, grant, platform_action=ACCESS_DENIED, tenant_action=T_REFUSED, actor=None,
                result=platform_audit.DENIED, tenant_actor_label=principal.actor_label, details=detail, ip=ip, user_agent=ua)
        db.commit()
        raise ForbiddenError("This is not available under the platform access you were granted.")
    grant.request_count = (grant.request_count or 0) + 1
    detail = {"method": method, "route": route_template, "scope": scope.value, "ids": ids}
    # One row per request, in the platform audit AND the tenant's own audit log.
    platform_audit.record(
        db, action=DATA_ACCESSED, result=platform_audit.SUCCESS, staff=staff, session_id=payload["psid"],
        ip_address=ip, user_agent=ua, organization=org, target_type="access_grant", target_id=grant.id,
        ticket_ref=grant.ticket_ref, details=detail,
    )
    audit.record(
        db, action=T_VIEWED, entity_type="platform_access_grant", entity_id=grant.id,
        entity_label=SCOPE_LABELS.get(scope, scope.value), organization_id=org.id, actor_label=principal.actor_label,
        after=_tenant_after(grant, staff, **detail), ip_address=ip, user_agent=ua,
    )
    db.commit()
    principal.route_scope = scope.value
    return principal


def exit_grant(db: Session, principal: GrantPrincipal, *, ip: Optional[str], ua: Optional[str]) -> None:
    grant = _grant(db, principal.grant.id, lock=True)
    grant.current_token_jti = None
    _record(db, grant, platform_action=EXITED, tenant_action=T_ENDED, actor=None,
            tenant_actor_label=principal.actor_label, details={"requests": grant.request_count}, ip=ip, user_agent=ua)
    db.commit()

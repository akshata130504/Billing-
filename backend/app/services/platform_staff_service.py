"""Platform staff administration from the console (Platform Administrator only).

Read: staff directory with role, active state, 2FA enrolment, last sign-in, live session count and
whether sign-in is currently throttled; per-person session metadata. Never passwords, TOTP
secrets, refresh-token hashes or any other credential.

Write: deactivate / reactivate a staff member and revoke their sessions. Creating staff, changing
roles and resetting 2FA stay with the server-side bootstrap CLI (backend/app/cli/platform_staff.py)
- there is deliberately no HTTP endpoint that creates platform staff.

Guard rails: nobody deactivates themselves, and the last active Platform Administrator cannot be
deactivated (the console would otherwise lock itself out). Every action is audited with the
ACTING staff member as the actor and the subject as the target.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import ConflictError, NotFoundError
from backend.app.models.base import utcnow
from backend.app.models.platform import PlatformRole, PlatformSession, PlatformStaff
from backend.app.services import platform_audit, platform_auth_service
from backend.app.services.auth_service import throttle_is_locked
from backend.app.services.platform_org_service import Actor


def _get(db: Session, staff_id: str, *, lock: bool = False) -> PlatformStaff:
    stmt = select(PlatformStaff).where(PlatformStaff.id == staff_id)
    if lock:
        stmt = stmt.with_for_update()
    staff = db.scalars(stmt).first()
    if staff is None:
        raise NotFoundError("Platform staff member not found.")
    return staff


def _live_sessions(db: Session, staff: PlatformStaff) -> List[PlatformSession]:
    return platform_auth_service.active_sessions(db, staff)


def _summary(db: Session, staff: PlatformStaff) -> Dict[str, Any]:
    return {
        "id": staff.id,
        "email": staff.email,
        "full_name": staff.full_name,
        "role": staff.role.value,
        "is_active": bool(staff.is_active),
        "deactivated_at": staff.deactivated_at,
        "two_factor_enrolled": staff.totp_enabled_at is not None,
        "last_login_at": staff.last_login_at,
        "created_at": staff.created_at,
        "active_sessions": len(_live_sessions(db, staff)) if staff.is_active else 0,
        "sign_in_locked": bool(throttle_is_locked(db, platform_auth_service.MFA_SCOPE, staff.id, None)),
    }


def list_staff(db: Session) -> List[Dict[str, Any]]:
    rows = db.scalars(select(PlatformStaff).order_by(PlatformStaff.is_active.desc(), PlatformStaff.full_name)).all()
    return [_summary(db, s) for s in rows]


def staff_detail(db: Session, staff_id: str, actor: Actor) -> Dict[str, Any]:
    staff = _get(db, staff_id)
    sessions = _live_sessions(db, staff) if staff.is_active else []
    return {
        **_summary(db, staff),
        "is_self": staff.id == actor.staff.id,
        "sessions": [
            {
                "id": s.id,
                "created_at": s.created_at,
                "last_used_at": s.last_used_at,
                "expires_at": s.expires_at,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "current": s.id == actor.session_id,
            }
            for s in sessions
        ],
    }


def _active_administrators(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count(PlatformStaff.id)).where(
                PlatformStaff.role == PlatformRole.PLATFORM_ADMINISTRATOR, PlatformStaff.is_active.is_(True)
            )
        )
        or 0
    )


def _audit(db: Session, actor: Actor, action: str, target: PlatformStaff, *, reason: Optional[str] = None,
           result: str = platform_audit.SUCCESS, details: Optional[Dict[str, Any]] = None) -> None:
    platform_audit.record(
        db, action=action, result=result, staff=actor.staff, session_id=actor.session_id,
        ip_address=actor.ip_address, user_agent=actor.user_agent, target_type="platform_staff",
        target_id=target.id, reason=reason, details={"target_email": target.email, **(details or {})},
    )


def _refuse(db: Session, actor: Actor, target: PlatformStaff, action: str, message: str, reason: str) -> None:
    _audit(db, actor, action, target, reason=reason, result=platform_audit.DENIED, details={"refused": message})
    db.commit()
    raise ConflictError(message)


def deactivate(db: Session, staff_id: str, actor: Actor, *, reason: str) -> Dict[str, Any]:
    reason = " ".join((reason or "").split())
    target = _get(db, staff_id, lock=True)
    if target.id == actor.staff.id:
        _refuse(db, actor, target, platform_audit.STAFF_DEACTIVATED, "You cannot deactivate your own account.", reason)
    if not target.is_active:
        _refuse(db, actor, target, platform_audit.STAFF_DEACTIVATED, "This staff member is already deactivated.", reason)
    if target.role == PlatformRole.PLATFORM_ADMINISTRATOR and _active_administrators(db) <= 1:
        _refuse(db, actor, target, platform_audit.STAFF_DEACTIVATED,
                "The last active Platform Administrator cannot be deactivated.", reason)
    target.is_active = False
    target.deactivated_at = utcnow()
    revoked = platform_auth_service.revoke_all_sessions(db, target, "staff_deactivated")
    _audit(db, actor, platform_audit.STAFF_DEACTIVATED, target, reason=reason, details={"sessions_revoked": revoked})
    db.commit()
    return _summary(db, target)


def activate(db: Session, staff_id: str, actor: Actor, *, reason: str) -> Dict[str, Any]:
    reason = " ".join((reason or "").split())
    target = _get(db, staff_id, lock=True)
    if target.is_active:
        _refuse(db, actor, target, platform_audit.STAFF_ACTIVATED, "This staff member is already active.", reason)
    target.is_active = True
    target.deactivated_at = None
    # Anything issued before re-activation stays dead: a fresh sign-in (with TOTP) is required.
    target.tokens_valid_after = utcnow()
    _audit(db, actor, platform_audit.STAFF_ACTIVATED, target, reason=reason)
    db.commit()
    return _summary(db, target)


def revoke_sessions(db: Session, staff_id: str, actor: Actor, *, reason: str) -> Dict[str, Any]:
    reason = " ".join((reason or "").split())
    target = _get(db, staff_id, lock=True)
    revoked = platform_auth_service.revoke_all_sessions(db, target, "revoked_by_administrator")
    _audit(db, actor, platform_audit.STAFF_SESSIONS_REVOKED, target, reason=reason,
           details={"sessions_revoked": revoked, "self": target.id == actor.staff.id})
    db.commit()
    return {**_summary(db, target), "sessions_revoked": revoked}

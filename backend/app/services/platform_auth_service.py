"""Platform staff authentication (Rooman staff) - separate from tenant authentication.

Sign-in is always two steps and 2FA is mandatory:

1. login(email, password)      -> a single-use, short-lived login challenge (nothing else)
2. verify_2fa(challenge, code) -> a PlatformSession + short-lived platform access token

A staff member without an enrolled TOTP secret can never complete step 2, so password alone never
authenticates. Failures are throttled per (email, IP) for passwords and per account for codes,
re-using the tenant throttle table under separate "platform_*" scopes; answers never reveal
whether an email belongs to platform staff. Every security event is written to the platform audit
log (services/platform_audit.py). Tenant users, memberships and tenant tokens are never involved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.core.alerts import send_alert
from backend.app.core.config import settings
from backend.app.core.exceptions import (
    AppException,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationAppError,
)
from backend.app.core.platform_security import (
    PlatformAuthNotConfigured,
    create_platform_access_token,
    decode_platform_access_token,
)
from backend.app.core.redaction import mask_email
from backend.app.core.security import (
    decrypt_secret,
    encrypt_secret,
    generate_opaque_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from backend.app.core.totp import generate_totp_secret, provisioning_uri, verify_totp
from backend.app.models.base import utcnow
from backend.app.models.platform import PlatformLoginChallenge, PlatformRole, PlatformSession, PlatformStaff
from backend.app.services import platform_audit
from backend.app.services.auth_service import (
    LOCKOUT_MINUTES,
    MAX_FAILED_LOGINS,
    _dummy_password_hash,
    throttle_clear,
    throttle_is_locked,
    throttle_register_failure,
)

LOGIN_SCOPE = "platform_login"  # per (normalised email, client IP)
MFA_SCOPE = "platform_mfa"  # per staff account
MAX_CHALLENGE_ATTEMPTS = 3
PLATFORM_MIN_PASSWORD_LENGTH = 14
TOTP_ISSUER = "Rooman Billing Platform"

INVALID_CREDENTIALS = "Invalid email or password."
TOO_MANY_ATTEMPTS = "Too many failed sign-in attempts. Please wait a few minutes and try again."
CHALLENGE_INVALID = "This sign-in attempt is invalid or has expired. Please sign in again."
INVALID_CODE = "The authentication code is invalid or has already been used."
SESSION_INVALID = "Your platform session has ended. Please sign in again."
STEP_UP_REQUIRED_MESSAGE = "Confirm it's you with a fresh authenticator code to continue."
STEP_UP_INVALID_CODE = "The authentication code is invalid or has already been used."
# Hard ceiling on a step-up's lifetime, whatever PLATFORM_STEP_UP_MINUTES says (config also refuses
# larger values at startup).
MAX_STEP_UP_MINUTES = 15


class PlatformAuthDisabledError(AppException):
    def __init__(self) -> None:
        super().__init__(
            message="Platform sign-in is not configured on this server.",
            code="PLATFORM_AUTH_DISABLED",
            status_code=503,
        )


class StepUpRequiredError(AppException):
    """A sensitive platform action needs a recent step-up on the current session."""

    def __init__(self) -> None:
        super().__init__(message=STEP_UP_REQUIRED_MESSAGE, code="STEP_UP_REQUIRED", status_code=403)


class StepUpFailedError(AppException):
    """A step-up code was wrong or replayed. 403, not 401: the session itself is still valid."""

    def __init__(self, message: str = STEP_UP_INVALID_CODE, *, throttled: bool = False) -> None:
        super().__init__(
            message=TOO_MANY_ATTEMPTS if throttled else message,
            code="TOO_MANY_ATTEMPTS" if throttled else "STEP_UP_FAILED",
            status_code=429 if throttled else 403,
        )


def ensure_enabled() -> None:
    if not settings.platform_auth_enabled:
        raise PlatformAuthDisabledError()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()[:255]


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _locked(db: Session, model, row_id: str):
    stmt = select(model).where(model.id == row_id)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    return db.scalars(stmt).first()


def _can_sign_in(staff: Optional[PlatformStaff]) -> bool:
    return bool(staff and staff.is_active and staff.totp_enabled_at is not None and staff.totp_secret)


# --- step 1: password -------------------------------------------------------------------------------


@dataclass
class LoginChallengeIssued:
    challenge_token: str
    expires_in: int


def login(db: Session, email: str, password: str, ip: Optional[str], user_agent: Optional[str]) -> LoginChallengeIssued:
    ensure_enabled()
    email = normalize_email(email)
    staff = db.scalars(select(PlatformStaff).where(PlatformStaff.email == email)).first()

    if throttle_is_locked(db, LOGIN_SCOPE, email, ip):
        platform_audit.record(
            db, action=platform_audit.LOGIN_FAILED, result=platform_audit.DENIED, staff=staff, email=email,
            ip_address=ip, user_agent=user_agent, details={"reason": "throttled"},
        )
        db.commit()
        raise UnauthorizedError(TOO_MANY_ATTEMPTS)

    # Always pay the bcrypt cost so timing does not reveal whether the email is platform staff.
    stored = staff.hashed_password if staff is not None else _dummy_password_hash()
    password_ok = verify_password(password or "", stored) and staff is not None

    if not password_ok or not _can_sign_in(staff):
        if staff is None:
            reason = "unknown_email"
        elif not password_ok:
            reason = "bad_password"
        elif not staff.is_active:
            reason = "inactive"
        else:
            reason = "two_factor_not_enrolled"
        blocked = throttle_register_failure(db, LOGIN_SCOPE, email, ip)
        platform_audit.record(
            db, action=platform_audit.LOGIN_FAILED, result=platform_audit.FAILURE, staff=staff, email=email,
            ip_address=ip, user_agent=user_agent, details={"reason": reason, "locked": blocked},
        )
        if blocked:
            platform_audit.record(
                db, action=platform_audit.ACCOUNT_LOCKED, result=platform_audit.DENIED, staff=staff, email=email,
                ip_address=ip, user_agent=user_agent,
                details={"scope": LOGIN_SCOPE, "locked_minutes": LOCKOUT_MINUTES, "after_failures": MAX_FAILED_LOGINS},
            )
        db.commit()
        if blocked:
            send_alert(
                "platform.auth.repeated_failures",
                "Platform sign-in throttle tripped",
                {"scope": LOGIN_SCOPE, "account": mask_email(email), "client_ip": ip or "unknown"},
                severity="warning",
                dedup_key=f"platform.auth.repeated_failures:{hash_token(email)[:16]}:{ip or ''}",
            )
        raise UnauthorizedError(TOO_MANY_ATTEMPTS if blocked else INVALID_CREDENTIALS)

    throttle_clear(db, LOGIN_SCOPE, email, ip)
    now = utcnow()
    # One outstanding challenge per staff member: starting a new sign-in voids older ones.
    db.execute(
        update(PlatformLoginChallenge)
        .where(PlatformLoginChallenge.staff_id == staff.id, PlatformLoginChallenge.consumed_at.is_(None))
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    token = generate_opaque_token()
    minutes = settings.PLATFORM_LOGIN_CHALLENGE_MINUTES
    challenge = PlatformLoginChallenge(
        staff_id=staff.id,
        token_hash=hash_token(token),
        created_at=now,
        expires_at=now + timedelta(minutes=minutes),
        failed_attempts=0,
        ip_address=(ip or None) and ip[:64],
        user_agent=(user_agent or None) and user_agent[:400],
    )
    db.add(challenge)
    platform_audit.record(
        db, action=platform_audit.LOGIN_PASSWORD_VERIFIED, result=platform_audit.SUCCESS, staff=staff,
        ip_address=ip, user_agent=user_agent, details={"next_step": "totp"},
    )
    db.commit()
    return LoginChallengeIssued(challenge_token=token, expires_in=minutes * 60)


# --- step 2: TOTP -> session ------------------------------------------------------------------------


@dataclass
class EstablishedSession:
    staff: PlatformStaff
    session: PlatformSession
    refresh_secret: str
    access_token: str


def verify_2fa(
    db: Session, challenge_token: str, code: str, ip: Optional[str], user_agent: Optional[str]
) -> EstablishedSession:
    ensure_enabled()
    now = utcnow()
    found = db.scalars(
        select(PlatformLoginChallenge).where(PlatformLoginChallenge.token_hash == hash_token(challenge_token or ""))
    ).first()
    challenge = _locked(db, PlatformLoginChallenge, found.id) if found is not None else None
    staff = db.get(PlatformStaff, challenge.staff_id) if challenge is not None else None

    def fail(message: str, reason: str, *, count: bool = False) -> None:
        blocked = False
        if count and staff is not None:
            challenge.failed_attempts = (challenge.failed_attempts or 0) + 1
            if challenge.failed_attempts >= MAX_CHALLENGE_ATTEMPTS:
                challenge.consumed_at = now
            blocked = throttle_register_failure(db, MFA_SCOPE, staff.id, None)
        platform_audit.record(
            db, action=platform_audit.TWO_FACTOR_FAILED, result=platform_audit.FAILURE, staff=staff,
            ip_address=ip, user_agent=user_agent, details={"reason": reason, "locked": blocked},
        )
        if blocked:
            platform_audit.record(
                db, action=platform_audit.ACCOUNT_LOCKED, result=platform_audit.DENIED, staff=staff,
                ip_address=ip, user_agent=user_agent, details={"scope": MFA_SCOPE, "locked_minutes": LOCKOUT_MINUTES},
            )
        db.commit()
        raise UnauthorizedError(TOO_MANY_ATTEMPTS if blocked else message)

    if challenge is None or challenge.consumed_at is not None or (_aware(challenge.expires_at) or now) <= now:
        fail(CHALLENGE_INVALID, "invalid_or_expired_challenge")
    if not _can_sign_in(staff):
        challenge.consumed_at = now
        fail(CHALLENGE_INVALID, "staff_cannot_sign_in")
    if throttle_is_locked(db, MFA_SCOPE, staff.id, None):
        fail(TOO_MANY_ATTEMPTS, "throttled")

    secret = decrypt_secret(staff.totp_secret)
    step = verify_totp(secret, (code or "").strip()) if secret else None
    if step is None or (staff.totp_last_used_step is not None and step <= staff.totp_last_used_step):
        fail(INVALID_CODE, "bad_or_replayed_code", count=True)

    challenge.consumed_at = now
    staff.totp_last_used_step = step
    staff.last_login_at = now
    throttle_clear(db, MFA_SCOPE, staff.id)
    session, refresh_secret = _create_session(db, staff, ip, user_agent, now)
    platform_audit.record(
        db, action=platform_audit.TWO_FACTOR_SUCCEEDED, result=platform_audit.SUCCESS, staff=staff,
        session_id=session.id, ip_address=ip, user_agent=user_agent, details={"method": "totp"},
    )
    platform_audit.record(
        db, action=platform_audit.LOGIN_SUCCEEDED, result=platform_audit.SUCCESS, staff=staff,
        session_id=session.id, ip_address=ip, user_agent=user_agent, details={"role": staff.role.value},
    )
    db.commit()
    access = create_platform_access_token(
        staff_id=staff.id, session_id=session.id, role=staff.role.value, auth_time=now
    )
    return EstablishedSession(staff=staff, session=session, refresh_secret=refresh_secret, access_token=access)


def _create_session(
    db: Session, staff: PlatformStaff, ip: Optional[str], user_agent: Optional[str], now: datetime
) -> Tuple[PlatformSession, str]:
    secret = generate_opaque_token()
    expires = now + timedelta(hours=settings.PLATFORM_SESSION_MAX_HOURS)
    session = PlatformSession(
        staff_id=staff.id,
        refresh_token_hash=hash_token(secret),
        created_at=now,
        last_used_at=now,
        idle_expires_at=min(now + timedelta(minutes=settings.PLATFORM_SESSION_IDLE_MINUTES), expires),
        expires_at=expires,
        mfa_verified_at=now,
        ip_address=(ip or None) and ip[:64],
        user_agent=(user_agent or None) and user_agent[:400],
    )
    db.add(session)
    db.flush()
    return session, secret


def _session_usable(session: Optional[PlatformSession], staff: Optional[PlatformStaff], now: datetime) -> bool:
    if session is None or staff is None or session.staff_id != staff.id:
        return False
    if session.revoked_at is not None:
        return False
    if (_aware(session.expires_at) or now) <= now or (_aware(session.idle_expires_at) or now) <= now:
        return False
    if not _can_sign_in(staff):
        return False
    valid_after = _aware(staff.tokens_valid_after)
    if valid_after is not None and (_aware(session.created_at) or now) < valid_after:
        return False
    return True


# --- refresh --------------------------------------------------------------------------------------------


def refresh(db: Session, refresh_secret: str, ip: Optional[str], user_agent: Optional[str]) -> EstablishedSession:
    """Rotate the refresh secret and issue a new access token. A secret that was already rotated
    away is treated as stolen: the whole session is revoked."""
    ensure_enabled()
    now = utcnow()
    digest = hash_token(refresh_secret or "")
    found = db.scalars(select(PlatformSession).where(PlatformSession.refresh_token_hash == digest)).first()
    if found is None:
        reused = db.scalars(
            select(PlatformSession).where(PlatformSession.previous_refresh_token_hash == digest)
        ).first()
        if reused is not None:
            reused = _locked(db, PlatformSession, reused.id)
            staff = db.get(PlatformStaff, reused.staff_id)
            if reused.revoked_at is None:
                reused.revoked_at = now
                reused.revoke_reason = "refresh_reuse_detected"
            reused.step_up_expires_at = None
            platform_audit.record(
                db, action=platform_audit.REFRESH_REUSE_DETECTED, result=platform_audit.DENIED, staff=staff,
                session_id=reused.id, ip_address=ip, user_agent=user_agent,
            )
            db.commit()
            send_alert(
                "platform.auth.refresh_reuse",
                "A rotated platform refresh token was presented again; the session was revoked",
                {"session_id": reused.id},
                severity="warning",
                dedup_key=f"platform.auth.refresh_reuse:{reused.id}",
            )
        raise UnauthorizedError(SESSION_INVALID)

    session = _locked(db, PlatformSession, found.id)
    staff = db.get(PlatformStaff, session.staff_id)
    if session.refresh_token_hash != digest or not _session_usable(session, staff, now):
        db.rollback()
        raise UnauthorizedError(SESSION_INVALID)

    new_secret = generate_opaque_token()
    session.previous_refresh_token_hash = session.refresh_token_hash
    session.refresh_token_hash = hash_token(new_secret)
    session.last_used_at = now
    session.idle_expires_at = min(now + timedelta(minutes=settings.PLATFORM_SESSION_IDLE_MINUTES), _aware(session.expires_at))
    db.commit()
    access = create_platform_access_token(
        staff_id=staff.id, session_id=session.id, role=staff.role.value, auth_time=_aware(session.mfa_verified_at)
    )
    return EstablishedSession(staff=staff, session=session, refresh_secret=new_secret, access_token=access)


# --- per-request authentication ------------------------------------------------------------------------


def authenticate(db: Session, access_token: str) -> Tuple[PlatformStaff, PlatformSession]:
    """Resolve a platform access token to an active staff member and live session, or raise."""
    ensure_enabled()
    try:
        payload = decode_platform_access_token(access_token)
    except PlatformAuthNotConfigured:
        raise PlatformAuthDisabledError()
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Platform access token has expired.")
    except jwt.PyJWTError:
        raise UnauthorizedError("Platform access token is invalid.")
    now = utcnow()
    staff = db.get(PlatformStaff, payload["sub"])
    session = db.get(PlatformSession, payload["sid"])
    if not _session_usable(session, staff, now):
        raise UnauthorizedError(SESSION_INVALID)
    valid_after = _aware(staff.tokens_valid_after)
    iat = payload.get("iat")
    if valid_after is not None and (
        not isinstance(iat, (int, float)) or datetime.fromtimestamp(iat, tz=timezone.utc) < valid_after
    ):
        raise UnauthorizedError(SESSION_INVALID)
    return staff, session


# --- logout / sessions -----------------------------------------------------------------------------------


def active_sessions(db: Session, staff: PlatformStaff) -> List[PlatformSession]:
    now = utcnow()
    rows = db.scalars(
        select(PlatformSession)
        .where(PlatformSession.staff_id == staff.id, PlatformSession.revoked_at.is_(None))
        .order_by(PlatformSession.created_at.desc())
    ).all()
    return [s for s in rows if _session_usable(s, staff, now)]


def logout(db: Session, staff: PlatformStaff, session: PlatformSession, ip: Optional[str], user_agent: Optional[str]) -> None:
    session = _locked(db, PlatformSession, session.id)
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        session.revoke_reason = "logout"
    session.step_up_expires_at = None
    platform_audit.record(
        db, action=platform_audit.LOGOUT, result=platform_audit.SUCCESS, staff=staff, session_id=session.id,
        ip_address=ip, user_agent=user_agent,
    )
    db.commit()


def revoke_session(
    db: Session, staff: PlatformStaff, current: PlatformSession, session_id: str, ip: Optional[str], user_agent: Optional[str]
) -> None:
    """Revoke one of the caller's OWN sessions (another staff member's id is simply not found)."""
    target = db.get(PlatformSession, session_id)
    if target is None or target.staff_id != staff.id:
        raise NotFoundError("Session not found.")
    target = _locked(db, PlatformSession, target.id)
    if target.revoked_at is None:
        target.revoked_at = utcnow()
        target.revoke_reason = "revoked_by_owner"
    target.step_up_expires_at = None
    platform_audit.record(
        db, action=platform_audit.SESSION_REVOKED, result=platform_audit.SUCCESS, staff=staff, session_id=current.id,
        ip_address=ip, user_agent=user_agent, details={"revoked_session_id": target.id},
    )
    db.commit()


def _revoke_all(db: Session, staff: PlatformStaff, reason: str) -> int:
    now = utcnow()
    result = db.execute(
        update(PlatformSession)
        .where(PlatformSession.staff_id == staff.id, PlatformSession.revoked_at.is_(None))
        .values(revoked_at=now, revoke_reason=reason, step_up_expires_at=None)
        .execution_options(synchronize_session=False)
    )
    staff.tokens_valid_after = now
    return int(result.rowcount or 0)


def logout_all(db: Session, staff: PlatformStaff, current: PlatformSession, ip: Optional[str], user_agent: Optional[str]) -> int:
    count = _revoke_all(db, staff, "logout_all")
    platform_audit.record(
        db, action=platform_audit.ALL_SESSIONS_REVOKED, result=platform_audit.SUCCESS, staff=staff,
        session_id=current.id, ip_address=ip, user_agent=user_agent, details={"sessions_revoked": count},
    )
    db.commit()
    return count


# --- step-up re-authentication ------------------------------------------------------------------------


def step_up_minutes() -> int:
    return max(1, min(int(settings.PLATFORM_STEP_UP_MINUTES), MAX_STEP_UP_MINUTES))


def step_up(
    db: Session, staff: PlatformStaff, session: PlatformSession, code: str, ip: Optional[str], user_agent: Optional[str]
) -> datetime:
    """Record a fresh TOTP confirmation on THIS session; returns when it lapses.

    The code is checked exactly like the sign-in second step: replay-protected (a code, or an older
    one, can never be used twice - including one already used to sign in) and throttled on the same
    per-account MFA budget, so step-up adds no extra guesses. Each success starts a new, fixed
    window; nothing ever extends an existing one. Issues no token of any kind.
    """
    ensure_enabled()
    now = utcnow()
    staff = _locked(db, PlatformStaff, staff.id)
    session = _locked(db, PlatformSession, session.id)
    if not _session_usable(session, staff, now):
        db.rollback()
        raise UnauthorizedError(SESSION_INVALID)

    def fail(reason: str, *, count: bool) -> None:
        blocked = throttle_register_failure(db, MFA_SCOPE, staff.id, None) if count else False
        platform_audit.record(
            db, action=platform_audit.STEP_UP_FAILED, result=platform_audit.FAILURE, staff=staff,
            session_id=session.id, ip_address=ip, user_agent=user_agent, details={"reason": reason, "locked": blocked},
        )
        if blocked:
            platform_audit.record(
                db, action=platform_audit.ACCOUNT_LOCKED, result=platform_audit.DENIED, staff=staff,
                session_id=session.id, ip_address=ip, user_agent=user_agent,
                details={"scope": MFA_SCOPE, "locked_minutes": LOCKOUT_MINUTES},
            )
        db.commit()
        raise StepUpFailedError(throttled=blocked or reason == "throttled")

    if throttle_is_locked(db, MFA_SCOPE, staff.id, None):
        fail("throttled", count=False)
    secret = decrypt_secret(staff.totp_secret)
    step = verify_totp(secret, (code or "").strip()) if secret else None
    if step is None or (staff.totp_last_used_step is not None and step <= staff.totp_last_used_step):
        fail("bad_or_replayed_code", count=True)

    staff.totp_last_used_step = step
    throttle_clear(db, MFA_SCOPE, staff.id)
    expires = min(now + timedelta(minutes=step_up_minutes()), _aware(session.expires_at))
    session.step_up_at = now
    session.step_up_expires_at = expires
    platform_audit.record(
        db, action=platform_audit.STEP_UP_SUCCEEDED, result=platform_audit.SUCCESS, staff=staff,
        session_id=session.id, ip_address=ip, user_agent=user_agent,
        details={"method": "totp", "valid_seconds": int((expires - now).total_seconds())},
    )
    db.commit()
    return expires


def has_recent_step_up(staff: PlatformStaff, session: PlatformSession, now: Optional[datetime] = None) -> bool:
    """True only if THIS live session completed a step-up recently enough.

    The window is re-derived from step_up_at with the current (capped) setting, so lowering
    PLATFORM_STEP_UP_MINUTES shortens windows already granted and nothing can lengthen one. Any
    revocation of the session, and anything that moves staff.tokens_valid_after (logout-all,
    password reset, 2FA reset), ends it.
    """
    now = now or utcnow()
    if not _session_usable(session, staff, now):
        return False
    at, expires = _aware(session.step_up_at), _aware(session.step_up_expires_at)
    if at is None or expires is None or at > now:
        return False
    if now >= min(expires, at + timedelta(minutes=step_up_minutes()), _aware(session.expires_at)):
        return False
    valid_after = _aware(staff.tokens_valid_after)
    if valid_after is not None and at < valid_after:
        return False
    return True


# --- staff management (server-side bootstrap CLI only; there is no HTTP endpoint for this) --------------


def _check_password(password: str) -> None:
    problem = validate_password_strength(password or "")
    if problem is None and len(password) < PLATFORM_MIN_PASSWORD_LENGTH:
        problem = f"Platform staff passwords must be at least {PLATFORM_MIN_PASSWORD_LENGTH} characters long."
    if problem:
        raise ValidationAppError(problem, {"fields": {"password": problem}})


@dataclass
class StaffEnrolment:
    staff: PlatformStaff
    totp_secret: str
    otpauth_uri: str


def create_staff(db: Session, *, email: str, full_name: str, role: PlatformRole, password: str, actor: str) -> StaffEnrolment:
    """Create an active staff member with TOTP already enrolled (mandatory 2FA from day one).

    The TOTP secret is returned once so the operator can load it into an authenticator app; only
    its encrypted form is stored."""
    email = normalize_email(email)
    if "@" not in email:
        raise ValidationAppError("A valid email is required.", {"fields": {"email": "invalid"}})
    if not (full_name or "").strip():
        raise ValidationAppError("A name is required.", {"fields": {"full_name": "required"}})
    _check_password(password)
    if db.scalars(select(PlatformStaff).where(PlatformStaff.email == email)).first() is not None:
        raise ConflictError("A platform staff member with this email already exists.")
    secret = generate_totp_secret()
    now = utcnow()
    staff = PlatformStaff(
        email=email,
        full_name=full_name.strip()[:200],
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
        totp_secret=encrypt_secret(secret),
        totp_enabled_at=now,
    )
    db.add(staff)
    db.flush()
    platform_audit.record(
        db, action=platform_audit.STAFF_CREATED, result=platform_audit.SUCCESS, staff=staff,
        details={"role": role.value, "actor": actor},
    )
    db.commit()
    return StaffEnrolment(staff=staff, totp_secret=secret, otpauth_uri=provisioning_uri(secret, email, TOTP_ISSUER))


def _staff_by_email(db: Session, email: str) -> PlatformStaff:
    staff = db.scalars(select(PlatformStaff).where(PlatformStaff.email == normalize_email(email))).first()
    if staff is None:
        raise NotFoundError("Platform staff member not found.")
    return staff


def deactivate_staff(db: Session, *, email: str, reason: str, actor: str) -> PlatformStaff:
    staff = _staff_by_email(db, email)
    staff.is_active = False
    staff.deactivated_at = utcnow()
    count = _revoke_all(db, staff, "staff_deactivated")
    platform_audit.record(
        db, action=platform_audit.STAFF_DEACTIVATED, result=platform_audit.SUCCESS, staff=staff,
        details={"reason": (reason or "")[:200], "actor": actor, "sessions_revoked": count},
    )
    db.commit()
    return staff


def activate_staff(db: Session, *, email: str, reason: str, actor: str) -> PlatformStaff:
    staff = _staff_by_email(db, email)
    staff.is_active = True
    staff.deactivated_at = None
    platform_audit.record(
        db, action=platform_audit.STAFF_ACTIVATED, result=platform_audit.SUCCESS, staff=staff,
        details={"reason": (reason or "")[:200], "actor": actor},
    )
    db.commit()
    return staff


def reset_two_factor(db: Session, *, email: str, reason: str, actor: str) -> StaffEnrolment:
    """Replace a lost authenticator: new secret, every existing session revoked."""
    staff = _staff_by_email(db, email)
    secret = generate_totp_secret()
    staff.totp_secret = encrypt_secret(secret)
    staff.totp_enabled_at = utcnow()
    staff.totp_last_used_step = None
    count = _revoke_all(db, staff, "two_factor_reset")
    platform_audit.record(
        db, action=platform_audit.TWO_FACTOR_RESET, result=platform_audit.SUCCESS, staff=staff,
        details={"reason": (reason or "")[:200], "actor": actor, "sessions_revoked": count},
    )
    db.commit()
    return StaffEnrolment(staff=staff, totp_secret=secret, otpauth_uri=provisioning_uri(secret, staff.email, TOTP_ISSUER))


def set_password(db: Session, *, email: str, password: str, actor: str) -> PlatformStaff:
    staff = _staff_by_email(db, email)
    _check_password(password)
    staff.hashed_password = hash_password(password)
    count = _revoke_all(db, staff, "password_reset")
    platform_audit.record(
        db, action=platform_audit.PASSWORD_RESET, result=platform_audit.SUCCESS, staff=staff,
        details={"actor": actor, "sessions_revoked": count},
    )
    db.commit()
    return staff

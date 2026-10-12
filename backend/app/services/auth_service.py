"""Authentication, sessions, password recovery and invitation acceptance.

Endpoints stay thin: everything that touches the database or decides an outcome
lives here. Every function that changes state commits its own transaction and
writes the matching audit row first.
"""
import hashlib
import hmac
import html
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import jwt
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.config import settings
from backend.app.core.exceptions import (
    AppException,
    ConflictError,
    EntityNotFoundError,
    ForbiddenError,
    UnauthorizedError,
    ValidationAppError,
)
from backend.app.core.alerts import send_alert
from backend.app.core.logging import logger
from backend.app.core.redaction import mask_email
from backend.app.core.security import (
    constant_time_equals,
    create_access_token,
    create_mfa_token,
    create_signup_verification_token,
    decode_mfa_token,
    decode_signup_verification_token,
    decrypt_secret,
    encrypt_secret,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_reset_expiry,
    refresh_token_expiry,
    validate_password_strength,
    verify_password,
)
from backend.app.core.totp import generate_totp_secret, provisioning_uri, verify_totp
from backend.app.models import (
    AuditStatus,
    Membership,
    MemberRole,
    MembershipStatus,
    Organization,
    OrganizationStatus,
    PasswordResetToken,
    PendingSignup,
    RefreshToken,
    User,
    utcnow,
)
from backend.app.models.identity import LoginThrottle
from backend.app.models.subscription_access import ModuleAccess
from backend.app.schemas.auth import (
    MeResponse,
    MembershipOut,
    OrganizationSummary,
    SignupVerificationRequest,
    UserOut,
)
from backend.app.schemas.organization import OrganizationOut, normalize_email
from backend.app.schemas.subscription_access import OrganizationAccess
from backend.app.services import audit, org_access
from backend.app.services.email import EmailDeliveryError, frontend_url, send_email

# Failed credential checks allowed per (email, client IP) - or per account for TOTP codes -
# inside THROTTLE_WINDOW_MINUTES before that key is blocked for LOCKOUT_MINUTES.
MAX_FAILED_LOGINS = 5
THROTTLE_WINDOW_MINUTES = 15
LOCKOUT_MINUTES = 15
INVALID_CREDENTIALS = "Invalid email or password."
# Deliberately identical for known and unknown emails so it never confirms an account exists.
TOO_MANY_ATTEMPTS = "Too many failed sign-in attempts. Please wait a few minutes and try again."
INVALID_MFA_CODE = "The authentication code is invalid or has already been used."
NOT_A_MEMBER = "You are not an active member of any organization."
OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
# How long a verified mailbox may take to choose a password and finish creating the organization.
SIGNUP_COMPLETION_MINUTES = 15
# An expired pending signup is kept this long (it can no longer be used) so a late code entry is
# told "expired" rather than "no pending signup", and a new code can be resent to it.
EXPIRED_PENDING_SIGNUP_RETENTION = timedelta(hours=24)


# --- helpers -------------------------------------------------------------------------


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes for DateTime(timezone=True); treat them as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ActorContext(CurrentContext):
    """A CurrentContext built by the service (no request dependency) that tolerates a
    missing organization, e.g. for password resets of users without a membership."""

    @property
    def organization_id(self) -> Optional[str]:  # type: ignore[override]
        return self.organization.id if self.organization is not None else None


def make_ctx(
    user: User,
    organization: Optional[Organization],
    membership: Optional[Membership],
    ip: Optional[str],
    user_agent: Optional[str],
) -> ActorContext:
    return ActorContext(
        user=user,
        organization=organization,  # type: ignore[arg-type]
        membership=membership,  # type: ignore[arg-type]
        ip_address=ip,
        user_agent=(user_agent or "")[:400] or None,
    )


_dummy_hash: Optional[str] = None


def _dummy_password_hash() -> str:
    """A real bcrypt hash we verify against for unknown emails so timing does not leak existence."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(generate_opaque_token())
    return _dummy_hash


def _password_problem(password: Optional[str], field: str = "password") -> None:
    problem = validate_password_strength(password or "")
    if problem:
        raise ValidationAppError(problem, {"fields": {field: problem}})


def _commit(db: Session, conflict_message: str = "The request conflicts with existing data.") -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Integrity error committing auth transaction: %s", exc.orig)
        raise ConflictError(conflict_message) from exc


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:70].strip("-") or "org"


def unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    taken = set(db.scalars(select(Organization.slug).where(Organization.slug.like(f"{base}%"))).all())
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalars(select(User).where(User.email == normalize_email(email))).first()


def pick_membership(db: Session, user_id: str, organization_id: Optional[str] = None) -> Optional[Membership]:
    """The user's active membership for `organization_id`, else the most recently created one."""
    stmt = select(Membership).where(
        Membership.user_id == user_id,
        Membership.status == MembershipStatus.ACTIVE,
    )
    if organization_id:
        stmt = stmt.where(Membership.organization_id == organization_id)
    return db.scalars(stmt.order_by(Membership.created_at.desc(), Membership.id)).first()


def revoke_refresh_tokens(
    db: Session,
    user_id: str,
    *,
    organization_id: Optional[str] = None,
    keep_token_hash: Optional[str] = None,
) -> int:
    """Revoke every live refresh token of a user (optionally only for one organization)."""
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    if organization_id:
        stmt = stmt.where(RefreshToken.organization_id == organization_id)
    if keep_token_hash:
        stmt = stmt.where(RefreshToken.token_hash != keep_token_hash)
    return db.execute(stmt).rowcount or 0


# --- tokens ---------------------------------------------------------------------------


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_in: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": "bearer",
            "expires_in": self.expires_in,
        }


def issue_tokens(
    db: Session,
    user: User,
    membership: Membership,
    ip: Optional[str],
    user_agent: Optional[str],
) -> Tuple[TokenBundle, RefreshToken]:
    """Create an access token + a persisted refresh token row (caller commits).

    The access token carries the refresh row id as `sid`, so revoking that session
    (DELETE /auth/sessions/{id}) also invalidates its access token.
    """
    raw = generate_opaque_token()
    row = RefreshToken(
        user_id=user.id,
        organization_id=membership.organization_id,
        token_hash=hash_token(raw),
        expires_at=refresh_token_expiry(),
        user_agent=(user_agent or "")[:400] or None,
        ip_address=(ip or "")[:64] or None,
    )
    db.add(row)
    db.flush()
    access = create_access_token(user.id, membership.organization_id, membership.role.value, session_id=row.id)
    return TokenBundle(access, raw, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60), row


# --- credential throttling ------------------------------------------------------------


def _throttle_row(db: Session, scope: str, subject: str, ip: str) -> Optional[LoginThrottle]:
    return db.scalars(
        select(LoginThrottle).where(
            LoginThrottle.scope == scope, LoginThrottle.subject == subject, LoginThrottle.ip_address == ip
        )
    ).first()


def _throttle_key_ip(ip: Optional[str]) -> str:
    return (ip or "")[:64]


def throttle_is_locked(db: Session, scope: str, subject: str, ip: Optional[str]) -> bool:
    row = _throttle_row(db, scope, subject, _throttle_key_ip(ip))
    locked_until = aware(row.locked_until) if row is not None else None
    return bool(locked_until and locked_until > utcnow())


def throttle_register_failure(db: Session, scope: str, subject: str, ip: Optional[str]) -> bool:
    """Count a failed attempt (caller commits). Returns True when this failure triggers a block."""
    key_ip = _throttle_key_ip(ip)
    now = utcnow()
    row = _throttle_row(db, scope, subject, key_ip)
    if row is None:
        row = LoginThrottle(scope=scope, subject=subject, ip_address=key_ip, failures=0, window_started_at=now)
        db.add(row)
    window_started = aware(row.window_started_at)
    if window_started is None or window_started <= now - timedelta(minutes=THROTTLE_WINDOW_MINUTES):
        row.failures = 0
        row.window_started_at = now
    row.failures = (row.failures or 0) + 1
    if row.failures >= MAX_FAILED_LOGINS:
        row.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        row.failures = 0
        row.window_started_at = now
        db.flush()
        return True
    db.flush()
    return False


def _alert_lockout(scope: str, subject_label: str, subject_key: str, ip: Optional[str]) -> None:
    """Alert once per (scope, account, IP) lockout burst (send_alert dedupes and never raises).
    Only a masked email / user id is included - never the submitted password or code."""
    send_alert(
        "auth.repeated_failures",
        f"{scope} throttle tripped after {MAX_FAILED_LOGINS} failed attempts",
        {"scope": scope, "account": subject_label, "client_ip": ip or "unknown", "locked_minutes": LOCKOUT_MINUTES},
        severity="warning",
        dedup_key=f"auth.repeated_failures:{scope}:{hash_token(subject_key)[:16]}:{ip or ''}",
    )


def throttle_clear(db: Session, scope: str, subject: str, ip: Optional[str] = None) -> None:
    """Forget failures for a key (caller commits). ip=None clears every IP for the subject."""
    stmt = (
        delete(LoginThrottle)
        .where(LoginThrottle.scope == scope, LoginThrottle.subject == subject)
        .execution_options(synchronize_session="fetch")
    )
    if ip is not None:
        stmt = stmt.where(LoginThrottle.ip_address == _throttle_key_ip(ip))
    db.execute(stmt)


# --- /me ------------------------------------------------------------------------------


def build_me(db: Session, ctx: CurrentContext) -> MeResponse:
    rows = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == ctx.user.id, Membership.status == MembershipStatus.ACTIVE)
        .order_by(Membership.created_at, Membership.id)
    ).all()
    m = ctx.membership
    return MeResponse(
        user=UserOut.model_validate(ctx.user),
        organization=OrganizationOut.model_validate(ctx.organization),
        membership=MembershipOut(id=m.id, role=m.role, status=m.status, joined_at=m.accepted_at or m.created_at),
        organizations=[
            OrganizationSummary(id=org.id, name=org.name, slug=org.slug, role=mem.role) for mem, org in rows
        ],
        access=OrganizationAccess(**org_access.access_summary(db, ctx.organization)),
    )


def hash_otp(email: str, otp: str) -> str:
    msg = f"{email.lower().strip()}:{otp.strip()}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _send_signup_verification_email(email: str, full_name: str, otp: str) -> bool:
    subject = "Verify your Rooman Billing email"
    text_body = (
        f"Hello {full_name},\n\n"
        f"Your Rooman Billing verification code is: {otp}\n\n"
        "This code will expire in 10 minutes.\n\n"
        "For your security, do not share this code with anyone. Rooman Billing support will never ask for your verification code.\n\n"
        "If you did not request this verification, please ignore this email.\n\n"
        "— Rooman Billing"
    )
    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
    .card {{ max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 32px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
    .header {{ text-align: center; margin-bottom: 24px; }}
    .title {{ font-size: 20px; font-weight: 700; color: #0f172a; margin: 0 0 8px 0; }}
    .subtitle {{ font-size: 14px; color: #64748b; margin: 0; }}
    .otp-container {{ text-align: center; margin: 32px 0; }}
    .otp-box {{ display: inline-block; font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #4f46e5; background: #f1f5f9; padding: 12px 28px; border-radius: 8px; border: 1px solid #cbd5e1; font-family: monospace; }}
    .expiry {{ font-size: 13px; color: #64748b; margin-top: 12px; }}
    .security-note {{ font-size: 13px; color: #475569; background: #f8fafc; border-left: 4px solid #6366f1; padding: 12px 16px; border-radius: 4px; margin: 24px 0; }}
    .footer {{ font-size: 12px; color: #94a3b8; text-align: center; margin-top: 32px; border-top: 1px solid #f1f5f9; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1 class="title">Verify your email address</h1>
      <p class="subtitle">Welcome to Rooman Billing, {html.escape(full_name)}!</p>
    </div>
    <p>Please enter the following 6-digit verification code to complete your organization registration:</p>
    <div class="otp-container">
      <div class="otp-box">{otp}</div>
      <div class="expiry">This code will expire in <strong>10 minutes</strong>.</div>
    </div>
    <div class="security-note">
      <strong>Security notice:</strong> Never share this code with anyone. Rooman Billing team members will never ask for your verification code.
    </div>
    <p style="font-size: 13px; color: #64748b;">If you didn't create an account with Rooman Billing, you can safely ignore this email.</p>
    <div class="footer">
      &copy; Rooman Billing. All rights reserved.
    </div>
  </div>
</body>
</html>"""
    return send_email(to=email, subject=subject, text_body=text_body, html_body=html_body)


def _ensure_email_claimable(db: Session, email: str) -> Optional[User]:
    """Reject emails that belong to a real account.

    A password-less user row is only a placeholder created by a team invitation; the owner of
    the mailbox may claim it through the OTP signup flow (proving control of the address), so
    an invitation cannot be used to squat an email and block its owner from signing up.
    """
    user = get_user_by_email(db, email)
    if user is not None and user.hashed_password is not None:
        raise ConflictError("An account with this email already exists.", {"fields": {"email": "already registered"}})
    return user


def purge_expired_pending_signups(db: Session) -> int:
    """Delete pending signups that expired more than EXPIRED_PENDING_SIGNUP_RETENTION ago.
    Commits; returns the number removed."""
    result = db.execute(
        delete(PendingSignup)
        .where(PendingSignup.expires_at <= utcnow() - EXPIRED_PENDING_SIGNUP_RETENTION)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount or 0


_EMAIL_FAILURE_MESSAGES = {
    "unreachable": "We couldn't reach the email server to send your verification code. Please try again in a few minutes; if it keeps failing, contact support.",
    "timeout": "The email server took too long to respond, so your verification code wasn't sent. Please try again in a few minutes.",
    "tls": "A secure connection to the email server could not be established, so your verification code wasn't sent. Please contact support.",
    "auth": "The email server rejected this server's login, so your verification code wasn't sent. Please contact support.",
    "rejected": "The email server refused to deliver to this address. Please check the email address and try again.",
    "error": "We couldn't send your verification code. Please try again in a few minutes.",
}


def _raise_email_delivery_failure(db: Session, email: str, exc: Exception, action: str) -> None:
    """Roll back the pending OTP and answer with a clear 503 (not a generic 422, and never a
    proxy 502 from a hung request). The category is logged for operators; no secrets."""
    db.rollback()
    reason = exc.reason if isinstance(exc, EmailDeliveryError) else "error"
    logger.error("Signup verification email %s to %s failed (%s): %s", action, email, reason, type(exc).__name__)
    raise AppException(
        message=_EMAIL_FAILURE_MESSAGES.get(reason, _EMAIL_FAILURE_MESSAGES["error"]),
        code="EMAIL_DELIVERY_FAILED",
        status_code=503,
        details={"reason": reason},
    )


def _pending_password_hash(password: Optional[str]) -> str:
    """Hash stored on a pending signup. Without a password yet it is the hash of a random secret
    nobody knows, so nothing can ever match it; the real password is set by /signup/complete."""
    return hash_password(password if password is not None else generate_opaque_token())


def request_signup_verification(
    db: Session,
    data: SignupVerificationRequest,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[str, int, int]:
    email = normalize_email(data.email)
    _ensure_email_claimable(db, email)
    # The sign-up page now asks for the password only after the email is verified, so the code
    # can be requested without one. A password, when sent, must still meet the policy.
    password_supplied = data.password is not None
    if password_supplied:
        _password_problem(data.password)

    org_name = data.organization_name.strip()
    if not org_name:
        raise ValidationAppError("Organization name cannot be empty.", {"fields": {"organization_name": "required"}})

    now = utcnow()
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first()
    if pending is not None:
        last_sent = aware(pending.last_sent_at)
        if last_sent is not None:
            elapsed = (now - last_sent).total_seconds()
            if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                cooldown_remaining = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
                raise ValidationAppError(
                    f"Please wait {cooldown_remaining} second(s) before requesting a new verification code.",
                    {"cooldown_remaining": cooldown_remaining},
                )

    otp = generate_otp()
    otp_hash = hash_otp(email, otp)
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    pending_expires = aware(pending.expires_at) if pending is not None else None
    live_pending = pending is not None and pending_expires is not None and pending_expires > now
    password_matches = bool(
        data.password is not None
        and pending is not None
        and live_pending
        and verify_password(data.password, pending.hashed_password)
    )
    if pending is not None and live_pending and not password_matches:
        # A live request exists that was not proven to be this requester's own (no password, or a
        # different one) - possibly someone racing the real owner of this mailbox. Never overwrite
        # its details: just send a fresh code to the mailbox. The code only ever reaches the
        # mailbox owner, and /signup/complete takes the organization details from whoever proves
        # that; the legacy verify-otp still requires the original password.
        pending.otp_hash = otp_hash
        pending.expires_at = expires_at
        pending.attempts = 0
        pending.last_sent_at = now
        display_name = pending.full_name
    elif pending is None:
        display_name = data.full_name.strip()
        pending = PendingSignup(
            email=email,
            organization_name=org_name,
            full_name=data.full_name.strip(),
            hashed_password=_pending_password_hash(data.password),
            otp_hash=otp_hash,
            expires_at=expires_at,
            attempts=0,
            last_sent_at=now,
            created_at=now,
        )
        db.add(pending)
    else:
        # Same requester (password matches) editing their details, or an expired request.
        display_name = data.full_name.strip()
        pending.organization_name = org_name
        pending.full_name = display_name
        pending.hashed_password = _pending_password_hash(data.password)
        pending.otp_hash = otp_hash
        pending.expires_at = expires_at
        pending.attempts = 0
        pending.last_sent_at = now

    db.flush()

    try:
        delivered = _send_signup_verification_email(email, display_name, otp)
        if not delivered and settings.is_production:
            raise ValidationAppError(
                "Email delivery is not configured on this server. Please contact an administrator."
            )
    except ValidationAppError:
        db.rollback()
        raise
    except Exception as exc:
        _raise_email_delivery_failure(db, email, exc, "send")

    _commit(db)
    logger.info("Signup verification OTP sent to %s", email)
    return email, OTP_EXPIRY_MINUTES * 60, OTP_RESEND_COOLDOWN_SECONDS


def resend_signup_otp(db: Session, email: str) -> Tuple[str, int, int]:
    email = normalize_email(email)
    _ensure_email_claimable(db, email)

    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first()
    if pending is None:
        raise ValidationAppError(
            "No pending signup found for this email. Please fill out the registration form again.",
            {"fields": {"email": "not_found"}},
        )

    now = utcnow()
    last_sent = aware(pending.last_sent_at)
    if last_sent is not None:
        elapsed = (now - last_sent).total_seconds()
        if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
            cooldown_remaining = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
            raise ValidationAppError(
                f"Please wait {cooldown_remaining} second(s) before requesting a new verification code.",
                {"cooldown_remaining": cooldown_remaining},
            )

    otp = generate_otp()
    pending.otp_hash = hash_otp(email, otp)
    pending.expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    pending.attempts = 0
    pending.last_sent_at = now
    db.flush()

    try:
        delivered = _send_signup_verification_email(email, pending.full_name, otp)
        if not delivered and settings.is_production:
            raise ValidationAppError(
                "Email delivery is not configured on this server. Please contact an administrator."
            )
    except ValidationAppError:
        db.rollback()
        raise
    except Exception as exc:
        _raise_email_delivery_failure(db, email, exc, "resend")

    _commit(db)
    logger.info("Signup verification OTP resent to %s", email)
    return email, OTP_EXPIRY_MINUTES * 60, OTP_RESEND_COOLDOWN_SECONDS


def _pending_for_otp(db: Session, email: str, now: datetime) -> PendingSignup:
    """The live pending signup for `email`; a missing, expired or attempt-locked one is rejected.
    An attempt-locked one is removed; an expired one is kept (until the purge) so retries keep
    saying "expired" and a new code can be resent."""
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first()
    if pending is None:
        raise ValidationAppError(
            "No pending signup found for this email. Please request a new verification code.",
            {"fields": {"otp": "not_found"}},
        )

    expires_at = aware(pending.expires_at)
    if expires_at is None or expires_at <= now:
        raise ValidationAppError(
            "This code has expired. Request a new code.",
            {"fields": {"otp": "expired"}},
        )

    if pending.attempts >= OTP_MAX_ATTEMPTS:
        db.delete(pending)
        _commit(db)
        raise ValidationAppError(
            "Maximum verification attempts exceeded. Please request a new code.",
            {"fields": {"otp": "locked"}, "attempts_remaining": 0},
        )
    return pending


def _reject_wrong_otp(db: Session, pending: PendingSignup) -> None:
    """Count a wrong code; the fifth one invalidates the pending signup. Always raises."""
    pending.attempts += 1
    remaining = OTP_MAX_ATTEMPTS - pending.attempts
    if remaining <= 0:
        db.delete(pending)
        _commit(db)
        raise ValidationAppError(
            "Maximum verification attempts exceeded. This code has been invalidated. Please request a new code.",
            {"fields": {"otp": "locked"}, "attempts_remaining": 0},
        )
    _commit(db)
    raise ValidationAppError(
        f"Invalid verification code. {remaining} attempt(s) remaining.",
        {"fields": {"otp": "invalid"}, "attempts_remaining": remaining},
    )


def confirm_signup_email(db: Session, email: str, otp: str) -> Tuple[str, int]:
    """Check the emailed code without creating anything. Returns (verification token, seconds).

    Same expiry, attempt limit and hashing as the legacy verify-otp. On success the code is spent
    (replaced by a random hash, so it can never be entered again) and the pending signup is kept
    for SIGNUP_COMPLETION_MINUTES so the verified owner can choose a password and finish.
    """
    email = normalize_email(email)
    now = utcnow()
    pending = _pending_for_otp(db, email, now)

    if not constant_time_equals(pending.otp_hash, hash_otp(email, otp)):
        _reject_wrong_otp(db, pending)

    existing = get_user_by_email(db, email)
    if existing is not None and existing.hashed_password is not None:
        db.delete(pending)
        _commit(db)
        raise ConflictError("An account with this email already exists.", {"fields": {"email": "already registered"}})

    completion_expires = now + timedelta(minutes=SIGNUP_COMPLETION_MINUTES)
    pending.otp_hash = hash_otp(email, generate_opaque_token())
    pending.attempts = 0
    pending.expires_at = completion_expires
    _commit(db)
    token = create_signup_verification_token(pending.id, email, completion_expires)
    return token, SIGNUP_COMPLETION_MINUTES * 60


def complete_signup(
    db: Session,
    email: str,
    verification_token: str,
    organization_name: str,
    full_name: str,
    password: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[TokenBundle, ActorContext]:
    """Create the organization once the mailbox is verified and a policy-compliant password chosen."""
    email = normalize_email(email)
    invalid = ValidationAppError(
        "Your email verification has expired or is invalid. Please verify your email again.",
        {"fields": {"verification_token": "invalid"}},
    )
    try:
        claims = decode_signup_verification_token(verification_token)
    except jwt.PyJWTError:
        raise invalid from None
    if claims.get("email") != email:
        raise invalid

    now = utcnow()
    pending = db.scalars(select(PendingSignup).where(PendingSignup.id == claims["sub"])).first()
    expires_at = aware(pending.expires_at) if pending is not None else None
    if pending is None or pending.email != email or expires_at is None or expires_at <= now:
        raise invalid

    _password_problem(password)
    org_name = organization_name.strip()
    name = full_name.strip()
    if not org_name:
        raise ValidationAppError("Organization name cannot be empty.", {"fields": {"organization_name": "required"}})
    if not name:
        raise ValidationAppError("Full name cannot be empty.", {"fields": {"full_name": "required"}})

    return _create_verified_signup(db, pending, email, org_name, name, hash_password(password), now, ip, user_agent)


def verify_signup_otp(
    db: Session,
    email: str,
    otp: str,
    password: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[TokenBundle, ActorContext]:
    email = normalize_email(email)
    now = utcnow()
    pending = _pending_for_otp(db, email, now)

    expected_hash = hash_otp(email, otp)
    otp_ok = constant_time_equals(pending.otp_hash, expected_hash)
    # The password chosen on the signup form must accompany the code, so a signup request
    # started by someone else (with their password) can never be completed by the mailbox
    # owner unknowingly, nor the reverse.
    password_ok = verify_password(password or "", pending.hashed_password)
    if otp_ok and not password_ok:
        pending.attempts += 1
        remaining = max(0, OTP_MAX_ATTEMPTS - pending.attempts)
        _commit(db)
        raise ValidationAppError(
            "The password does not match the one entered when this verification code was requested. "
            "Use that password, or wait for the code to expire and sign up again.",
            {"fields": {"password": "mismatch"}, "attempts_remaining": remaining},
        )
    if not otp_ok:
        _reject_wrong_otp(db, pending)

    return _create_verified_signup(
        db, pending, email, pending.organization_name, pending.full_name, pending.hashed_password, now, ip, user_agent
    )


def _create_verified_signup(
    db: Session,
    pending: PendingSignup,
    email: str,
    org_name: str,
    full_name: str,
    hashed_password: str,
    now: datetime,
    ip: Optional[str],
    user_agent: Optional[str],
) -> Tuple[TokenBundle, ActorContext]:
    """Turn a pending signup whose mailbox has been verified into the organization and its owner."""
    existing = get_user_by_email(db, email)
    if existing is not None and existing.hashed_password is not None:
        db.delete(pending)
        _commit(db)
        raise ConflictError("An account with this email already exists.", {"fields": {"email": "already registered"}})

    # Remove pending record so OTP can never be reused
    db.delete(pending)
    db.flush()

    # Self-service signup: the organization is ACTIVE at once and its free trial starts now (no
    # approval). After the trial a subscription request, decided by a Platform Administrator, sets
    # its modules and seats (subscription_request_service); the platform can suspend it any time.
    organization = Organization(
        name=org_name,
        slug=unique_slug(db, org_name),
        status=OrganizationStatus.ACTIVE,
        module_access=ModuleAccess.TRIAL.value,
        trial_started_at=now,
        trial_ends_at=now + timedelta(days=settings.ORGANIZATION_TRIAL_DAYS),
    )
    db.add(organization)
    db.flush()

    if existing is not None:
        # Claim the password-less placeholder an invitation created (see _ensure_email_claimable).
        # Its pending invitations stay pending and can be accepted after signing in.
        user = existing
        user.full_name = full_name
        user.hashed_password = hashed_password
        user.is_active = True
        user.email_verified_at = user.email_verified_at or now
        user.last_login_at = now
    else:
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            is_active=True,
            email_verified_at=now,
            last_login_at=now,
        )
        db.add(user)
    db.flush()

    membership = Membership(
        organization_id=organization.id,
        user_id=user.id,
        role=MemberRole.OWNER,
        status=MembershipStatus.ACTIVE,
        accepted_at=now,
    )
    db.add(membership)
    db.flush()

    tokens, _ = issue_tokens(db, user, membership, ip, user_agent)
    ctx = make_ctx(user, organization, membership, ip, user_agent)
    audit.record(
        db,
        action="USER_SIGNED_UP",
        entity_type="user",
        entity_id=user.id,
        entity_label=user.email,
        ctx=ctx,
        after={
            "email": user.email,
            "full_name": user.full_name,
            "organization_id": organization.id,
            "organization_name": organization.name,
            "slug": organization.slug,
            "email_verified": True,
            "claimed_invited_user": existing is not None,
            "organization_status": organization.status.value,
        },
    )
    from backend.app.services import platform_audit
    platform_audit.record(
        db,
        action=platform_audit.ORGANIZATION_CREATED,
        result=platform_audit.SUCCESS,
        staff=None,
        tenant_actor=user,
        tenant_role=membership.role,
        session_id=None,
        ip_address=ip,
        user_agent=user_agent,
        organization=organization,
        target_type="organization",
        target_id=organization.id,
        details={
            "owner_email": user.email,
            "owner_name": user.full_name,
            "organization_name": organization.name,
            "status": organization.status.value,
        },
    )
    platform_audit.record(
        db,
        action=platform_audit.ORGANIZATION_TRIAL_STARTED,
        result=platform_audit.SUCCESS,
        tenant_actor=user,
        tenant_role=membership.role,
        ip_address=ip,
        user_agent=user_agent,
        organization=organization,
        target_type="organization",
        target_id=organization.id,
        details={
            "trial_started_at": organization.trial_started_at.isoformat(),
            "trial_ends_at": organization.trial_ends_at.isoformat(),
            "trial_days": settings.ORGANIZATION_TRIAL_DAYS,
        },
    )
    _commit(db, "An account with this email or organization already exists.")
    return tokens, ctx


def _record_login_failure(
    db: Session,
    email: str,
    user: Optional[User],
    reason: str,
    ip: Optional[str],
    user_agent: Optional[str],
) -> None:
    ctx = None
    if user is not None:
        membership = pick_membership(db, user.id)
        organization = db.get(Organization, membership.organization_id) if membership else None
        ctx = make_ctx(user, organization, membership, ip, user_agent)
    audit.record(
        db,
        action="LOGIN_FAILED",
        entity_type="user",
        entity_id=user.id if user else None,
        entity_label=email,
        ctx=ctx,
        actor_label=email,
        status=AuditStatus.DENIED,
        after={"reason": reason, "ip_address": ip},
    )


@dataclass
class MfaChallenge:
    """Returned by login() instead of tokens when the user has two-factor authentication on."""

    mfa_token: str
    expires_in: int = 5 * 60

    def as_dict(self) -> Dict[str, Any]:
        return {"mfa_required": True, "mfa_token": self.mfa_token, "expires_in": self.expires_in}


def _complete_login(
    db: Session,
    user: User,
    membership: Membership,
    ip: Optional[str],
    user_agent: Optional[str],
    *,
    mfa: bool = False,
) -> TokenBundle:
    now = utcnow()
    organization = db.get(Organization, membership.organization_id)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    tokens, _ = issue_tokens(db, user, membership, ip, user_agent)
    ctx = make_ctx(user, organization, membership, ip, user_agent)
    audit.record(
        db,
        action="USER_LOGGED_IN",
        entity_type="user",
        entity_id=user.id,
        entity_label=user.email,
        ctx=ctx,
        actor_label=user.email,
        after={"organization_id": membership.organization_id, "role": membership.role.value, "mfa": mfa},
    )
    _commit(db)
    return tokens


def check_password_throttled(
    db: Session, email: str, password: str, ip: Optional[str], user_agent: Optional[str]
) -> User:
    """Verify email + password under the per-(email, IP) throttle. Returns the user or raises.

    Failures are counted per (email, client IP) instead of locking the account outright, so
    someone guessing from another address cannot lock the real user out; the slowapi per-IP
    limit on the endpoints caps password spraying across many accounts from one address.
    Unknown emails are counted and answered exactly like known ones.
    """
    email = normalize_email(email)
    if throttle_is_locked(db, "login", email, ip):
        user = get_user_by_email(db, email)
        _record_login_failure(db, email, user, "throttled", ip, user_agent)
        db.commit()
        raise UnauthorizedError(TOO_MANY_ATTEMPTS)

    user = get_user_by_email(db, email)
    # Always pay the bcrypt cost so response time does not reveal whether the email exists.
    stored_hash = user.hashed_password if (user and user.hashed_password) else _dummy_password_hash()
    password_ok = verify_password(password, stored_hash) and user is not None and bool(user.hashed_password)

    if user is None or not user.is_active or not password_ok:
        blocked = throttle_register_failure(db, "login", email, ip)
        if user is None or not user.is_active:
            reason = "unknown_or_inactive_user"
        else:
            reason = "throttled_after_failures" if blocked else "bad_password"
        _record_login_failure(db, email, user, reason, ip, user_agent)
        db.commit()
        if blocked:
            _alert_lockout("login", mask_email(email), email, ip)
        raise UnauthorizedError(TOO_MANY_ATTEMPTS if blocked else INVALID_CREDENTIALS)

    throttle_clear(db, "login", email, ip)
    return user


def login(
    db: Session, email: str, password: str, ip: Optional[str], user_agent: Optional[str]
) -> Union[TokenBundle, MfaChallenge]:
    user = check_password_throttled(db, email, password, ip, user_agent)

    membership = pick_membership(db, user.id)
    if membership is None:
        _record_login_failure(db, user.email, user, "no_active_membership", ip, user_agent)
        db.commit()
        raise UnauthorizedError(NOT_A_MEMBER)

    if user.totp_enabled_at is not None:
        # Password step done; tokens are only issued by login_mfa() with a valid TOTP code.
        db.commit()
        return MfaChallenge(mfa_token=create_mfa_token(user.id))

    return _complete_login(db, user, membership, ip, user_agent)


def _check_totp_code(db: Session, user: User, code: str, ip: Optional[str], user_agent: Optional[str]) -> None:
    """Validate a TOTP code for an enrolled (or enrolling) user under the per-account throttle.

    Raises on failure (after committing the failure count); on success records the used step
    so the same code cannot be replayed. Caller commits on success.
    """
    if throttle_is_locked(db, "mfa", user.id, None):
        raise UnauthorizedError(TOO_MANY_ATTEMPTS)
    secret = decrypt_secret(user.totp_secret)
    step = verify_totp(secret, code) if secret else None
    if step is None or (user.totp_last_used_step is not None and step <= user.totp_last_used_step):
        blocked = throttle_register_failure(db, "mfa", user.id, None)
        _record_login_failure(db, user.email, user, "bad_totp_code", ip, user_agent)
        db.commit()
        if blocked:
            _alert_lockout("mfa", f"user {user.id}", user.id, ip)
        raise UnauthorizedError(TOO_MANY_ATTEMPTS if blocked else INVALID_MFA_CODE)
    user.totp_last_used_step = step
    throttle_clear(db, "mfa", user.id)


def login_mfa(db: Session, mfa_token: str, code: str, ip: Optional[str], user_agent: Optional[str]) -> TokenBundle:
    expired = UnauthorizedError("This sign-in attempt has expired. Please sign in again.")
    try:
        payload = decode_mfa_token(mfa_token)
    except jwt.PyJWTError:
        raise expired
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active or user.totp_enabled_at is None:
        raise expired
    valid_after = aware(user.tokens_valid_after)
    iat = payload.get("iat")
    if valid_after is not None and (not isinstance(iat, (int, float)) or datetime.fromtimestamp(iat, tz=timezone.utc) < valid_after):
        raise expired

    _check_totp_code(db, user, code, ip, user_agent)
    membership = pick_membership(db, user.id)
    if membership is None:
        db.commit()
        raise UnauthorizedError(NOT_A_MEMBER)
    return _complete_login(db, user, membership, ip, user_agent, mfa=True)


# --- two-factor enrolment ------------------------------------------------------------


def setup_totp(db: Session, ctx: CurrentContext) -> Dict[str, str]:
    """Start (or restart) enrolment: store a new encrypted seed, not yet active."""
    user = ctx.user
    if user.totp_enabled_at is not None:
        raise ConflictError("Two-factor authentication is already enabled. Disable it first to re-enrol.")
    secret = generate_totp_secret()
    user.totp_secret = encrypt_secret(secret)
    user.totp_last_used_step = None
    _commit(db)
    return {
        "secret": secret,
        "otpauth_uri": provisioning_uri(secret, user.email, settings.PROJECT_NAME),
    }


def enable_totp(db: Session, ctx: CurrentContext, code: str) -> None:
    user = ctx.user
    if user.totp_enabled_at is not None:
        raise ConflictError("Two-factor authentication is already enabled.")
    if not user.totp_secret:
        raise ValidationAppError("Start two-factor setup first.", {"fields": {"code": "Start two-factor setup first."}})
    try:
        _check_totp_code(db, user, code, ctx.ip_address, ctx.user_agent)
    except UnauthorizedError as exc:
        # A wrong code while signed in is a form error, not a lost session.
        raise ValidationAppError(exc.message, {"fields": {"code": exc.message}}) from exc
    user.totp_enabled_at = utcnow()
    audit.record(
        db,
        action="TWO_FACTOR_ENABLED",
        entity_type="user",
        entity_id=user.id,
        entity_label=user.email,
        ctx=ctx,
    )
    _commit(db)


def disable_totp(db: Session, ctx: CurrentContext, password: str, code: str) -> None:
    user = ctx.user
    if user.totp_enabled_at is None:
        raise ConflictError("Two-factor authentication is not enabled.")
    if not verify_password(password, user.hashed_password):
        raise ValidationAppError("The password is incorrect.", {"fields": {"password": "The password is incorrect."}})
    try:
        _check_totp_code(db, user, code, ctx.ip_address, ctx.user_agent)
    except UnauthorizedError as exc:
        raise ValidationAppError(exc.message, {"fields": {"code": exc.message}}) from exc
    user.totp_secret = None
    user.totp_enabled_at = None
    user.totp_last_used_step = None
    audit.record(
        db,
        action="TWO_FACTOR_DISABLED",
        entity_type="user",
        entity_id=user.id,
        entity_label=user.email,
        ctx=ctx,
    )
    _commit(db)


# --- sessions ------------------------------------------------------------------------


def list_sessions(db: Session, ctx: CurrentContext, current_session_id: Optional[str]) -> List[Dict[str, Any]]:
    """The caller's live refresh tokens (one per signed-in browser/device).

    Refresh tokens rotate on every refresh, so `created_at` of the live row is the last time
    that session was refreshed ("last active"), not the original sign-in time.
    """
    rows = db.scalars(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == ctx.user.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
        .order_by(RefreshToken.created_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "organization_id": row.organization_id,
            "created_at": aware(row.created_at),
            "last_active_at": aware(row.created_at),
            "expires_at": aware(row.expires_at),
            "user_agent": row.user_agent,
            "ip_address": row.ip_address,
            "current": row.id == current_session_id,
        }
        for row in rows
    ]


def revoke_session(db: Session, ctx: CurrentContext, session_id: str) -> None:
    row = db.scalars(
        select(RefreshToken).where(RefreshToken.id == session_id, RefreshToken.user_id == ctx.user.id)
    ).first()
    if row is None or row.revoked_at is not None:
        raise EntityNotFoundError("Session", session_id)
    row.revoked_at = utcnow()
    audit.record(
        db,
        action="SESSION_REVOKED",
        entity_type="user",
        entity_id=ctx.user.id,
        entity_label=ctx.user.email,
        ctx=ctx,
        after={"session_id": row.id, "user_agent": row.user_agent, "ip_address": row.ip_address},
    )
    _commit(db)


def refresh(db: Session, raw_token: str, ip: Optional[str], user_agent: Optional[str]) -> TokenBundle:
    # Lock the row for the rotation so two concurrent refreshes with the same token cannot both
    # mint a successor (FOR UPDATE is a no-op on SQLite, which serialises writers anyway).
    token = db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update()
    ).first()
    if token is None:
        raise UnauthorizedError("Refresh token is invalid.")
    if token.revoked_at is not None and token.replaced_by_id is None:
        # Explicitly revoked (logout, password change, DELETE /auth/sessions/{id}, deactivation):
        # just refuse. Not treated as theft, so signing out one device from another does not
        # cascade into signing out everything when the revoked device next tries to refresh.
        raise UnauthorizedError("Refresh token has been revoked. Please sign in again.")
    if token.revoked_at is not None:
        # Replay of a rotated token: someone else may hold the chain. Kill every session.
        revoked = revoke_refresh_tokens(db, token.user_id)
        db.commit()
        logger.warning("Refresh token reuse detected for user %s; revoked %d token(s)", token.user_id, revoked)
        raise UnauthorizedError("Refresh token has been revoked. Please sign in again.")
    if aware(token.expires_at) <= utcnow():
        raise UnauthorizedError("Refresh token has expired. Please sign in again.")

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User account is inactive or no longer exists.")
    membership = pick_membership(db, user.id, token.organization_id) or pick_membership(db, user.id)
    if membership is None:
        raise UnauthorizedError(NOT_A_MEMBER)

    tokens, new_row = issue_tokens(db, user, membership, ip, user_agent)
    token.revoked_at = utcnow()
    token.replaced_by_id = new_row.id
    _commit(db)
    return tokens


def logout(db: Session, ctx: CurrentContext, raw_token: str) -> None:
    token = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))).first()
    if token is not None and token.user_id == ctx.user.id and token.revoked_at is None:
        token.revoked_at = utcnow()
    ctx.user.tokens_valid_after = utcnow()
    audit.record(
        db,
        action="USER_LOGGED_OUT",
        entity_type="user",
        entity_id=ctx.user.id,
        entity_label=ctx.user.email,
        ctx=ctx,
    )
    _commit(db)


def switch_organization(
    db: Session, ctx: CurrentContext, organization_id: str, ip: Optional[str], user_agent: Optional[str]
) -> TokenBundle:
    membership = db.scalars(
        select(Membership).where(
            Membership.user_id == ctx.user.id,
            Membership.organization_id == organization_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    ).first()
    if membership is None:
        raise ForbiddenError("You are not an active member of that organization.")
    tokens, _ = issue_tokens(db, ctx.user, membership, ip, user_agent)
    _commit(db)
    return tokens


# --- passwords --------------------------------------------------------------------------


def change_password(
    db: Session,
    ctx: CurrentContext,
    current_password: str,
    new_password: str,
    keep_refresh_token: Optional[str] = None,
) -> None:
    if not verify_password(current_password, ctx.user.hashed_password):
        raise ValidationAppError(
            "The current password is incorrect.",
            {"fields": {"current_password": "The current password is incorrect."}},
        )
    _password_problem(new_password, "new_password")
    if verify_password(new_password, ctx.user.hashed_password):
        raise ValidationAppError(
            "The new password must differ from the current one.",
            {"fields": {"new_password": "The new password must differ from the current one."}},
        )
    ctx.user.hashed_password = hash_password(new_password)
    ctx.user.failed_login_attempts = 0
    ctx.user.locked_until = None
    ctx.user.tokens_valid_after = utcnow()
    revoked = revoke_refresh_tokens(
        db, ctx.user.id, keep_token_hash=hash_token(keep_refresh_token) if keep_refresh_token else None
    )
    audit.record(
        db,
        action="PASSWORD_CHANGED",
        entity_type="user",
        entity_id=ctx.user.id,
        entity_label=ctx.user.email,
        ctx=ctx,
        after={"sessions_revoked": revoked},
    )
    _commit(db)


def _invalidate_reset_tokens(db: Session, user_id: str, except_id: Optional[str] = None) -> None:
    stmt = (
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    if except_id:
        stmt = stmt.where(PasswordResetToken.id != except_id)
    db.execute(stmt)


def forgot_password(db: Session, email: str, ip: Optional[str], user_agent: Optional[str]) -> str:
    """Always succeeds with the same message. The link is only ever delivered by email -
    never in the response (production refuses to start without SMTP_HOST)."""
    message = "If an account exists for that email address, a password reset link has been sent."
    email = normalize_email(email)
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return message

    # Only the newest link works: requesting another one voids the earlier ones.
    _invalidate_reset_tokens(db, user.id)
    raw = generate_opaque_token()
    db.add(PasswordResetToken(user_id=user.id, token_hash=hash_token(raw), expires_at=password_reset_expiry()))
    link = frontend_url(f"reset-password?token={raw}")
    delivered = False
    try:
        delivered = send_email(
            user.email,
            "Reset your Rooman Billing password",
            (
                f"Hello {user.full_name},\n\n"
                f"We received a request to reset the password for your Rooman Billing account.\n"
                f"Open the link below within {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes to choose a new password:\n\n"
                f"{link}\n\n"
                "If you did not request this you can ignore this email; your password will not change."
            ),
            html_body=(
                f"<p>Hello {html.escape(user.full_name)},</p>"
                f"<p>We received a request to reset the password for your Rooman Billing account. "
                f"The link is valid for {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes.</p>"
                f'<p><a href="{link}">Reset your password</a></p>'
                "<p>If you did not request this you can ignore this email.</p>"
            ),
        )
    except Exception as exc:  # smtplib / OSError: never fail the request, never leak the link
        logger.error("Password reset email to %s failed: %s", user.email, exc)
        delivered = False

    membership = pick_membership(db, user.id)
    organization = db.get(Organization, membership.organization_id) if membership else None
    audit.record(
        db,
        action="PASSWORD_RESET_REQUESTED",
        entity_type="user",
        entity_id=user.id,
        entity_label=user.email,
        ctx=make_ctx(user, organization, membership, ip, user_agent),
        actor_label=user.email,
        after={"email_delivered": delivered},
    )
    _commit(db)
    if not delivered:
        logger.warning("Password reset email for user %s was not delivered (SMTP disabled or failing)", user.id)
    return message


def reset_password(db: Session, raw_token: str, new_password: str, ip: Optional[str], user_agent: Optional[str]) -> None:
    invalid = ValidationAppError(
        "This password reset link is invalid or has expired.",
        {"fields": {"token": "This password reset link is invalid or has expired. Request a new link."}},
    )
    token = db.scalars(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw_token))).first()
    if token is None or token.used_at is not None or aware(token.expires_at) <= utcnow():
        raise invalid
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise invalid
    _password_problem(new_password, "new_password")

    user.hashed_password = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    user.tokens_valid_after = utcnow()
    token.used_at = utcnow()
    _invalidate_reset_tokens(db, user.id, except_id=token.id)
    throttle_clear(db, "login", user.email)
    revoked = revoke_refresh_tokens(db, user.id)

    membership = pick_membership(db, user.id)
    organization = db.get(Organization, membership.organization_id) if membership else None
    audit.record(
        db,
        action="PASSWORD_RESET",
        entity_type="user",
        entity_id=user.id,
        entity_label=user.email,
        ctx=make_ctx(user, organization, membership, ip, user_agent),
        actor_label=user.email,
        after={"sessions_revoked": revoked},
    )
    _commit(db)


# --- invitations ------------------------------------------------------------------------


def _invitation_not_found() -> AppException:
    return AppException(
        message="This invitation is invalid, has expired or was already used.",
        code="ENTITY_NOT_FOUND",
        status_code=404,
        details={"entity": "invitation"},
    )


def find_invitation(db: Session, raw_token: str) -> Membership:
    membership = db.scalars(
        select(Membership).where(
            Membership.invite_token_hash == hash_token(raw_token),
            Membership.status == MembershipStatus.INVITED,
        )
    ).first()
    if membership is None or membership.invite_expires_at is None or aware(membership.invite_expires_at) <= utcnow():
        raise _invitation_not_found()
    return membership


def get_invitation(db: Session, raw_token: str) -> Dict[str, Any]:
    membership = find_invitation(db, raw_token)
    user = db.get(User, membership.user_id)
    organization = db.get(Organization, membership.organization_id)
    inviter = db.get(User, membership.invited_by_id) if membership.invited_by_id else None
    if user is None or organization is None:
        raise _invitation_not_found()
    return {
        "email": user.email,
        "organization_name": organization.name,
        "role": membership.role,
        "invited_by": inviter.full_name if inviter else organization.name,
        "expires_at": aware(membership.invite_expires_at),
        "user_exists": user.hashed_password is not None,
    }


def accept_invitation(
    db: Session,
    raw_token: str,
    full_name: Optional[str],
    password: Optional[str],
    ip: Optional[str],
    user_agent: Optional[str],
    totp_code: Optional[str] = None,
) -> TokenBundle:
    membership = find_invitation(db, raw_token)
    user = db.get(User, membership.user_id)
    organization = db.get(Organization, membership.organization_id)
    if user is None or organization is None or not user.is_active:
        raise _invitation_not_found()

    now = utcnow()
    if user.hashed_password is None:
        fields: Dict[str, str] = {}
        if not (full_name or "").strip():
            fields["full_name"] = "required"
        if not password:
            fields["password"] = "required"
        if fields:
            raise ValidationAppError("Your name and a password are required to create your account.", {"fields": fields})
        _password_problem(password)
        user.full_name = full_name.strip()  # type: ignore[union-attr]
        user.hashed_password = hash_password(password)  # type: ignore[arg-type]
        user.email_verified_at = user.email_verified_at or now
    else:
        # The invite token only proves someone can read the link, which an organization admin
        # can too. Signing into an existing account needs that account's own credentials.
        if not password:
            raise ValidationAppError(
                "Enter the password of your existing account to accept this invitation.",
                {"fields": {"password": "required"}},
            )
        check_password_throttled(db, user.email, password, ip, user_agent)
        if user.totp_enabled_at is not None:
            if not (totp_code or "").strip():
                raise ValidationAppError(
                    "Enter the code from your authenticator app.", {"fields": {"totp_code": "required"}}
                )
            _check_totp_code(db, user, totp_code or "", ip, user_agent)

    # The invitation already holds a seat; this refuses only if the limit was lowered since.
    org_access.ensure_seat_available(db, organization, already_counted=True)
    from backend.app.services import tenant_admin_provisioning

    provisioned_by_platform = tenant_admin_provisioning.was_provisioned(db, membership.id)
    membership.status = MembershipStatus.ACTIVE
    membership.accepted_at = now
    membership.deactivated_at = None
    membership.invite_token_hash = None
    membership.invite_expires_at = None
    user.last_login_at = now
    user.failed_login_attempts = 0
    user.locked_until = None

    tokens, _ = issue_tokens(db, user, membership, ip, user_agent)
    ctx = make_ctx(user, organization, membership, ip, user_agent)
    audit.record(
        db,
        action="INVITATION_ACCEPTED",
        entity_type="membership",
        entity_id=membership.id,
        entity_label=user.email,
        ctx=ctx,
        before={"status": MembershipStatus.INVITED.value},
        after={"status": MembershipStatus.ACTIVE.value, "role": membership.role.value, "user_id": user.id},
    )
    if provisioned_by_platform:
        from backend.app.services import platform_audit

        platform_audit.record(
            db, action=platform_audit.TENANT_ADMIN_ACTIVATED, result=platform_audit.SUCCESS,
            tenant_actor=user, tenant_role=membership.role, ip_address=ip, user_agent=user_agent, organization=organization, target_type="membership",
            target_id=membership.id, details={"user_id": user.id, "admin_email": user.email, "role": membership.role.value},
        )
    _commit(db)
    return tokens

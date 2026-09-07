"""Authentication, sessions, password recovery and invitation acceptance.

Endpoints stay thin: everything that touches the database or decides an outcome
lives here. Every function that changes state commits its own transaction and
writes the matching audit row first.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.config import settings
from backend.app.core.exceptions import (
    AppException,
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
    ValidationAppError,
)
from backend.app.core.logging import logger
from backend.app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_reset_expiry,
    refresh_token_expiry,
    validate_password_strength,
    verify_password,
)
from backend.app.models import (
    AuditStatus,
    Membership,
    MemberRole,
    MembershipStatus,
    Organization,
    PasswordResetToken,
    RefreshToken,
    User,
    utcnow,
)
from backend.app.schemas.auth import (
    MeResponse,
    MembershipOut,
    OrganizationSummary,
    SignupRequest,
    UserOut,
)
from backend.app.schemas.organization import OrganizationOut, normalize_email
from backend.app.services import audit
from backend.app.services.email import frontend_url, send_email

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
INVALID_CREDENTIALS = "Invalid email or password."
NOT_A_MEMBER = "You are not an active member of any organization."


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
    """Create an access token + a persisted refresh token row (caller commits)."""
    access = create_access_token(user.id, membership.organization_id, membership.role.value)
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
    return TokenBundle(access, raw, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60), row


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
    )


# --- signup / login / refresh / logout ------------------------------------------------


def signup(db: Session, data: SignupRequest, ip: Optional[str], user_agent: Optional[str]) -> Tuple[TokenBundle, ActorContext]:
    email = normalize_email(data.email)
    if get_user_by_email(db, email) is not None:
        raise ConflictError("An account with this email already exists.", {"fields": {"email": "already registered"}})
    _password_problem(data.password)

    now = utcnow()
    organization = Organization(name=data.organization_name.strip(), slug=unique_slug(db, data.organization_name))
    db.add(organization)
    db.flush()
    user = User(
        email=email,
        full_name=data.full_name.strip(),
        hashed_password=hash_password(data.password),
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
        after={"email": user.email, "full_name": user.full_name, "organization_id": organization.id, "organization_name": organization.name, "slug": organization.slug},
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


def login(db: Session, email: str, password: str, ip: Optional[str], user_agent: Optional[str]) -> TokenBundle:
    email = normalize_email(email)
    user = get_user_by_email(db, email)
    # Always pay the bcrypt cost so response time does not reveal whether the email exists.
    stored_hash = user.hashed_password if (user and user.hashed_password) else _dummy_password_hash()
    password_ok = verify_password(password, stored_hash) and user is not None and bool(user.hashed_password)

    if user is None or not user.is_active:
        _record_login_failure(db, email, user, "unknown_or_inactive_user", ip, user_agent)
        db.commit()
        raise UnauthorizedError(INVALID_CREDENTIALS)

    now = utcnow()
    locked_until = aware(user.locked_until)
    if locked_until and locked_until > now:
        minutes = max(1, int((locked_until - now).total_seconds() // 60) + 1)
        _record_login_failure(db, email, user, "account_locked", ip, user_agent)
        db.commit()
        raise UnauthorizedError(
            f"Account is temporarily locked after too many failed attempts. Try again in {minutes} minute(s)."
        )

    if not password_ok:
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        message = INVALID_CREDENTIALS
        if user.failed_login_attempts >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
            message = f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes."
            reason = "locked_after_failures"
        else:
            reason = "bad_password"
        _record_login_failure(db, email, user, reason, ip, user_agent)
        db.commit()
        raise UnauthorizedError(message)

    membership = pick_membership(db, user.id)
    if membership is None:
        _record_login_failure(db, email, user, "no_active_membership", ip, user_agent)
        db.commit()
        raise UnauthorizedError(NOT_A_MEMBER)
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
        after={"organization_id": membership.organization_id, "role": membership.role.value},
    )
    _commit(db)
    return tokens


def refresh(db: Session, raw_token: str, ip: Optional[str], user_agent: Optional[str]) -> TokenBundle:
    token = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))).first()
    if token is None:
        raise UnauthorizedError("Refresh token is invalid.")
    if token.revoked_at is not None:
        # Replay of a rotated/revoked token: someone else may hold the chain. Kill every session.
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
            "The current password is incorrect.", {"fields": {"current_password": "incorrect"}}
        )
    _password_problem(new_password, "new_password")
    if verify_password(new_password, ctx.user.hashed_password):
        raise ValidationAppError(
            "The new password must differ from the current one.", {"fields": {"new_password": "unchanged"}}
        )
    ctx.user.hashed_password = hash_password(new_password)
    ctx.user.failed_login_attempts = 0
    ctx.user.locked_until = None
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


def forgot_password(db: Session, email: str, ip: Optional[str], user_agent: Optional[str]) -> Tuple[str, Optional[str]]:
    """Always succeeds. Returns (message, reset_url) where reset_url is set only when SMTP is off."""
    message = "If an account exists for that email address, a password reset link has been sent."
    email = normalize_email(email)
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return message, None

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
                f"<p>Hello {user.full_name},</p>"
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
    # Only hand the link back when this deployment has no SMTP at all (documented behaviour).
    reset_url = link if not settings.email_enabled else None
    return message, reset_url


def reset_password(db: Session, raw_token: str, new_password: str, ip: Optional[str], user_agent: Optional[str]) -> None:
    invalid = ValidationAppError(
        "This password reset link is invalid or has expired.", {"fields": {"token": "invalid_or_expired"}}
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
    token.used_at = utcnow()
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
    _commit(db)
    return tokens

"""Organization settings and team management."""
import re
from decimal import Decimal
from functools import lru_cache
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.config import settings
from backend.app.core.exceptions import (
    ConflictError,
    EntityNotFoundError,
    ForbiddenError,
    InvalidStateError,
    ValidationAppError,
)
from backend.app.core.logging import logger
from backend.app.core.security import generate_opaque_token, hash_token, invite_token_expiry
from backend.app.models import Membership, MemberRole, MembershipStatus, Organization, User, utcnow
from backend.app.schemas.common_refs import user_ref
from backend.app.schemas.organization import TeamMember, TeamMemberInvited, normalize_email
from backend.app.services import audit
from backend.app.services.auth_service import revoke_refresh_tokens
from backend.app.services.email import frontend_url, send_email

# --- organization ------------------------------------------------------------------

NULLABLE_TEXT_FIELDS = {
    "legal_name", "email", "phone", "website", "address_line1", "address_line2", "city", "state",
    "postal_code", "gstin", "pan", "invoice_notes", "invoice_terms", "logo_url",
}
REQUIRED_TEXT_FIELDS = {
    "name", "country", "default_currency", "timezone",
    "invoice_prefix", "quote_prefix", "payment_prefix", "subscription_prefix", "customer_prefix",
}
SEQUENCE_FIELDS = {
    "invoice_next_number", "quote_next_number", "payment_next_number",
    "subscription_next_number", "customer_next_number",
}
PERCENT_FIELDS = {"default_tax_rate_pct", "discount_approval_threshold_pct"}
INT_FIELDS = SEQUENCE_FIELDS | {"default_payment_terms_days"}
EDITABLE_FIELDS = NULLABLE_TEXT_FIELDS | REQUIRED_TEXT_FIELDS | INT_FIELDS | PERCENT_FIELDS

_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z0-9]{13}$")
_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@lru_cache(maxsize=1)
def _known_timezones() -> frozenset:
    try:
        import zoneinfo

        return frozenset(zoneinfo.available_timezones())
    except Exception:  # pragma: no cover - platform without tz database
        return frozenset()


def _commit(db: Session, conflict_message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Integrity error: %s", exc.orig)
        raise ConflictError(conflict_message) from exc


def _validate_organization_changes(organization: Organization, changes: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise + validate the patch. Returns the cleaned values or raises 422 with per-field messages."""
    errors: Dict[str, str] = {}
    cleaned: Dict[str, Any] = {}
    for field, value in changes.items():
        if field not in EDITABLE_FIELDS:
            errors[field] = "not editable"
            continue

        if field in NULLABLE_TEXT_FIELDS:
            value = value.strip() if isinstance(value, str) else value
            if value == "":
                value = None
            if field == "gstin" and value is not None:
                value = value.upper()
                if not _GSTIN_RE.match(value):
                    errors[field] = "must be a 15 character GSTIN"
                    continue
            if field == "pan" and value is not None:
                value = value.upper()
                if not _PAN_RE.match(value):
                    errors[field] = "must be a 10 character PAN"
                    continue
            if field == "email" and value is not None and not _EMAIL_RE.match(value):
                errors[field] = "is not a valid email address"
                continue
            cleaned[field] = value
            continue

        if value is None:
            errors[field] = "cannot be null"
            continue

        if field in REQUIRED_TEXT_FIELDS:
            value = str(value).strip()
            if field == "country":
                value = value.upper()
                if not re.fullmatch(r"[A-Z]{2}", value):
                    errors[field] = "must be a 2 letter ISO-3166 code"
                    continue
            elif field == "default_currency":
                value = value.upper()
                if not re.fullmatch(r"[A-Z]{3}", value):
                    errors[field] = "must be a 3 letter ISO-4217 code"
                    continue
            elif field == "timezone":
                known = _known_timezones()
                if not value or (known and value not in known):
                    errors[field] = "is not a known IANA timezone"
                    continue
            elif field == "name":
                if not value:
                    errors[field] = "cannot be empty"
                    continue
            else:  # prefixes
                if not value or len(value) > 12:
                    errors[field] = "must be 1 to 12 characters"
                    continue
            cleaned[field] = value
            continue

        if field in SEQUENCE_FIELDS:
            current = int(getattr(organization, field) or 1)
            if int(value) < current:
                errors[field] = f"cannot be decreased below the current value ({current})"
                continue
            cleaned[field] = int(value)
            continue

        if field == "default_payment_terms_days":
            if int(value) < 0 or int(value) > 365:
                errors[field] = "must be between 0 and 365"
                continue
            cleaned[field] = int(value)
            continue

        if field in PERCENT_FIELDS:
            try:
                pct = Decimal(str(value))
            except Exception:
                errors[field] = "must be a number"
                continue
            if pct < 0 or pct > 100:
                errors[field] = "must be between 0 and 100"
                continue
            cleaned[field] = pct.quantize(Decimal("0.01"))
            continue

    if errors:
        raise ValidationAppError("The organization update contains invalid fields.", {"fields": errors})
    return cleaned


def update_organization(db: Session, ctx: CurrentContext, changes: Dict[str, Any]) -> Organization:
    organization = ctx.organization
    cleaned = _validate_organization_changes(organization, changes)

    before: Dict[str, Any] = {}
    after: Dict[str, Any] = {}
    for field, value in cleaned.items():
        current = getattr(organization, field)
        if isinstance(current, Decimal) and isinstance(value, Decimal):
            unchanged = current.quantize(Decimal("0.01")) == value
        else:
            unchanged = current == value
        if unchanged:
            continue
        before[field] = current
        after[field] = value
        setattr(organization, field, value)

    if after:
        organization.updated_at = utcnow()
        audit.record(
            db,
            action="ORGANIZATION_UPDATED",
            entity_type="organization",
            entity_id=organization.id,
            entity_label=organization.name,
            ctx=ctx,
            before=before,
            after=after,
        )
        _commit(db, "The organization could not be updated because of conflicting data.")
        db.refresh(organization)
    return organization


# --- team ------------------------------------------------------------------------------


def _members_query(organization_id: str):
    return (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id)
        .order_by(Membership.created_at, Membership.id)
    )


def _inviters(db: Session, memberships: List[Membership]) -> Dict[str, User]:
    ids = {m.invited_by_id for m in memberships if m.invited_by_id}
    if not ids:
        return {}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids))).all()}


def serialize_member(membership: Membership, user: User, inviter: Optional[User]) -> Dict[str, Any]:
    return {
        "id": membership.id,
        "user": user_ref(user),
        "role": membership.role,
        "status": membership.status,
        "invited_by": user_ref(inviter),
        "invite_expires_at": membership.invite_expires_at,
        "accepted_at": membership.accepted_at,
        "created_at": membership.created_at,
    }


def list_team(db: Session, organization_id: str) -> List[TeamMember]:
    rows = db.execute(_members_query(organization_id)).all()
    inviters = _inviters(db, [m for m, _ in rows])
    return [TeamMember.model_validate(serialize_member(m, u, inviters.get(m.invited_by_id))) for m, u in rows]


def team_member(db: Session, membership: Membership) -> TeamMember:
    user = db.get(User, membership.user_id)
    inviter = db.get(User, membership.invited_by_id) if membership.invited_by_id else None
    return TeamMember.model_validate(serialize_member(membership, user, inviter))


def _get_membership(db: Session, organization_id: str, membership_id: str) -> Membership:
    membership = db.scalars(
        select(Membership).where(Membership.id == membership_id, Membership.organization_id == organization_id)
    ).first()
    if membership is None:
        raise EntityNotFoundError("Membership", membership_id)
    return membership


def _active_owner_count(db: Session, organization_id: str) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(Membership).where(
                Membership.organization_id == organization_id,
                Membership.role == MemberRole.OWNER,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        or 0
    )


def _assert_can_touch_owner(ctx: CurrentContext, target: Membership, new_role: Optional[MemberRole] = None) -> None:
    involves_owner = target.role == MemberRole.OWNER or new_role == MemberRole.OWNER
    if involves_owner and ctx.role != MemberRole.OWNER:
        raise ForbiddenError("Only an owner can grant or revoke the owner role.")


def invite_member(
    db: Session,
    ctx: CurrentContext,
    email: str,
    role: MemberRole,
    full_name: Optional[str],
) -> TeamMemberInvited:
    email = normalize_email(email)
    if role == MemberRole.OWNER and ctx.role != MemberRole.OWNER:
        raise ForbiddenError("Only an owner can invite another owner.")

    user = db.scalars(select(User).where(User.email == email)).first()
    membership: Optional[Membership] = None
    reinvited = False
    if user is None:
        user = User(
            email=email,
            full_name=(full_name or "").strip() or email.split("@", 1)[0],
            hashed_password=None,
        )
        db.add(user)
        db.flush()
    else:
        membership = db.scalars(
            select(Membership).where(Membership.organization_id == ctx.organization_id, Membership.user_id == user.id)
        ).first()
        if membership is not None and membership.status == MembershipStatus.ACTIVE:
            raise ConflictError("This user is already an active member of the organization.", {"fields": {"email": "already a member"}})
        if membership is not None and membership.role == MemberRole.OWNER and ctx.role != MemberRole.OWNER:
            raise ForbiddenError("Only an owner can re-invite an owner.")
        reinvited = membership is not None

    raw = generate_opaque_token()
    previous_status = membership.status.value if membership else None
    if membership is None:
        membership = Membership(organization_id=ctx.organization_id, user_id=user.id)
        db.add(membership)
    membership.role = role
    membership.status = MembershipStatus.INVITED
    membership.invited_by_id = ctx.user.id
    membership.invite_token_hash = hash_token(raw)
    membership.invite_expires_at = invite_token_expiry()
    membership.accepted_at = None
    membership.deactivated_at = None
    db.flush()

    link = frontend_url(f"accept-invitation?token={raw}")
    org_name = ctx.organization.name
    delivered = False
    try:
        delivered = send_email(
            user.email,
            f"You've been invited to {org_name} on Rooman Billing",
            (
                f"Hello {user.full_name},\n\n"
                f"{ctx.user.full_name} has invited you to join {org_name} on Rooman Billing as {role.value}.\n"
                f"Accept the invitation within {settings.INVITE_TOKEN_EXPIRE_HOURS} hours:\n\n{link}\n"
            ),
            html_body=(
                f"<p>Hello {user.full_name},</p>"
                f"<p><strong>{ctx.user.full_name}</strong> has invited you to join <strong>{org_name}</strong> "
                f"on Rooman Billing as <strong>{role.value}</strong>.</p>"
                f'<p><a href="{link}">Accept the invitation</a> (valid for {settings.INVITE_TOKEN_EXPIRE_HOURS} hours)</p>'
            ),
        )
    except Exception as exc:  # delivery problems must not lose the invitation
        logger.error("Invitation email to %s failed: %s", user.email, exc)
        delivered = False

    audit.record(
        db,
        action="TEAM_MEMBER_INVITED",
        entity_type="membership",
        entity_id=membership.id,
        entity_label=user.email,
        ctx=ctx,
        before={"status": previous_status} if reinvited else None,
        after={"email": user.email, "role": role.value, "status": MembershipStatus.INVITED.value, "email_delivered": delivered, "reinvited": reinvited},
    )
    _commit(db, "This user is already a member of the organization.")
    db.refresh(membership)

    data = serialize_member(membership, user, ctx.user)
    if not settings.email_enabled:
        data["invite_url"] = link
    return TeamMemberInvited.model_validate(data)


def change_role(db: Session, ctx: CurrentContext, membership_id: str, new_role: MemberRole) -> TeamMember:
    membership = _get_membership(db, ctx.organization_id, membership_id)
    if membership.user_id == ctx.user.id:
        raise ForbiddenError("You cannot change your own role.")
    _assert_can_touch_owner(ctx, membership, new_role)
    if membership.status == MembershipStatus.DEACTIVATED:
        raise InvalidStateError("Cannot change the role of a deactivated member.")
    if (
        membership.role == MemberRole.OWNER
        and new_role != MemberRole.OWNER
        and membership.status == MembershipStatus.ACTIVE
        and _active_owner_count(db, ctx.organization_id) <= 1
    ):
        raise InvalidStateError("An organization must keep at least one active owner.")

    if membership.role != new_role:
        before = {"role": membership.role.value}
        membership.role = new_role
        audit.record(
            db,
            action="TEAM_ROLE_CHANGED",
            entity_type="membership",
            entity_id=membership.id,
            entity_label=db.get(User, membership.user_id).email,
            ctx=ctx,
            before=before,
            after={"role": new_role.value},
        )
        _commit(db, "The membership could not be updated.")
        db.refresh(membership)
    return team_member(db, membership)


def deactivate_member(db: Session, ctx: CurrentContext, membership_id: str) -> None:
    membership = _get_membership(db, ctx.organization_id, membership_id)
    if membership.user_id == ctx.user.id:
        raise ForbiddenError("You cannot deactivate your own membership.")
    _assert_can_touch_owner(ctx, membership)
    if membership.status == MembershipStatus.DEACTIVATED:
        raise InvalidStateError("This member is already deactivated.")
    if (
        membership.role == MemberRole.OWNER
        and membership.status == MembershipStatus.ACTIVE
        and _active_owner_count(db, ctx.organization_id) <= 1
    ):
        raise InvalidStateError("An organization must keep at least one active owner.")

    before = {"status": membership.status.value, "role": membership.role.value}
    membership.status = MembershipStatus.DEACTIVATED
    membership.deactivated_at = utcnow()
    membership.invite_token_hash = None
    membership.invite_expires_at = None
    revoked = revoke_refresh_tokens(db, membership.user_id, organization_id=ctx.organization_id)
    audit.record(
        db,
        action="TEAM_MEMBER_DEACTIVATED",
        entity_type="membership",
        entity_id=membership.id,
        entity_label=db.get(User, membership.user_id).email,
        ctx=ctx,
        before=before,
        after={"status": MembershipStatus.DEACTIVATED.value, "role": membership.role.value, "sessions_revoked": revoked},
    )
    _commit(db, "The membership could not be deactivated.")

"""Platform identity: Rooman staff who operate the platform (docs/platform-administration-design.md).

A completely separate security principal from tenant users. Platform staff have no Membership in
any organization, sign in on /api/v1/platform/auth with mandatory TOTP, and receive tokens signed
with a different key and audience from tenant tokens. None of these tables use TenantMixin and
none reference organizations: platform data never cascades from a tenant.
"""
import enum

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, String

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow


def _enum_values(members):
    return [m.value for m in members]


class PlatformRole(str, enum.Enum):
    """Platform staff roles. There is no wildcard/superuser role: each grants named capabilities.

    PLATFORM_ADMINISTRATOR is what the product calls "Super Admin".
    """

    PLATFORM_ADMINISTRATOR = "platform_administrator"
    PLATFORM_OPERATIONS = "platform_operations"
    PLATFORM_SUPPORT = "platform_support"


class PlatformStaff(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_staff"

    email = Column(String(255), nullable=False, unique=True, index=True)  # normalised lower-case
    full_name = Column(String(200), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(
        Enum(
            PlatformRole,
            name="platform_role",
            native_enum=False,
            create_constraint=False,
            length=32,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    is_active = Column(Boolean, nullable=False, default=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    # Mandatory TOTP: an account without totp_enabled_at can never complete sign-in.
    totp_secret = Column(String(255), nullable=True)  # encrypted (core/security.encrypt_secret)
    totp_enabled_at = Column(DateTime(timezone=True), nullable=True)
    totp_last_used_step = Column(Integer, nullable=True)
    # Access tokens issued before this instant are rejected (revoke everything for this person).
    tokens_valid_after = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)


class PlatformSession(UUIDPrimaryKeyMixin, Base):
    """One signed-in browser/device of a platform staff member.

    Only a SHA-256 hash of the opaque refresh secret is stored. Refresh rotates the secret in
    place; the previous hash is kept so presenting it again (a stolen, already-rotated secret)
    revokes the session.
    """

    __tablename__ = "platform_sessions"

    staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=False, index=True)
    refresh_token_hash = Column(String(64), nullable=False, unique=True, index=True)
    previous_refresh_token_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    idle_expires_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)  # absolute lifetime
    mfa_verified_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(String(64), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)


class PlatformLoginChallenge(UUIDPrimaryKeyMixin, Base):
    """The second step of a platform sign-in: proves the password step succeeded.

    Single use (consumed_at), short-lived, and invalidated after too many wrong codes. Grants
    nothing by itself: only /platform/auth/2fa with a valid TOTP code turns it into a session.
    """

    __tablename__ = "platform_login_challenges"

    staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    failed_attempts = Column(Integer, nullable=False, default=0)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)


class PlatformAuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only record of platform security events. Never references (or cascades from) a
    tenant, and is never updated or deleted by application code. Never holds passwords, TOTP
    codes or secrets, or token values."""

    __tablename__ = "platform_audit_logs"

    occurred_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    # Null only when the event has no known staff member (e.g. sign-in with an unknown email).
    platform_staff_id = Column(
        String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    staff_email_snapshot = Column(String(255), nullable=True)
    action = Column(String(64), nullable=False, index=True)
    result = Column(String(16), nullable=False)  # success | failure | denied
    session_id = Column(String(36), nullable=True, index=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)
    details = Column(JSON, nullable=True)

"""Platform identity: Rooman staff who operate the platform (docs/platform-administration-design.md).

A completely separate security principal from tenant users. Platform staff have no Membership in
any organization, sign in on /api/v1/platform/auth with email and password, and receive tokens signed
with a different key and audience from tenant tokens. None of these tables use TenantMixin and
none reference organizations: platform data never cascades from a tenant.
"""
import enum

from sqlalchemy import DDL, JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, event

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
    # Unused since sign-in became email + password only; kept (no destructive migration) so data
    # from the former TOTP sign-in stays intact. Never read for authentication.
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
    # Step-up re-authentication (current password) for sensitive actions, bound to THIS session. It is
    # never extended: a new step-up sets both values afresh, and it expires with the session (and on
    # revocation / logout / logout-all / password or 2FA reset, via revoked_at and tokens_valid_after).
    step_up_at = Column(DateTime(timezone=True), nullable=True)
    step_up_expires_at = Column(DateTime(timezone=True), nullable=True)


class PlatformLoginChallenge(UUIDPrimaryKeyMixin, Base):
    """Unused: the second step of the former two-step (TOTP) platform sign-in. Sign-in is now one
    step (email + password), so no challenge is created any more; the table is kept so existing
    rows and migrations stay intact.
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
    # Phase 3 (design section 10): the acting role, the target and the justification.
    # organization_id is a plain column with NO foreign key, so platform history outlives a tenant.
    staff_role_snapshot = Column(String(32), nullable=True)
    target_type = Column(String(32), nullable=True)
    target_id = Column(String(36), nullable=True)
    organization_id = Column(String(36), nullable=True, index=True)
    organization_name_snapshot = Column(String(200), nullable=True)
    reason = Column(String(500), nullable=True)
    ticket_ref = Column(String(100), nullable=True)


# --- append-only audit log, enforced by PostgreSQL ------------------------------------------------------
# Migration 0028 installs the same function and triggers on migrated databases; this DDL event adds
# them to databases built with metadata.create_all (the PostgreSQL test suite). Any UPDATE, DELETE
# or TRUNCATE of platform_audit_logs - from the ORM, raw SQL, or any role that does not own the
# table - raises. Only the table owner / a superuser can disable the triggers (see
# docs/platform-console-deployment.md, "Audit log immutability"). SQLite has no equivalent.
PLATFORM_AUDIT_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION platform_audit_logs_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'platform_audit_logs is append-only: % is not allowed', TG_OP
        USING ERRCODE = '42501';
END
$$
"""
PLATFORM_AUDIT_APPEND_ONLY_TRIGGERS = (
    "DROP TRIGGER IF EXISTS platform_audit_logs_no_update_delete ON platform_audit_logs",
    "CREATE TRIGGER platform_audit_logs_no_update_delete BEFORE UPDATE OR DELETE ON platform_audit_logs "
    "FOR EACH ROW EXECUTE FUNCTION platform_audit_logs_append_only()",
    "DROP TRIGGER IF EXISTS platform_audit_logs_no_truncate ON platform_audit_logs",
    "CREATE TRIGGER platform_audit_logs_no_truncate BEFORE TRUNCATE ON platform_audit_logs "
    "FOR EACH STATEMENT EXECUTE FUNCTION platform_audit_logs_append_only()",
)

for _statement in (PLATFORM_AUDIT_APPEND_ONLY_FUNCTION, *PLATFORM_AUDIT_APPEND_ONLY_TRIGGERS):
    event.listen(PlatformAuditLog.__table__, "after_create", DDL(_statement.replace("%", "%%")).execute_if(dialect="postgresql"))

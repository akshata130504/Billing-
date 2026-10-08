"""Organizations (tenants), users, memberships and auth tokens."""
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class MemberRole(str, enum.Enum):
    OWNER = "owner"  # full control incl. billing settings & deleting the org
    ADMIN = "admin"  # manage team, settings, approve requests
    FINANCE = "finance"  # create/edit customers, quotes, invoices, payments
    VIEWER = "viewer"  # read-only


# Higher number = more privilege. Used by require_role().
ROLE_RANK = {
    MemberRole.VIEWER: 10,
    MemberRole.FINANCE: 20,
    MemberRole.ADMIN: 30,
    MemberRole.OWNER: 40,
}


class MembershipStatus(str, enum.Enum):
    INVITED = "invited"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class OrganizationStatus(str, enum.Enum):
    """Platform lifecycle of a tenant. Only ACTIVE organizations run billing automation."""

    # Effective trial states, computed by services/org_access.py for an ACTIVE organization whose
    # module_access is 'trial' (the trial is a phase of an active organization, not a stored status;
    # these values stay valid for rows written before that change).
    TRIAL = "trial"
    TRIAL_EXPIRED = "trial_expired"
    # Self-service signup: waits here until a Platform Administrator approves (-> ACTIVE, trial starts)
    # or rejects (-> REJECTED) the organization.
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    PENDING_DELETION = "pending_deletion"
    DELETED = "deleted"


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name = Column(String(200), nullable=False)
    slug = Column(String(80), nullable=False, unique=True, index=True)
    legal_name = Column(String(200), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(40), nullable=True)
    website = Column(String(255), nullable=True)

    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(120), nullable=True)
    state = Column(String(120), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(2), nullable=False, default="IN")

    gstin = Column(String(15), nullable=True)
    pan = Column(String(10), nullable=True)
    default_currency = Column(String(3), nullable=False, default="INR")
    timezone = Column(String(64), nullable=False, default="Asia/Kolkata")

    # Numbering sequences (per tenant)
    invoice_prefix = Column(String(12), nullable=False, default="INV-")
    invoice_next_number = Column(Integer, nullable=False, default=1)
    quote_prefix = Column(String(12), nullable=False, default="QT-")
    quote_next_number = Column(Integer, nullable=False, default=1)
    payment_prefix = Column(String(12), nullable=False, default="PAY-")
    payment_next_number = Column(Integer, nullable=False, default=1)
    subscription_prefix = Column(String(12), nullable=False, default="SUB-")
    subscription_next_number = Column(Integer, nullable=False, default=1)
    customer_prefix = Column(String(12), nullable=False, default="CUS-")
    customer_next_number = Column(Integer, nullable=False, default=1)

    # Billing policy
    default_payment_terms_days = Column(Integer, nullable=False, default=30)
    default_tax_rate_pct = Column(Numeric(5, 2), nullable=False, default=18)
    # Quote/invoice discounts above this percentage need an admin/owner approval.
    discount_approval_threshold_pct = Column(Numeric(5, 2), nullable=False, default=20)
    invoice_notes = Column(Text, nullable=True)
    invoice_terms = Column(Text, nullable=True)
    logo_url = Column(String(500), nullable=True)
    # Platform lifecycle. Changed only by the platform console (services/platform_org_service.py).
    # Anything but ACTIVE, or jobs_paused, makes the scheduler skip this organization's billing
    # automation (services/org_lifecycle.py). Stored as plain VARCHAR values, not a native enum type.
    status = Column(
        Enum(
            OrganizationStatus,
            name="organization_status",
            native_enum=False,
            create_constraint=False,
            length=20,
            values_callable=lambda members: [m.value for m in members],
            validate_strings=True,
        ),
        nullable=False,
        default=OrganizationStatus.ACTIVE,
        server_default=OrganizationStatus.ACTIVE.value,
    )
    jobs_paused = Column(Boolean, nullable=False, default=False, server_default=false())
    # Last lifecycle transition (the full history lives in platform_audit_logs).
    status_changed_at = Column(DateTime(timezone=True), nullable=True)
    status_changed_by_staff_id = Column(
        String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True
    )
    status_reason = Column(String(500), nullable=True)
    # PENDING_DELETION only: the earliest time the (future, separately approved) purge may run.
    deletion_scheduled_for = Column(DateTime(timezone=True), nullable=True)
    # Trial (UTC): set when a Platform Administrator approves a self-service organization. Expiry is
    # decided by the backend from trial_ends_at on every request (services/org_access.py).
    trial_started_at = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    # Active + invited members allowed. NULL = no limit (organizations that predate subscriptions).
    seat_limit = Column(Integer, nullable=True)
    # 'unrestricted' (every module; organizations that predate entitlements), 'trial' (self-service
    # signup: free trial after approval, then a subscription request) or 'entitled' (base modules +
    # organization_entitlements). See models/subscription_access.py.
    module_access = Column(String(20), nullable=False, default="unrestricted", server_default="unrestricted")

    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(200), nullable=False)
    phone = Column(String(40), nullable=True)
    # Null until an invited user sets their password.
    hashed_password = Column(String(128), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    # Revocation cutoff: access tokens with iat issued before this timestamp are rejected.
    tokens_valid_after = Column(DateTime(timezone=True), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    # Two-factor authentication (RFC 6238 TOTP). The seed is Fernet-encrypted with a key
    # derived from SECRET_KEY. A seed with totp_enabled_at NULL is a pending (unconfirmed) setup.
    totp_secret = Column(String(255), nullable=True)
    totp_enabled_at = Column(DateTime(timezone=True), nullable=True)
    # Last accepted TOTP time step: a code can never be replayed within its validity window.
    totp_last_used_step = Column(Integer, nullable=True)

    memberships = relationship(
        "Membership", back_populates="user", foreign_keys="Membership.user_id", cascade="all, delete-orphan"
    )


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),)

    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum(MemberRole, name="member_role"), nullable=False, default=MemberRole.VIEWER)
    status = Column(Enum(MembershipStatus, name="membership_status"), nullable=False, default=MembershipStatus.ACTIVE)
    invited_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invite_token_hash = Column(String(64), nullable=True, index=True)
    invite_expires_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="memberships")
    user = relationship("User", back_populates="memberships", foreign_keys=[user_id])


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    # When a token is rotated we record its successor so reuse of the old one can
    # be detected and the whole chain revoked.
    replaced_by_id = Column(String(36), nullable=True)
    user_agent = Column(String(400), nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PendingSignup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pending_signups"

    email = Column(String(255), nullable=False, unique=True, index=True)
    organization_name = Column(String(200), nullable=False)
    full_name = Column(String(200), nullable=False)
    hashed_password = Column(String(128), nullable=False)
    otp_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    last_sent_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)



class LoginThrottle(UUIDPrimaryKeyMixin, Base):
    """Failed-attempt counters for credential checks, keyed per (scope, subject, client IP).

    scope="login": subject is the normalised email (known or not, so the response never
    reveals whether an account exists). Keying on the IP too means an attacker elsewhere
    cannot lock the real user out; the per-IP slowapi limit caps spraying across accounts.
    scope="mfa": subject is the user id and ip_address is "" (account-wide) - only someone
    who already knows the password can reach the TOTP step.
    """

    __tablename__ = "login_throttles"
    __table_args__ = (UniqueConstraint("scope", "subject", "ip_address", name="uq_login_throttle_key"),)

    scope = Column(String(16), nullable=False)
    subject = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(64), nullable=False, default="")
    failures = Column(Integer, nullable=False, default=0)
    window_started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    locked_until = Column(DateTime(timezone=True), nullable=True)

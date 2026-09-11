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

    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(200), nullable=False)
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

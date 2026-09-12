"""Customer Portal models: portal preferences, customer users, and portal sessions."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CustomerPortalSettings(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Organization-wide configuration for the Customer Portal."""
    __tablename__ = "customer_portal_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_portal_settings_organization"),
    )

    portal_name = Column(String(100), nullable=False, default="Billing Portal")
    portal_url_slug = Column(String(64), nullable=True, index=True)
    banner_message = Column(Text, nullable=True)
    auto_invite_enabled = Column(Boolean, nullable=False, default=False)
    mfa_enabled = Column(Boolean, nullable=False, default=False)
    prevent_duplicate_payments = Column(Boolean, nullable=False, default=True)
    allow_self_signup = Column(Boolean, nullable=False, default=False)
    allow_document_upload = Column(Boolean, nullable=False, default=True)
    allow_document_forwarding = Column(Boolean, nullable=False, default=True)
    allow_save_payment_methods = Column(Boolean, nullable=False, default=True)
    save_payment_method_default = Column(Boolean, nullable=False, default=True)
    prevent_deselecting_save_payment = Column(Boolean, nullable=False, default=False)
    enable_identity_verification_public_links = Column(Boolean, nullable=False, default=True)
    trials_allow_customer_extension = Column(Boolean, nullable=False, default=True)
    trials_max_extensions = Column(Integer, nullable=False, default=2)
    trials_activate_immediately = Column(Boolean, nullable=False, default=True)


class CustomerPortalUser(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """An authenticated customer contact with portal credentials."""
    __tablename__ = "customer_portal_users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_portal_user_email_per_org"),
    )

    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(200), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    mfa_secret = Column(String(64), nullable=True)
    mfa_enabled = Column(Boolean, nullable=False, default=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer")
    sessions = relationship("CustomerPortalSession", back_populates="user", cascade="all, delete-orphan")


class CustomerPortalSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Active customer session token for portal access."""
    __tablename__ = "customer_portal_sessions"

    portal_user_id = Column(String(36), ForeignKey("customer_portal_users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(128), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    is_revoked = Column(Boolean, nullable=False, default=False)

    user = relationship("CustomerPortalUser", back_populates="sessions")


class CustomerPortalInvitation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Secure, single-use, time-limited invitation for customer portal activation."""
    __tablename__ = "customer_portal_invitations"

    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    invited_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer")
    invited_by = relationship("User")

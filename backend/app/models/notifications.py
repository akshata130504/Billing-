"""Notification templates and delivery logs across channels (email, sms, webhook)."""
from __future__ import annotations

import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"


class NotificationDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class NotificationTemplate(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Versioned document and message templates for billing notifications."""
    __tablename__ = "notification_templates"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", "version", name="uq_notif_template_code_version"),
    )

    name = Column(String(120), nullable=False)
    code = Column(String(64), nullable=False, index=True)  # e.g., "invoice_issued", "payment_failed", "trial_expiring"
    channel = Column(Enum(NotificationChannel, name="notification_channel"), nullable=False, default=NotificationChannel.EMAIL)
    subject_template = Column(String(255), nullable=True)
    body_template = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)
    description = Column(String(300), nullable=True)

    deliveries = relationship("NotificationDelivery", back_populates="template")


class NotificationDelivery(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Audit and delivery record of every dispatched customer notification."""
    __tablename__ = "notification_deliveries"

    template_id = Column(String(36), ForeignKey("notification_templates.id", ondelete="SET NULL"), nullable=True, index=True)
    recipient = Column(String(255), nullable=False, index=True)
    channel = Column(Enum(NotificationChannel, name="notification_delivery_channel"), nullable=False, default=NotificationChannel.EMAIL)
    status = Column(Enum(NotificationDeliveryStatus, name="notification_delivery_status"), nullable=False, default=NotificationDeliveryStatus.PENDING, index=True)
    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=True)
    provider_message_id = Column(String(120), nullable=True, index=True)
    attempts = Column(Integer, nullable=False, default=1)
    error = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    template = relationship("NotificationTemplate", back_populates="deliveries")


# --- Per-user, per-organization notification state -------------------------------------------------------------


class UserNotificationPreference(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A user's in-app notification preferences inside one organization.

    ``preferences`` holds a flat ``{key: bool}`` map validated against
    ``schemas.notifications.NotificationPreferencesIn`` (unknown keys are rejected).
    A user who belongs to several organizations has one row per organization.
    """
    __tablename__ = "user_notification_preferences"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_user_notif_prefs_org_user"),
    )

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    preferences = Column(JSON, nullable=False, default=dict)


class NotificationReadState(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Read / dismissed marker for one header (action-center) notification, per user and organization.

    ``notification_key`` is the stable action-center item id (e.g. ``overdue:<invoice id>``).
    """
    __tablename__ = "notification_read_states"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "notification_key", name="uq_notif_read_state_org_user_key"),
        Index("ix_notif_read_states_user_org_updated", "user_id", "organization_id", "updated_at"),
    )

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    notification_key = Column(String(160), nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)

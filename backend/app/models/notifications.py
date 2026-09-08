"""Notification templates and delivery logs across channels (email, sms, webhook)."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
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

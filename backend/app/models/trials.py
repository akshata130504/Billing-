"""Trial management models: trial periods, extensions, conversion attempts, and reminders."""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
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


class TrialPeriodStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CONVERTED = "converted"
    CANCELLED = "cancelled"


class TrialConversionAttemptType(str, enum.Enum):
    AUTOMATIC_TRIAL_END = "automatic_trial_end"
    CUSTOMER_EARLY_CONVERSION = "customer_early_conversion"
    ADMIN_CONVERSION = "admin_conversion"


class TrialConversionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TrialPeriod(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Tracks the trial lifecycle, configuration, and parameters for a subscription."""
    __tablename__ = "trial_periods"
    __table_args__ = (
        UniqueConstraint("organization_id", "subscription_id", name="uq_trial_period_subscription"),
    )

    subscription_id = Column(
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trial_start_date = Column(Date, nullable=False)
    trial_end_date = Column(Date, nullable=False, index=True)
    extension_count = Column(Integer, nullable=False, default=0)
    max_extensions_allowed = Column(Integer, nullable=False, default=2)
    allow_customer_extension = Column(Boolean, nullable=False, default=True)
    allow_early_conversion = Column(Boolean, nullable=False, default=True)
    auto_charge_enabled = Column(Boolean, nullable=False, default=True)
    fallback_plan_id = Column(String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    status = Column(
        Enum(TrialPeriodStatus, name="trial_period_status"),
        nullable=False,
        default=TrialPeriodStatus.ACTIVE,
        index=True,
    )
    converted_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    subscription = relationship("Subscription", back_populates="trial_period")
    fallback_plan = relationship("Plan", foreign_keys=[fallback_plan_id])
    extensions = relationship("TrialExtension", back_populates="trial_period", cascade="all, delete-orphan")
    conversion_attempts = relationship("TrialConversionAttempt", back_populates="trial_period", cascade="all, delete-orphan")
    reminders = relationship("TrialReminder", back_populates="trial_period", cascade="all, delete-orphan")


class TrialExtension(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Audit record for an extension applied to a subscription trial."""
    __tablename__ = "trial_extensions"

    trial_period_id = Column(
        String(36),
        ForeignKey("trial_periods.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id = Column(
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_trial_end = Column(Date, nullable=False)
    new_trial_end = Column(Date, nullable=False)
    extended_days = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=True)
    is_customer_initiated = Column(Boolean, nullable=False, default=False)
    extended_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    trial_period = relationship("TrialPeriod", back_populates="extensions")


class TrialConversionAttempt(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Tracks conversion attempts, payment outcomes, and resulting invoices."""
    __tablename__ = "trial_conversion_attempts"

    trial_period_id = Column(
        String(36),
        ForeignKey("trial_periods.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id = Column(
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_type = Column(
        Enum(TrialConversionAttemptType, name="trial_conversion_attempt_type"),
        nullable=False,
        default=TrialConversionAttemptType.AUTOMATIC_TRIAL_END,
    )
    status = Column(
        Enum(TrialConversionStatus, name="trial_conversion_status"),
        nullable=False,
        default=TrialConversionStatus.PENDING,
    )
    payment_method_id = Column(String(36), ForeignKey("customer_payment_methods.id", ondelete="SET NULL"), nullable=True)
    payment_attempt_id = Column(String(36), ForeignKey("payment_attempts.id", ondelete="SET NULL"), nullable=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)
    error_message = Column(Text, nullable=True)

    trial_period = relationship("TrialPeriod", back_populates="conversion_attempts")


class TrialReminder(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Tracks sent and scheduled expiry warning notifications."""
    __tablename__ = "trial_reminders"

    trial_period_id = Column(
        String(36),
        ForeignKey("trial_periods.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id = Column(
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reminder_type = Column(String(64), nullable=False)
    scheduled_for = Column(Date, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    notification_delivery_id = Column(String(36), ForeignKey("notification_deliveries.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(32), nullable=False, default="pending")

    trial_period = relationship("TrialPeriod", back_populates="reminders")

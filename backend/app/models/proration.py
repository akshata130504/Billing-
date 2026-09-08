"""Proration adjustment and subscription change tracking models."""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class SubscriptionChangeType(str, enum.Enum):
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    QUANTITY_CHANGE = "quantity_change"
    ADDON_CHANGE = "addon_change"
    CANCELLATION = "cancellation"


class SubscriptionChangeStatus(str, enum.Enum):
    PREVIEWED = "previewed"
    SCHEDULED = "scheduled"
    APPLIED = "applied"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ProrationEffectiveType(str, enum.Enum):
    IMMEDIATE = "immediate"
    END_OF_TERM = "end_of_term"
    SCHEDULED = "scheduled"


class SubscriptionChange(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Tracks requested, previewed, scheduled, and applied subscription modifications."""
    __tablename__ = "subscription_changes"

    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    change_type = Column(Enum(SubscriptionChangeType, name="sub_change_type"), nullable=False, default=SubscriptionChangeType.UPGRADE)
    status = Column(Enum(SubscriptionChangeStatus, name="sub_change_status"), nullable=False, default=SubscriptionChangeStatus.PREVIEWED, index=True)
    effective_type = Column(Enum(ProrationEffectiveType, name="proration_effective_type"), nullable=False, default=ProrationEffectiveType.IMMEDIATE)
    effective_date = Column(Date, nullable=False, default=date.today)

    target_plan_id = Column(String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    target_quantity = Column(Numeric(12, 3), nullable=True)
    proration_enabled = Column(Boolean, nullable=False, default=True)

    old_plan_amount = Column(Numeric(14, 2), nullable=False, default=0)
    new_plan_amount = Column(Numeric(14, 2), nullable=False, default=0)
    prorated_credit = Column(Numeric(14, 2), nullable=False, default=0)
    prorated_charge = Column(Numeric(14, 2), nullable=False, default=0)
    net_amount = Column(Numeric(14, 2), nullable=False, default=0)

    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    credit_note_id = Column(String(36), ForeignKey("credit_notes.id", ondelete="SET NULL"), nullable=True, index=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    subscription = relationship("Subscription")
    target_plan = relationship("Plan")
    invoice = relationship("Invoice")
    credit_note = relationship("CreditNote")
    adjustment = relationship("ProrationAdjustment", back_populates="subscription_change", uselist=False, cascade="all, delete-orphan")


class ProrationAdjustment(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Detailed formula inputs and mathematical evidence for a prorated subscription adjustment."""
    __tablename__ = "proration_adjustments"

    subscription_change_id = Column(String(36), ForeignKey("subscription_changes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)

    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    total_days = Column(Integer, nullable=False)
    days_used = Column(Integer, nullable=False)
    days_remaining = Column(Integer, nullable=False)

    old_unit_price = Column(Numeric(14, 2), nullable=False, default=0)
    new_unit_price = Column(Numeric(14, 2), nullable=False, default=0)
    old_quantity = Column(Numeric(12, 3), nullable=False, default=1)
    new_quantity = Column(Numeric(12, 3), nullable=False, default=1)

    unused_credit = Column(Numeric(14, 2), nullable=False, default=0)
    remaining_charge = Column(Numeric(14, 2), nullable=False, default=0)
    net_adjustment = Column(Numeric(14, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="INR")
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    subscription_change = relationship("SubscriptionChange", back_populates="adjustment")
    subscription = relationship("Subscription")

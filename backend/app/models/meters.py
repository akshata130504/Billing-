"""Usage meters, raw usage events, and aggregated rated billing models."""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
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
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class AggregationType(str, enum.Enum):
    SUM = "sum"
    MAX = "max"
    COUNT = "count"
    LAST = "last"


class UsageEventStatus(str, enum.Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CORRECTED = "corrected"


class UsageAggregateStatus(str, enum.Enum):
    OPEN = "open"
    CALCULATED = "calculated"
    FINALIZED = "finalized"


class UsageMeter(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Definition of a measurable consumption metric (e.g. API requests, gigabytes)."""
    __tablename__ = "usage_meters"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_usage_meter_code_per_org"),
    )

    code = Column(String(64), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(String(300), nullable=True)
    unit_name = Column(String(40), nullable=False, default="unit")
    aggregation_type = Column(Enum(AggregationType, name="meter_aggregation_type"), nullable=False, default=AggregationType.SUM)
    is_active = Column(Boolean, nullable=False, default=True)
    # Flat per-unit rate usage on this meter is billed at. NULL = unpriced: usage is
    # rated at 0 and flagged rather than silently billed at the plan's recurring price.
    unit_price = Column(Numeric(18, 4), nullable=True)

    events = relationship("UsageEvent", back_populates="meter", cascade="all, delete-orphan")
    aggregates = relationship("UsageAggregate", back_populates="meter")


class UsageEvent(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Raw, append-only usage event record submitted via API or batch."""
    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "meter_id", "idempotency_key", name="uq_usage_event_idempotency"),
    )

    meter_id = Column(String(36), ForeignKey("usage_meters.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=True, index=True)

    quantity = Column(Numeric(16, 4), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    idempotency_key = Column(String(128), nullable=False, index=True)
    properties = Column(JSON, nullable=True)
    status = Column(Enum(UsageEventStatus, name="usage_event_status"), nullable=False, default=UsageEventStatus.ACCEPTED, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    meter = relationship("UsageMeter", back_populates="events")
    customer = relationship("Customer")
    subscription = relationship("Subscription")


class UsageAggregate(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Aggregated, rated usage for a subscription over a billing cycle period."""
    __tablename__ = "usage_aggregates"
    __table_args__ = (
        UniqueConstraint("organization_id", "meter_id", "subscription_id", "period_start", "period_end", name="uq_sub_meter_period"),
    )

    meter_id = Column(String(36), ForeignKey("usage_meters.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    billing_cycle_id = Column(String(36), ForeignKey("billing_cycles.id", ondelete="SET NULL"), nullable=True, index=True)

    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    total_quantity = Column(Numeric(16, 4), nullable=False, default=0)
    rated_amount = Column(Numeric(14, 2), nullable=False, default=0)
    status = Column(Enum(UsageAggregateStatus, name="usage_aggregate_status"), nullable=False, default=UsageAggregateStatus.OPEN, index=True)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)

    meter = relationship("UsageMeter", back_populates="aggregates")
    subscription = relationship("Subscription")
    billing_cycle = relationship("BillingCycle")
    invoice = relationship("Invoice")

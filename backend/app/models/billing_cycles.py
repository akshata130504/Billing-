"""Billing cycle, subscription item, and immutable price snapshot models."""
from __future__ import annotations

import enum

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from backend.app.models.catalog import BillingInterval, PricingModel


class SubscriptionItemType(str, enum.Enum):
    PLAN = "plan"
    ADDON = "addon"
    METERED = "metered"


class SubscriptionItemStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class PriceSnapshot(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Immutable snapshot of commercial terms applied to a subscription item."""
    __tablename__ = "price_snapshots"

    plan_id = Column(String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True)
    unit_amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    billing_interval = Column(Enum(BillingInterval, name="billing_interval_snapshot"), nullable=False, default=BillingInterval.MONTHLY)
    interval_count = Column(Integer, nullable=False, default=1)
    pricing_model = Column(Enum(PricingModel, name="pricing_model_snapshot"), nullable=False, default=PricingModel.FLAT)

    tax_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    setup_fee = Column(Numeric(14, 2), nullable=False, default=0)
    trial_days = Column(Integer, nullable=False, default=0)
    snapshot_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    metadata_ = Column("metadata", JSON, nullable=True)

    plan = relationship("Plan")


class SubscriptionItem(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Individual line item or component within a subscription (plans, add-ons, metered items)."""
    __tablename__ = "subscription_items"

    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True)
    price_snapshot_id = Column(String(36), ForeignKey("price_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    item_type = Column(Enum(SubscriptionItemType, name="subscription_item_type"), nullable=False, default=SubscriptionItemType.PLAN)
    quantity = Column(Numeric(12, 3), nullable=False, default=1)
    unit_price = Column(Numeric(14, 2), nullable=False, default=0)
    status = Column(Enum(SubscriptionItemStatus, name="subscription_item_status"), nullable=False, default=SubscriptionItemStatus.ACTIVE)

    subscription = relationship("Subscription", back_populates="subscription_items")
    plan = relationship("Plan")
    price_snapshot = relationship("PriceSnapshot")


class BillingCycleStatus(str, enum.Enum):
    OPEN = "open"
    FINALIZED = "finalized"
    INVOICED = "invoiced"
    CANCELLED = "cancelled"


class BillingCycle(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Tracks each recurring service period and links it to the generated invoice."""
    __tablename__ = "billing_cycles"
    __table_args__ = (
        UniqueConstraint("organization_id", "subscription_id", "cycle_number", name="uq_sub_cycle_number"),
    )

    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    cycle_number = Column(Integer, nullable=False, default=1)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    status = Column(Enum(BillingCycleStatus, name="billing_cycle_status"), nullable=False, default=BillingCycleStatus.OPEN, index=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    finalized_at = Column(DateTime(timezone=True), nullable=True)

    subscription = relationship("Subscription")
    invoice = relationship("Invoice")


class SchedulerHeartbeat(Base):
    """Last-run bookkeeping for the background billing scheduler (one row per job).

    Written by scheduler.run_billing_jobs after every run so health checks can tell a
    stalled/crashing scheduler from a healthy one (see scheduler.get_scheduler_heartbeat).
    """
    __tablename__ = "scheduler_heartbeats"

    job_name = Column(String(64), primary_key=True)
    last_started_at = Column(DateTime(timezone=True), nullable=True)
    last_finished_at = Column(DateTime(timezone=True), nullable=True)
    last_error_count = Column(Integer, nullable=False, default=0)
    last_counts = Column(JSON, nullable=True)
    total_runs = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

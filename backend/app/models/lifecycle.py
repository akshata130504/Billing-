"""Customer lifecycle and account health tracking."""
from __future__ import annotations

import enum

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class CustomerLifecycleStage(str, enum.Enum):
    PROSPECT = "prospect"
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    RENEWAL_DUE = "renewal_due"
    EXPANSION = "expansion"
    AT_RISK = "at_risk"
    CHURNED = "churned"


class HealthStatus(str, enum.Enum):
    HEALTHY = "healthy"
    NEUTRAL = "neutral"
    AT_RISK = "at_risk"
    CRITICAL = "critical"


class CustomerLifecycle(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "customer_lifecycles"
    __table_args__ = (
        UniqueConstraint("organization_id", "customer_id", name="uq_lifecycle_customer_per_org"),
    )

    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    lifecycle_stage = Column(
        Enum(CustomerLifecycleStage, name="customer_lifecycle_stage"),
        nullable=False,
        default=CustomerLifecycleStage.ACTIVE,
        index=True,
    )
    stage_entered_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    health_status = Column(
        Enum(HealthStatus, name="health_status"),
        nullable=False,
        default=HealthStatus.HEALTHY,
        index=True,
    )
    health_score = Column(Integer, nullable=False, default=85)
    next_action = Column(String(255), nullable=True)
    next_action_due = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)

    customer = relationship("Customer")

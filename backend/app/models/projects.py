"""Project management model."""
from __future__ import annotations

import enum
from sqlalchemy import (
    Column,
    Date,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BillingMethod(str, enum.Enum):
    FIXED_PRICE = "fixed_price"
    TIME_AND_MATERIAL = "time_and_material"
    NON_BILLABLE = "non_billable"


class Project(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    name = Column(String(200), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(
        Enum(ProjectStatus, name="project_status"),
        nullable=False,
        default=ProjectStatus.ACTIVE,
        index=True,
    )
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    billing_method = Column(
        Enum(BillingMethod, name="project_billing_method"),
        nullable=False,
        default=BillingMethod.FIXED_PRICE,
        index=True,
    )
    budget = Column(Numeric(14, 2), nullable=False, default=0)
    project_manager = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)

    customer = relationship("Customer")
    time_entries = relationship("TimeEntry", foreign_keys="TimeEntry.project_id", primaryjoin="Project.id == foreign(TimeEntry.project_id)")

"""Time tracking and timesheet entries."""
from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TimeEntryStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    BILLED = "billed"


class TimeEntry(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "time_entries"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(String(64), nullable=True, index=True)
    project_name = Column(String(200), nullable=True)

    date = Column(Date, nullable=False, index=True)
    start_time = Column(String(10), nullable=True)
    end_time = Column(String(10), nullable=True)
    duration_hours = Column(Numeric(8, 2), nullable=False, default=0)
    description = Column(Text, nullable=False)

    billable = Column(Boolean, nullable=False, default=True, index=True)
    billing_rate = Column(Numeric(14, 2), nullable=False, default=0)
    billable_amount = Column(Numeric(14, 2), nullable=False, default=0)

    status = Column(
        Enum(TimeEntryStatus, name="time_entry_status"),
        nullable=False,
        default=TimeEntryStatus.DRAFT,
        index=True,
    )
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    rejection_reason = Column(Text, nullable=True)
    approved_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    approver = relationship("User", foreign_keys=[approved_by_id])
    customer = relationship("Customer")
    invoice = relationship("Invoice")

"""Expense tracking and recurring expense models."""
from __future__ import annotations

import enum
from sqlalchemy import (
    Boolean,
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


class ExpenseStatus(str, enum.Enum):
    DRAFT = "draft"
    RECORDED = "recorded"
    BILLABLE = "billable"
    INVOICED = "invoiced"
    REIMBURSED = "reimbursed"
    CANCELLED = "cancelled"


class RecurringExpenseFrequency(str, enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class RecurringExpenseStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class Expense(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "expenses"

    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    date = Column(Date, nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="INR")
    billable = Column(Boolean, nullable=False, default=False, index=True)

    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(200), nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    project_name = Column(String(200), nullable=True)

    billable_amount = Column(Numeric(14, 2), nullable=True)
    tax_rate = Column(Numeric(5, 2), nullable=True)
    invoice_treatment = Column(String(50), nullable=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)

    payment_method = Column(String(50), nullable=False, default="Cash")
    paid_by = Column(String(200), nullable=False, default="Self")
    status = Column(
        Enum(ExpenseStatus, name="expense_status"),
        nullable=False,
        default=ExpenseStatus.RECORDED,
        index=True,
    )

    receipt_file_name = Column(String(255), nullable=True)
    receipt_file_size = Column(String(50), nullable=True)
    receipt_file_type = Column(String(50), nullable=True)
    # Server-generated file name of the uploaded receipt in the private upload store
    # (never the client's file name; never served statically).
    receipt_storage_key = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    customer = relationship("Customer")
    project = relationship("Project")
    invoice = relationship("Invoice")


class RecurringExpense(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "recurring_expenses"

    name = Column(String(200), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    amount = Column(Numeric(14, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="INR")

    frequency = Column(
        Enum(RecurringExpenseFrequency, name="recurring_expense_frequency"),
        nullable=False,
        default=RecurringExpenseFrequency.MONTHLY,
        index=True,
    )
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    never_ends = Column(Boolean, nullable=False, default=True)
    next_run = Column(Date, nullable=True)
    last_run = Column(Date, nullable=True)

    billable = Column(Boolean, nullable=False, default=False)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(200), nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    project_name = Column(String(200), nullable=True)

    billable_amount = Column(Numeric(14, 2), nullable=True)
    invoice_treatment = Column(String(50), nullable=True)
    payment_method = Column(String(50), nullable=False, default="Cash")
    paid_by = Column(String(200), nullable=False, default="Self")

    status = Column(
        Enum(RecurringExpenseStatus, name="recurring_expense_status"),
        nullable=False,
        default=RecurringExpenseStatus.ACTIVE,
        index=True,
    )

    customer = relationship("Customer")
    project = relationship("Project")

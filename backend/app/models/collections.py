"""Collections: manual follow-up tracking layered on top of invoices/payments.

Nothing here duplicates invoice/payment math. `Invoice.amount_due`/`status`
stay the single source of truth for outstanding balances; these tables only
store the things invoices don't already track — manual status overrides
(disputed/escalated/...), contact/follow-up dates, activity notes, and
promise-to-pay commitments.
"""
import enum

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CollectionStatus(str, enum.Enum):
    CURRENT = "current"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    IN_FOLLOW_UP = "in_follow_up"
    PROMISE_TO_PAY = "promise_to_pay"
    DISPUTED = "disputed"
    ESCALATED = "escalated"
    COLLECTED = "collected"
    WRITTEN_OFF = "written_off"


# Statuses a user can explicitly set that "stick" until cleared or the invoice is paid,
# as opposed to current/due_soon/overdue/collected which are always derived automatically.
MANUAL_COLLECTION_STATUSES = (
    CollectionStatus.IN_FOLLOW_UP,
    CollectionStatus.PROMISE_TO_PAY,
    CollectionStatus.DISPUTED,
    CollectionStatus.ESCALATED,
    CollectionStatus.WRITTEN_OFF,
)


class CollectionActivityType(str, enum.Enum):
    EMAIL_SENT = "email_sent"
    PHONE_CALL = "phone_call"
    REMINDER = "reminder"
    PAYMENT_PROMISE = "payment_promise"
    CUSTOMER_CONTACTED = "customer_contacted"
    DISPUTE_RAISED = "dispute_raised"
    DISPUTE_RESOLVED = "dispute_resolved"
    INTERNAL_NOTE = "internal_note"


class PromiseToPayStatus(str, enum.Enum):
    PENDING = "pending"
    KEPT = "kept"
    BROKEN = "broken"
    CANCELLED = "cancelled"


class InvoiceCollection(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """One row per invoice that has ever had collections activity. Created on demand."""

    __tablename__ = "invoice_collections"
    __table_args__ = (UniqueConstraint("invoice_id", name="uq_invoice_collection_invoice"),)

    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    manual_status = Column(Enum(CollectionStatus, name="collection_manual_status"), nullable=True)
    last_contact_at = Column(DateTime(timezone=True), nullable=True)
    next_follow_up_at = Column(DateTime(timezone=True), nullable=True, index=True)

    invoice = relationship("Invoice")


class CollectionActivity(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "collection_activities"

    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type = Column(Enum(CollectionActivityType, name="collection_activity_type"), nullable=False)
    note = Column(Text, nullable=True)
    activity_at = Column(DateTime(timezone=True), nullable=False)
    next_follow_up_at = Column(DateTime(timezone=True), nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    invoice = relationship("Invoice")
    customer = relationship("Customer")
    created_by = relationship("User")


class PromiseToPay(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "promise_to_pay"

    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    promised_amount = Column(Numeric(14, 2), nullable=False)
    promised_date = Column(Date, nullable=False)
    note = Column(Text, nullable=True)
    status = Column(Enum(PromiseToPayStatus, name="promise_to_pay_status"), nullable=False, default=PromiseToPayStatus.PENDING)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    invoice = relationship("Invoice")
    customer = relationship("Customer")
    created_by = relationship("User")

"""Invoices and line items."""
import enum

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"  # issued / awaiting payment
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


OPEN_INVOICE_STATUSES = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE)


class Invoice(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("organization_id", "invoice_number", name="uq_invoice_number_per_org"),)

    invoice_number = Column(String(24), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    quote_id = Column(String(36), ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True)
    status = Column(Enum(InvoiceStatus, name="invoice_status"), nullable=False, default=InvoiceStatus.DRAFT, index=True)

    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    currency = Column(String(3), nullable=False, default="INR")

    subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    discount_pct = Column(Numeric(5, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(14, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    total = Column(Numeric(14, 2), nullable=False, default=0)
    amount_paid = Column(Numeric(14, 2), nullable=False, default=0)
    amount_due = Column(Numeric(14, 2), nullable=False, default=0)

    notes = Column(Text, nullable=True)
    terms = Column(Text, nullable=True)
    # Token for the hosted payment page (/pay/<token>) and PDF download without login.
    public_token = Column(String(64), nullable=False, unique=True, index=True)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    void_reason = Column(String(500), nullable=True)
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)
    reminder_count = Column(Integer, nullable=False, default=0)
    # Service period for subscription invoices.
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    customer = relationship("Customer")
    subscription = relationship("Subscription")
    items = relationship(
        "InvoiceItem", back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceItem.position"
    )
    allocations = relationship("PaymentAllocation", back_populates="invoice")


class InvoiceItem(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "invoice_items"

    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    plan_id = Column(String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False, default=1)
    unit_price = Column(Numeric(14, 2), nullable=False, default=0)
    tax_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    amount = Column(Numeric(14, 2), nullable=False, default=0)  # quantity * unit_price (pre-tax)
    position = Column(Integer, nullable=False, default=0)

    invoice = relationship("Invoice", back_populates="items")

"""Invoices and line items."""
import enum

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
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

# Must stay identical to PERIOD_INDEX_WHERE in alembic revision e6f7a8b9c0d1 (0019).
INVOICE_PERIOD_INDEX_WHERE = "status <> 'VOID' AND subscription_id IS NOT NULL AND period_start IS NOT NULL"


class Invoice(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_number", name="uq_invoice_number_per_org"),
        # Database-level backstop against double-invoicing a subscription period (migration 0019).
        # Enum columns store member NAMES, so a void invoice's status is 'VOID'.
        Index(
            "uq_invoices_subscription_period",
            "subscription_id",
            "period_start",
            unique=True,
            postgresql_where=text(INVOICE_PERIOD_INDEX_WHERE),
            sqlite_where=text(INVOICE_PERIOD_INDEX_WHERE),
        ),
    )

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
    # GST heads. cgst+sgst+igst always reconcile to tax_amount for Indian supplies;
    # all three are zero for exports, where tax_amount is zero too.
    cgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    sgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    igst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    # intra_state | inter_state | export — determines which heads are populated.
    supply_type = Column(String(16), nullable=True)
    # GST state code (first two digits of the recipient GSTIN) + its name, frozen
    # at issue time so a later change to the customer's address cannot alter an
    # already-issued tax invoice.
    place_of_supply_code = Column(String(2), nullable=True)
    place_of_supply_name = Column(String(120), nullable=True)
    customer_gstin = Column(String(15), nullable=True)
    supplier_gstin = Column(String(15), nullable=True)
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
    offering_id = Column(String(36), ForeignKey("offerings.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(String(36), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    plan_id = Column(String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False, default=1)
    unit_price = Column(Numeric(14, 2), nullable=False, default=0)
    tax_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    amount = Column(Numeric(14, 2), nullable=False, default=0)  # quantity * unit_price (pre-tax)
    # Per-line GST split; the line's share of the document totals.
    cgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    sgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    igst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    cgst_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    sgst_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    igst_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    # HSN/SAC copied from the product at issue time (required on a tax invoice).
    hsn_sac_code = Column(String(16), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    pricing_explanation = Column(Text, nullable=True)

    invoice = relationship("Invoice", back_populates="items")

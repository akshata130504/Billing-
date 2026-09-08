"""Quotes / proposals and their line items."""
import enum

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"  # discount above org threshold, awaiting admin
    APPROVED = "approved"
    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    PARTIALLY_INVOICED = "partially_invoiced"
    INVOICED = "invoiced"
    CONVERTED = "converted"  # an invoice was generated from it


class Quote(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("organization_id", "quote_number", name="uq_quote_number_per_org"),)

    quote_number = Column(String(24), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(Enum(QuoteStatus, name="quote_status"), nullable=False, default=QuoteStatus.DRAFT, index=True)
    issue_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=True)
    currency = Column(String(3), nullable=False, default="INR")

    subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    discount_pct = Column(Numeric(5, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(14, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    # GST heads, so a quote shows the same tax breakup the resulting invoice will.
    cgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    sgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    igst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    supply_type = Column(String(16), nullable=True)
    place_of_supply_code = Column(String(2), nullable=True)
    place_of_supply_name = Column(String(120), nullable=True)
    total = Column(Numeric(14, 2), nullable=False, default=0)

    title = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    terms = Column(Text, nullable=True)
    public_token = Column(String(64), nullable=True, unique=True, index=True)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    declined_at = Column(DateTime(timezone=True), nullable=True)
    converted_invoice_id = Column(String(36), nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    customer = relationship("Customer")
    items = relationship(
        "QuoteItem", back_populates="quote", cascade="all, delete-orphan", order_by="QuoteItem.position"
    )


class QuoteItem(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "quote_items"

    quote_id = Column(String(36), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True)
    offering_id = Column(String(36), ForeignKey("offerings.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(String(36), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    plan_id = Column(String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False, default=1)
    unit_price = Column(Numeric(14, 2), nullable=False, default=0)
    tax_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    amount = Column(Numeric(14, 2), nullable=False, default=0)  # quantity * unit_price (pre-tax)
    cgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    sgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    igst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    cgst_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    sgst_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    igst_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    hsn_sac_code = Column(String(16), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    pricing_explanation = Column(Text, nullable=True)

    quote = relationship("Quote", back_populates="items")

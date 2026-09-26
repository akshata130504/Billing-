"""Credit notes, line items, and credit applications to invoices."""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
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


class CreditNoteStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_APPLIED = "partially_applied"
    APPLIED = "applied"
    VOID = "void"


class CreditNote(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Credit notes issued to customers, which can be applied to reduce invoice balances."""
    __tablename__ = "credit_notes"
    __table_args__ = (
        UniqueConstraint("organization_id", "credit_note_number", name="uq_credit_note_number_per_org"),
    )

    credit_note_number = Column(String(24), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(Enum(CreditNoteStatus, name="credit_note_status"), nullable=False, default=CreditNoteStatus.DRAFT, index=True)
    reason = Column(String(500), nullable=True)
    issue_date = Column(Date, nullable=False, default=date.today)
    currency = Column(String(3), nullable=False, default="INR")

    subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    # GST heads, split like the invoice being credited (cgst+sgst+igst == tax_amount;
    # all zero for exports). Place of supply / GSTINs are frozen at issue time.
    cgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    sgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    igst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    supply_type = Column(String(16), nullable=True)
    place_of_supply_code = Column(String(2), nullable=True)
    place_of_supply_name = Column(String(120), nullable=True)
    customer_gstin = Column(String(15), nullable=True)
    supplier_gstin = Column(String(15), nullable=True)
    total = Column(Numeric(14, 2), nullable=False, default=0)
    balance_remaining = Column(Numeric(14, 2), nullable=False, default=0)

    notes = Column(Text, nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    void_reason = Column(String(500), nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    customer = relationship("Customer")
    invoice = relationship("Invoice")
    lines = relationship("CreditNoteLine", back_populates="credit_note", cascade="all, delete-orphan", order_by="CreditNoteLine.position")
    applications = relationship("CreditApplication", back_populates="credit_note", cascade="all, delete-orphan")


class CreditNoteLine(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "credit_note_lines"

    credit_note_id = Column(String(36), ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False, default=1)
    unit_price = Column(Numeric(14, 2), nullable=False, default=0)
    tax_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    amount = Column(Numeric(14, 2), nullable=False, default=0)
    cgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    sgst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    igst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    position = Column(Integer, nullable=False, default=0)

    credit_note = relationship("CreditNote", back_populates="lines")


class CreditApplication(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Application of a credit note amount toward an unpaid/partially paid invoice."""
    __tablename__ = "credit_applications"

    credit_note_id = Column(String(36), ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    applied_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    notes = Column(String(500), nullable=True)

    credit_note = relationship("CreditNote", back_populates="applications")
    invoice = relationship("Invoice")

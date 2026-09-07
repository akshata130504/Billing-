"""Payments, allocations to invoices, refunds and gateway webhook events."""
import enum

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class PaymentMethod(str, enum.Enum):
    RAZORPAY = "razorpay"  # online, collected through the hosted payment page
    BANK_TRANSFER = "bank_transfer"
    UPI = "upi"
    CARD = "card"
    CASH = "cash"
    CHEQUE = "cheque"
    OTHER = "other"


class PaymentGateway(str, enum.Enum):
    MANUAL = "manual"
    RAZORPAY = "razorpay"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"  # gateway order created, awaiting capture
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class ReconciliationStatus(str, enum.Enum):
    AUTO_MATCHED = "auto_matched"  # verified gateway payment tied to an invoice
    MATCHED = "matched"  # manually allocated by a user
    UNMATCHED = "unmatched"  # money received, no invoice allocated yet
    EXCEPTION = "exception"  # allocated amount differs from payment amount


class Payment(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("organization_id", "payment_number", name="uq_payment_number_per_org"),)

    payment_number = Column(String(24), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    method = Column(Enum(PaymentMethod, name="payment_method"), nullable=False, default=PaymentMethod.BANK_TRANSFER)
    gateway = Column(Enum(PaymentGateway, name="payment_gateway"), nullable=False, default=PaymentGateway.MANUAL)
    status = Column(Enum(PaymentStatus, name="payment_status"), nullable=False, default=PaymentStatus.SUCCEEDED, index=True)
    reconciliation_status = Column(
        Enum(ReconciliationStatus, name="reconciliation_status"),
        nullable=False,
        default=ReconciliationStatus.UNMATCHED,
        index=True,
    )

    # Gateway references (Razorpay order_xxx / pay_xxx).
    gateway_order_id = Column(String(64), nullable=True, index=True)
    gateway_payment_id = Column(String(64), nullable=True, unique=True, index=True)
    gateway_signature_verified = Column(Boolean, nullable=False, default=False)
    gateway_payload = Column(JSON, nullable=True)
    # Bank UTR / cheque number / any external reference for offline payments.
    reference = Column(String(120), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    amount_refunded = Column(Numeric(14, 2), nullable=False, default=0)
    recorded_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    customer = relationship("Customer")
    allocations = relationship("PaymentAllocation", back_populates="payment", cascade="all, delete-orphan")
    refunds = relationship("Refund", back_populates="payment", cascade="all, delete-orphan")


class PaymentAllocation(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "payment_allocations"

    payment_id = Column(String(36), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    payment = relationship("Payment", back_populates="allocations")
    invoice = relationship("Invoice", back_populates="allocations")


class RefundStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class Refund(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "refunds"

    payment_id = Column(String(36), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    status = Column(Enum(RefundStatus, name="refund_status"), nullable=False, default=RefundStatus.PROCESSED)
    gateway_refund_id = Column(String(64), nullable=True)
    reason = Column(String(500), nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    payment = relationship("Payment", back_populates="refunds")


class WebhookEvent(UUIDPrimaryKeyMixin, Base):
    """Inbound gateway webhooks, stored for idempotency and debugging."""

    __tablename__ = "webhook_events"

    provider = Column(String(32), nullable=False, default="razorpay")
    event_id = Column(String(128), nullable=False, unique=True, index=True)
    event_type = Column(String(120), nullable=False)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    payload = Column(JSON, nullable=False)
    signature_valid = Column(Boolean, nullable=False, default=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

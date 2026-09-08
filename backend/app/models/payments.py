"""Payments, allocations to invoices, refunds and gateway webhook events."""
import enum

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint

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



class CustomerPaymentMethodStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CustomerPaymentMethod(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Tokenized customer payment instrument (card, upi mandate, etc.) stored at the gateway."""
    __tablename__ = "customer_payment_methods"

    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    gateway = Column(Enum(PaymentGateway, name="customer_payment_method_gateway"), nullable=False, default=PaymentGateway.RAZORPAY)
    gateway_customer_id = Column(String(80), nullable=True, index=True)
    gateway_token = Column(String(120), nullable=False, index=True)
    type = Column(String(30), nullable=False, default="card")
    card_brand = Column(String(30), nullable=True)
    last4 = Column(String(4), nullable=True)
    exp_month = Column(Integer, nullable=True)
    exp_year = Column(Integer, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    is_autocharge_eligible = Column(Boolean, nullable=False, default=True)
    status = Column(Enum(CustomerPaymentMethodStatus, name="customer_payment_method_status"), nullable=False, default=CustomerPaymentMethodStatus.ACTIVE, index=True)

    customer = relationship("Customer")


class PaymentAttemptStatus(str, enum.Enum):
    CREATED = "created"
    SUBMITTED = "submitted"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PaymentAttempt(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Every discrete charge attempt on a gateway, supporting automated dunning and retries."""
    __tablename__ = "payment_attempts"

    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_id = Column(String(36), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_payment_method_id = Column(String(36), ForeignKey("customer_payment_methods.id", ondelete="SET NULL"), nullable=True, index=True)
    gateway = Column(Enum(PaymentGateway, name="payment_attempt_gateway"), nullable=False, default=PaymentGateway.RAZORPAY)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    status = Column(Enum(PaymentAttemptStatus, name="payment_attempt_status"), nullable=False, default=PaymentAttemptStatus.CREATED, index=True)
    attempt_number = Column(Integer, nullable=False, default=1)
    gateway_attempt_reference = Column(String(100), nullable=True, index=True)
    failure_reason = Column(String(500), nullable=True)
    failure_category = Column(String(50), nullable=True)
    payload = Column(JSON, nullable=True)

    invoice = relationship("Invoice")
    payment = relationship("Payment")
    customer = relationship("Customer")
    payment_method = relationship("CustomerPaymentMethod")

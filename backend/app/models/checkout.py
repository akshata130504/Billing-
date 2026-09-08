"""Hosted Payment Pages and Checkout Session models."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CheckoutTemplateType(str, enum.Enum):
    SINGLE_PAGE = "single_page"
    MULTI_PAGE = "multi_page"


class CheckoutSessionPurpose(str, enum.Enum):
    INVOICE_PAYMENT = "invoice_payment"
    NEW_SUBSCRIPTION = "new_subscription"
    UPDATE_SUBSCRIPTION = "update_subscription"
    UPDATE_CARD = "update_card"
    ONE_TIME_ADDON = "one_time_addon"
    ADD_PAYMENT_METHOD = "add_payment_method"


class CheckoutSessionStatus(str, enum.Enum):
    CREATED = "created"
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CheckoutTemplate(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Customizable branding and layout template for hosted payment and checkout pages."""
    __tablename__ = "checkout_templates"

    name = Column(String(100), nullable=False)
    template_type = Column(
        Enum(CheckoutTemplateType, name="checkout_template_type"),
        nullable=False,
        default=CheckoutTemplateType.SINGLE_PAGE,
    )
    primary_color = Column(String(20), nullable=False, default="#2563eb")
    accent_color = Column(String(20), nullable=False, default="#1e40af")
    logo_url = Column(String(500), nullable=True)
    button_text = Column(String(50), nullable=False, default="Pay Now")
    allow_quantity_edit = Column(Boolean, nullable=False, default=False)
    show_order_summary = Column(Boolean, nullable=False, default=True)
    redirect_url = Column(String(500), nullable=True)
    thank_you_message = Column(Text, nullable=True)
    error_message_template = Column(String(255), nullable=True)
    custom_fields = Column(JSON, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)


class CheckoutSession(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A time-limited, tokenized public checkout instance for paying invoices, subscribing, or updating payment methods."""
    __tablename__ = "checkout_sessions"

    template_id = Column(String(36), ForeignKey("checkout_templates.id", ondelete="SET NULL"), nullable=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    purpose = Column(
        Enum(CheckoutSessionPurpose, name="checkout_session_purpose"),
        nullable=False,
        default=CheckoutSessionPurpose.INVOICE_PAYMENT,
    )
    status = Column(
        Enum(CheckoutSessionStatus, name="checkout_session_status"),
        nullable=False,
        default=CheckoutSessionStatus.CREATED,
        index=True,
    )
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    plan_id = Column(String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    amount = Column(Numeric(14, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="INR")
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    payment_attempt_id = Column(String(36), ForeignKey("payment_attempts.id", ondelete="SET NULL"), nullable=True)
    payment_id = Column(String(36), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    save_payment_method = Column(Boolean, nullable=False, default=False)
    metadata_snapshot = Column(JSON, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    template = relationship("CheckoutTemplate")
    customer = relationship("Customer")
    invoice = relationship("Invoice")
    subscription = relationship("Subscription")
    plan = relationship("Plan")
    payment_attempt = relationship("PaymentAttempt")
    payment = relationship("Payment")

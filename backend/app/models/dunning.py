"""Dunning management models: policies, cases, retry attempts, and recovery tracking."""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class DunningFinalAction(str, enum.Enum):
    UNPAID = "unpaid"  # Keep subscription as unpaid, invoice remains overdue
    CANCEL_AND_VOID = "cancel_and_void"  # Cancel subscription and void invoice
    SUSPEND = "suspend"  # Suspend/pause subscription until paid


class DunningCaseStatus(str, enum.Enum):
    OPEN = "open"
    RETRY_SCHEDULED = "retry_scheduled"
    RETRYING = "retrying"
    RECOVERED = "recovered"
    PAUSED = "paused"
    STOPPED = "stopped"
    EXHAUSTED = "exhausted"
    FINALIZED = "finalized"


class DunningAttemptStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class DunningPolicy(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "dunning_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_dunning_policy_name_per_org"),
    )

    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)

    # Autocharge vs manual past-due
    applies_to_autocharge = Column(Boolean, nullable=False, default=True)
    min_amount = Column(Numeric(14, 2), nullable=True)  # For policy segmentation by invoice amount

    # Retries: up to 3 retries, total span <= 30 days per Zoho specification
    max_retries = Column(Integer, nullable=False, default=3)
    retry_intervals_days = Column(JSON, nullable=False, default=lambda: [3, 5, 7])
    total_span_days = Column(Integer, nullable=False, default=30)

    # Notifications
    notify_on_failure = Column(Boolean, nullable=False, default=True)
    notify_on_retry = Column(Boolean, nullable=False, default=True)
    notify_on_success = Column(Boolean, nullable=False, default=True)

    # Special rules
    first_ach_immediate_cancel = Column(Boolean, nullable=False, default=True)
    final_action: Mapped[DunningFinalAction] = mapped_column(
        Enum(DunningFinalAction, name="dunning_final_action"),
        nullable=False,
        default=DunningFinalAction.UNPAID,
    )
    non_autocharge_grace_days = Column(Integer, nullable=False, default=15)

    cases = relationship("DunningCase", back_populates="policy", cascade="all, delete-orphan")


class DunningCase(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "dunning_cases"
    __table_args__ = (
        UniqueConstraint("organization_id", "case_number", name="uq_dunning_case_number_per_org"),
    )

    case_number = Column(String(32), nullable=False, index=True)
    policy_id = Column(String(36), ForeignKey("dunning_policies.id", ondelete="RESTRICT"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(
        Enum(DunningCaseStatus, name="dunning_case_status"),
        nullable=False,
        default=DunningCaseStatus.OPEN,
        index=True,
    )
    trigger_reason = Column(String(200), nullable=False, default="payment_declined")
    amount_due = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")

    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Pause / stop metadata
    paused_at = Column(DateTime(timezone=True), nullable=True)
    pause_reason = Column(String(255), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    stop_reason = Column(String(255), nullable=True)

    # Recovery metadata
    recovered_at = Column(DateTime(timezone=True), nullable=True)
    recovered_by_payment_id = Column(String(36), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)

    # Finalization
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    final_action_taken = Column(String(50), nullable=True)
    metadata_snapshot = Column(JSON, nullable=True)

    # Relationships
    policy = relationship("DunningPolicy", back_populates="cases")
    customer = relationship("Customer")
    subscription = relationship("Subscription")
    invoice = relationship("Invoice")
    recovered_by_payment = relationship("Payment")
    attempts = relationship("DunningAttempt", back_populates="case", cascade="all, delete-orphan", order_by="DunningAttempt.attempt_number")
    communications = relationship("DunningCommunication", back_populates="case", cascade="all, delete-orphan")


class DunningAttempt(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "dunning_attempts"

    case_id = Column(String(36), ForeignKey("dunning_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        Enum(DunningAttemptStatus, name="dunning_attempt_status"),
        nullable=False,
        default=DunningAttemptStatus.SCHEDULED,
        index=True,
    )
    payment_attempt_id = Column(String(36), ForeignKey("payment_attempts.id", ondelete="SET NULL"), nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(String(500), nullable=True)
    notification_sent = Column(Boolean, nullable=False, default=False)

    case = relationship("DunningCase", back_populates="attempts")
    payment_attempt = relationship("PaymentAttempt")


class DunningCommunication(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "dunning_communications"

    case_id = Column(String(36), ForeignKey("dunning_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_email = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    template_type = Column(String(50), nullable=False)  # failure, retry, success, final_notice, card_expiry
    body_preview = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    case = relationship("DunningCase", back_populates="communications")

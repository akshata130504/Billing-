"""Domain event types, transactional outbox, inbox, and durable job models."""
from __future__ import annotations

import enum

from sqlalchemy import JSON, Column, DateTime, Enum, Integer, String, Text, UniqueConstraint

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class DomainEventType(str, enum.Enum):
    # Invoices
    INVOICE_ISSUED = "invoice.issued"
    INVOICE_PAID = "invoice.paid"
    INVOICE_PARTIALLY_PAID = "invoice.partially_paid"
    INVOICE_OVERDUE = "invoice.overdue"
    INVOICE_VOIDED = "invoice.voided"

    # Payments
    PAYMENT_CREATED = "payment.created"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"

    # Subscriptions & Trials
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_ACTIVATED = "subscription.activated"
    SUBSCRIPTION_PAUSED = "subscription.paused"
    SUBSCRIPTION_RESUMED = "subscription.resumed"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    SUBSCRIPTION_RENEWED = "subscription.renewed"
    SUBSCRIPTION_CHANGED = "subscription.changed"
    TRIAL_STARTED = "trial.started"
    TRIAL_EXTENDED = "trial.extended"
    TRIAL_EXPIRED = "trial.expired"
    TRIAL_CONVERTED = "trial.converted"

    # Credits
    CREDIT_NOTE_ISSUED = "credit_note.issued"
    CREDIT_NOTE_APPLIED = "credit_note.applied"
    CREDIT_NOTE_VOIDED = "credit_note.voided"

    # Usage
    USAGE_RECORDED = "usage.recorded"

    # Dunning
    DUNNING_STARTED = "dunning.started"
    DUNNING_STEP_EXECUTED = "dunning.step_executed"
    DUNNING_RECOVERED = "dunning.recovered"
    DUNNING_EXHAUSTED = "dunning.exhausted"

    # Notifications
    NOTIFICATION_SENT = "notification.sent"
    NOTIFICATION_FAILED = "notification.failed"


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"


class OutboxEvent(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Transactional Outbox: ensures events are saved in the same DB transaction as business mutations."""
    __tablename__ = "outbox_events"

    event_type = Column(String(80), nullable=False, index=True)
    aggregate_type = Column(String(80), nullable=False, index=True)
    aggregate_id = Column(String(36), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(Enum(OutboxStatus, name="outbox_status"), nullable=False, default=OutboxStatus.PENDING, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    # Retry scheduling: a failed event is re-queued as PENDING with next_attempt_at in the future.
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    # Lease start for PROCESSING rows; rows stuck past the lease are reclaimed by the processor.
    locked_at = Column(DateTime(timezone=True), nullable=True)


class InboxStatus(str, enum.Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    IGNORED = "ignored"


class InboxEvent(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Transactional Inbox: deduplicates and durably processes external inbound messages/webhooks."""
    __tablename__ = "inbox_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider", "event_id", name="uq_inbox_provider_event_id"),
    )

    provider = Column(String(40), nullable=False, index=True)
    event_id = Column(String(120), nullable=False, index=True)
    event_type = Column(String(80), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(Enum(InboxStatus, name="inbox_status"), nullable=False, default=InboxStatus.RECEIVED, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


class Job(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Durable Job Queue backed by PostgreSQL, with leasing and retry limits."""
    __tablename__ = "durable_jobs"

    job_type = Column(String(80), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(Enum(JobStatus, name="durable_job_status"), nullable=False, default=JobStatus.PENDING, index=True)
    run_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(String(80), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    last_error = Column(Text, nullable=True)


class IdempotencyRecord(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Records executed commands and cached responses to prevent duplicate operations."""
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_org_idempotency_key"),
    )

    idempotency_key = Column(String(128), nullable=False, index=True)
    request_path = Column(String(255), nullable=False)
    request_method = Column(String(10), nullable=False)
    params_hash = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, default="processing")  # processing | completed | failed
    status_code = Column(Integer, nullable=True)
    response_body = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

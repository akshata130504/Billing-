"""Approvals, the append-only audit log and data import jobs."""
import enum

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class ApprovalType(str, enum.Enum):
    QUOTE_DISCOUNT = "quote_discount"
    INVOICE_DISCOUNT = "invoice_discount"
    REFUND = "refund"
    INVOICE_VOID = "invoice_void"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRequest(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "approval_requests"

    type = Column(Enum(ApprovalType, name="approval_type"), nullable=False)
    status = Column(Enum(ApprovalStatus, name="approval_status"), nullable=False, default=ApprovalStatus.PENDING, index=True)
    entity_type = Column(String(40), nullable=False)  # "quote" | "invoice" | "payment"
    entity_id = Column(String(36), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    justification = Column(Text, nullable=True)
    # Structured context for the reviewer: amounts, discount %, customer name...
    payload = Column(JSON, nullable=True)
    requested_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(Text, nullable=True)

    requested_by = relationship("User", foreign_keys=[requested_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])


class AuditStatus(str, enum.Enum):
    SUCCESS = "success"
    WARNING = "warning"
    DENIED = "denied"


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only. Rows are never updated or deleted by application code."""

    __tablename__ = "audit_logs"

    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # Human readable actor: user's name, "System scheduler", "Razorpay webhook", "Customer (pay page)".
    actor_label = Column(String(200), nullable=False)
    action = Column(String(80), nullable=False, index=True)  # e.g. INVOICE_SENT
    entity_type = Column(String(40), nullable=False, index=True)  # invoice, payment, customer, user, ...
    entity_id = Column(String(36), nullable=True, index=True)
    entity_label = Column(String(200), nullable=True)  # INV-000123, customer name...
    status = Column(Enum(AuditStatus, name="audit_status"), nullable=False, default=AuditStatus.SUCCESS)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    actor = relationship("User", foreign_keys=[actor_user_id])


class ImportEntity(str, enum.Enum):
    CUSTOMERS = "customers"
    PRODUCTS = "products"
    PLANS = "plans"


class ImportStatus(str, enum.Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class ImportJob(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "import_jobs"

    entity = Column(Enum(ImportEntity, name="import_entity"), nullable=False)
    file_name = Column(String(255), nullable=False)
    status = Column(Enum(ImportStatus, name="import_status"), nullable=False)
    total_rows = Column(Integer, nullable=False, default=0)
    imported_rows = Column(Integer, nullable=False, default=0)
    failed_rows = Column(Integer, nullable=False, default=0)
    # [{"row": 3, "error": "email is invalid"}, ...] capped to the first 100 problems.
    errors = Column(JSON, nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

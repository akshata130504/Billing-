"""Automation: simple event-driven rules (WHEN/IF/THEN) over real billing events."""
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AutomationTrigger(str, enum.Enum):
    INVOICE_OVERDUE = "invoice_overdue"
    INVOICE_DUE_SOON = "invoice_due_soon"
    QUOTE_EXPIRING = "quote_expiring"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_FAILED = "payment_failed"
    CUSTOMER_CREATED = "customer_created"
    QUOTE_ACCEPTED = "quote_accepted"
    INVOICE_CREATED = "invoice_created"


class AutomationExecutionStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"


class AutomationRule(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "automation_rules"

    name = Column(String(200), nullable=False)
    trigger = Column(Enum(AutomationTrigger, name="automation_trigger"), nullable=False, index=True)
    # List[{field, op, value}] — all must match (AND) for the rule to fire.
    conditions = Column(JSON, nullable=False, default=list)
    # List[{action, params}] — action in create_activity/create_reminder/send_email/
    # update_collection_status/create_approval_task.
    actions = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_by = relationship("User")
    executions = relationship("AutomationExecution", back_populates="rule", cascade="all, delete-orphan")


class AutomationExecution(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "automation_executions"

    rule_id = Column(String(36), ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger = Column(Enum(AutomationTrigger, name="automation_execution_trigger"), nullable=False)
    triggered_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(Enum(AutomationExecutionStatus, name="automation_execution_status"), nullable=False)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    rule = relationship("AutomationRule", back_populates="executions")

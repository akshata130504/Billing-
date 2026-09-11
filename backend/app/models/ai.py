"""Models for AI in Billing: conversations, requests, source references, tool invocations, and action drafts.

Per the architecture plan, AI never mutates billing tables directly — it only proposes structured
drafts that are re-validated and executed through existing domain services (e.g. credit_service).
"""
import enum

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AIRequestMode(str, enum.Enum):
    QUERY = "query"
    DRAFT = "draft"
    WRITING = "writing"


class AIRequestStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AIActionType(str, enum.Enum):
    CREDIT_NOTE = "credit_note"


class AIActionDraftStatus(str, enum.Enum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    APPROVED = "approved"
    EXECUTED = "executed"
    REJECTED = "rejected"
    EXPIRED = "expired"


def _enum_values(enum_cls):
    return [e.value for e in enum_cls]


class AIConversation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "ai_conversations"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=True)

    requests = relationship("AIRequest", back_populates="conversation", cascade="all, delete-orphan")


class AIRequest(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "ai_requests"

    conversation_id = Column(String(36), ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mode = Column(Enum(AIRequestMode, name="ai_request_mode", values_callable=_enum_values), nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    model_provider = Column(String(50), nullable=False, default="rooman-local")
    model_name = Column(String(50), nullable=False, default="deterministic-v1")
    status = Column(
        Enum(AIRequestStatus, name="ai_request_status", values_callable=_enum_values),
        nullable=False,
        default=AIRequestStatus.QUEUED,
        index=True,
    )
    answer = Column(Text, nullable=True)
    result_data = Column(JSON, nullable=True)
    error_message = Column(String(500), nullable=True)

    conversation = relationship("AIConversation", back_populates="requests")
    sources = relationship("AISourceReference", back_populates="request", cascade="all, delete-orphan")
    tool_invocations = relationship("AIToolInvocation", back_populates="request", cascade="all, delete-orphan")
    drafts = relationship("AIActionDraft", back_populates="request", cascade="all, delete-orphan")


class AISourceReference(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "ai_source_references"

    request_id = Column(String(36), ForeignKey("ai_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(50), nullable=False)
    source_id = Column(String(36), nullable=True)
    label = Column(String(200), nullable=False)
    snippet = Column(Text, nullable=True)

    request = relationship("AIRequest", back_populates="sources")


class AIToolInvocation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "ai_tool_invocations"

    request_id = Column(String(36), ForeignKey("ai_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False)
    arguments = Column(JSON, nullable=False, default=lambda: {})
    result_summary = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="success")

    request = relationship("AIRequest", back_populates="tool_invocations")


class AIActionDraft(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "ai_action_drafts"

    request_id = Column(String(36), ForeignKey("ai_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(Enum(AIActionType, name="ai_action_type", values_callable=_enum_values), nullable=False, index=True)
    proposed_payload = Column(JSON, nullable=False)
    status = Column(
        Enum(AIActionDraftStatus, name="ai_action_draft_status", values_callable=_enum_values),
        nullable=False,
        default=AIActionDraftStatus.PROPOSED,
        index=True,
    )
    validation_errors = Column(JSON, nullable=True)
    executed_entity_type = Column(String(50), nullable=True)
    executed_entity_id = Column(String(36), nullable=True)
    confirmed_by_id = Column(String(36), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    request = relationship("AIRequest", back_populates="drafts")

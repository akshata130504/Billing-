"""Pydantic schemas for AI in Billing: queries, drafts, writing assistance, and history."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.ai import AIActionDraftStatus, AIActionType, AIRequestMode, AIRequestStatus


class AISourceReferenceOut(BaseModel):
    source_type: str
    source_id: Optional[str] = None
    label: str
    snippet: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Queries (Ask-Zia-equivalent)
# ---------------------------------------------------------------------------

class AIQueryRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None


class AIQueryResponse(BaseModel):
    request_id: str
    conversation_id: str
    answer: str
    sources: List[AISourceReferenceOut] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Drafts (CoCreate-equivalent: propose -> validate -> confirm -> execute)
# ---------------------------------------------------------------------------

class AIActionDraftLineIn(BaseModel):
    description: str = Field(..., max_length=255)
    quantity: float = Field(default=1, gt=0)
    unit_price: float = Field(..., ge=0)
    tax_rate_pct: float = Field(default=0, ge=0, le=100)


class AIDraftRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    action_type: AIActionType
    customer_id: str
    invoice_id: Optional[str] = None
    reason: Optional[str] = Field(None, max_length=255)
    lines: List[AIActionDraftLineIn] = Field(..., min_length=1)
    conversation_id: Optional[str] = None


class AIActionDraftOut(BaseModel):
    id: str
    request_id: str
    action_type: AIActionType
    proposed_payload: Dict[str, Any]
    status: AIActionDraftStatus
    validation_errors: Optional[Dict[str, Any]] = None
    executed_entity_type: Optional[str] = None
    executed_entity_id: Optional[str] = None
    expires_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIDraftResponse(BaseModel):
    draft: AIActionDraftOut
    preview: Dict[str, Any]


class AIDraftConfirmResponse(BaseModel):
    draft: AIActionDraftOut
    executed_result: Dict[str, Any]


# ---------------------------------------------------------------------------
# Writing Assistant
# ---------------------------------------------------------------------------

class AIWritingRequest(BaseModel):
    purpose: str = Field(default="custom", max_length=50, description="e.g. 'payment_reminder' or 'custom'")
    tone: str = Field(default="neutral", max_length=20, description="friendly | firm | neutral")
    context: Dict[str, Any] = Field(default_factory=dict)
    instructions: Optional[str] = Field(None, max_length=1000)


class AIWritingResponse(BaseModel):
    request_id: str
    subject: Optional[str] = None
    body: str


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class AIHistoryOut(BaseModel):
    id: str
    conversation_id: str
    mode: AIRequestMode
    prompt: str
    status: AIRequestStatus
    answer: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

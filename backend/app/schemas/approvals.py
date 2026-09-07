"""Approval request schemas (contract section 10)."""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.common_refs import UserRef


class ApprovalDecisionIn(BaseModel):
    note: Optional[str] = Field(None, max_length=2000)


class ApprovalRejectIn(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)


class ApprovalOut(BaseModel):
    id: str
    type: str
    status: str
    entity_type: str
    entity_id: str
    entity_label: str
    title: str
    justification: Optional[str] = None
    payload: Dict[str, Any]
    requested_by: Optional[UserRef] = None
    reviewed_by: Optional[UserRef] = None
    reviewed_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: datetime

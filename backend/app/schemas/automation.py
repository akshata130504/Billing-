"""Request/response schemas for /automation."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.models import AutomationExecutionStatus, AutomationTrigger
from backend.app.schemas.common_refs import UserRef


class AutomationRuleIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    trigger: AutomationTrigger
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(..., min_length=1)


class AutomationRuleActiveIn(BaseModel):
    is_active: bool


class AutomationRuleOut(BaseModel):
    id: str
    name: str
    trigger: AutomationTrigger
    conditions: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    is_active: bool
    created_by: Optional[UserRef] = None
    created_at: datetime
    updated_at: datetime


class AutomationExecutionOut(BaseModel):
    id: str
    rule_id: str
    trigger: AutomationTrigger
    triggered_at: datetime
    status: AutomationExecutionStatus
    result: Optional[Any] = None
    error: Optional[str] = None


class AutomationDashboardOut(BaseModel):
    active_rules: int
    paused_rules: int
    failed_executions: int
    total_executions: int
    success_rate: Optional[float] = None

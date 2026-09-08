"""Pydantic schemas for dunning policies, cases, retries, and recovery metrics."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.dunning import DunningAttemptStatus, DunningCaseStatus, DunningFinalAction


class DunningPolicyBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    is_default: bool = False
    is_active: bool = True
    applies_to_autocharge: bool = True
    min_amount: Optional[Decimal] = None
    max_retries: int = Field(default=3, ge=1, le=3)
    retry_intervals_days: List[int] = Field(default_factory=lambda: [3, 5, 7])
    total_span_days: int = Field(default=30, le=30)
    notify_on_failure: bool = True
    notify_on_retry: bool = True
    notify_on_success: bool = True
    first_ach_immediate_cancel: bool = True
    final_action: DunningFinalAction = DunningFinalAction.UNPAID
    non_autocharge_grace_days: int = Field(default=15, ge=1, le=60)


class DunningPolicyCreate(DunningPolicyBase):
    pass


class DunningPolicyUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    applies_to_autocharge: Optional[bool] = None
    min_amount: Optional[Decimal] = None
    max_retries: Optional[int] = Field(None, ge=1, le=3)
    retry_intervals_days: Optional[List[int]] = None
    total_span_days: Optional[int] = Field(None, le=30)
    notify_on_failure: Optional[bool] = None
    notify_on_retry: Optional[bool] = None
    notify_on_success: Optional[bool] = None
    first_ach_immediate_cancel: Optional[bool] = None
    final_action: Optional[DunningFinalAction] = None
    non_autocharge_grace_days: Optional[int] = Field(None, ge=1, le=60)


class DunningPolicyOut(DunningPolicyBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DunningAttemptOut(BaseModel):
    id: str
    attempt_number: int
    scheduled_at: datetime
    executed_at: Optional[datetime] = None
    status: DunningAttemptStatus
    payment_attempt_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    notification_sent: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DunningCommunicationOut(BaseModel):
    id: str
    recipient_email: str
    subject: str
    template_type: str
    body_preview: Optional[str] = None
    sent_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DunningCaseOut(BaseModel):
    id: str
    case_number: str
    policy_id: str
    customer_id: str
    subscription_id: Optional[str] = None
    invoice_id: str
    status: DunningCaseStatus
    trigger_reason: str
    amount_due: Decimal
    currency: str
    attempt_count: int
    max_attempts: int
    next_retry_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    pause_reason: Optional[str] = None
    stopped_at: Optional[datetime] = None
    stop_reason: Optional[str] = None
    recovered_at: Optional[datetime] = None
    recovered_by_payment_id: Optional[str] = None
    finalized_at: Optional[datetime] = None
    final_action_taken: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DunningCaseDetailOut(DunningCaseOut):
    policy: Optional[DunningPolicyOut] = None
    customer_name: Optional[str] = None
    invoice_number: Optional[str] = None
    attempts: List[DunningAttemptOut] = []
    communications: List[DunningCommunicationOut] = []


class DunningCasePauseIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=255)


class DunningCaseStopIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=255)
    apply_final_action: bool = True


class DunningMetricsOut(BaseModel):
    total_cases: int
    active_cases: int
    recovered_cases: int
    exhausted_cases: int
    paused_cases: int
    stopped_cases: int
    recovery_rate_pct: float
    total_amount_at_risk: Decimal
    total_amount_recovered: Decimal
    currency: str = "INR"


class ExpiringCardNoticeOut(BaseModel):
    payment_method_id: str
    customer_id: str
    customer_email: str
    card_last4: str
    card_brand: Optional[str] = None
    expiry_month: int
    expiry_year: int
    days_until_expiry: int
    notification_sent: bool

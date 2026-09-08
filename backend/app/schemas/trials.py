"""Pydantic schemas for trial management, extensions, conversion, and reports."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TrialPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    subscription_id: str
    trial_start_date: date
    trial_end_date: date
    extension_count: int
    max_extensions_allowed: int
    allow_customer_extension: bool
    allow_early_conversion: bool
    auto_charge_enabled: bool
    fallback_plan_id: Optional[str] = None
    status: str
    converted_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TrialExtensionIn(BaseModel):
    days: Optional[int] = Field(None, ge=1, le=365, description="Number of additional days to extend trial")
    new_expiration_date: Optional[date] = Field(None, description="Exact new trial expiration date")
    reason: Optional[str] = Field(None, max_length=255, description="Reason for the trial extension")
    admin_override: bool = Field(False, description="Admin override allowing extension beyond maximum allowed cap")


class TrialExtensionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    trial_period_id: str
    subscription_id: str
    previous_trial_end: date
    new_trial_end: date
    extended_days: int
    reason: Optional[str] = None
    is_customer_initiated: bool
    extended_by_id: Optional[str] = None
    created_at: datetime


class TrialConversionAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    trial_period_id: str
    subscription_id: str
    attempt_type: str
    status: str
    payment_method_id: Optional[str] = None
    payment_attempt_id: Optional[str] = None
    invoice_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime


class TrialConvertIn(BaseModel):
    payment_method_id: Optional[str] = Field(None, description="Optional vaulted customer payment method to charge")
    generate_first_invoice: bool = Field(True, description="Whether to immediately generate first period invoice")


class TrialConversionResultOut(BaseModel):
    subscription_id: str
    status: str
    converted_at: datetime
    invoice_id: Optional[str] = None
    payment_attempt_id: Optional[str] = None
    payment_succeeded: bool = False
    message: str


class TrialFallbackIn(BaseModel):
    fallback_plan_id: Optional[str] = Field(None, description="Optional target free/fallback plan ID")


class TrialDetailOut(BaseModel):
    trial_period: TrialPeriodOut
    subscription_number: str
    customer_id: str
    customer_name: Optional[str] = None
    plan_id: str
    plan_name: Optional[str] = None
    extensions: List[TrialExtensionOut] = Field(default_factory=list)
    conversion_attempts: List[TrialConversionAttemptOut] = Field(default_factory=list)


class TrialReportPlanStat(BaseModel):
    plan_id: str
    plan_name: str
    total_trials: int
    active_trials: int
    converted_trials: int
    expired_trials: int
    conversion_rate_pct: float


class TrialReportsOut(BaseModel):
    active_trials_count: int
    expiring_in_7_days_count: int
    inactive_trials_count: int
    converted_trials_count: int
    total_trials_count: int
    overall_conversion_rate_pct: float
    average_sales_cycle_days: float
    by_plan: List[TrialReportPlanStat] = Field(default_factory=list)

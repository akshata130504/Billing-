"""Request/response schemas for /subscriptions (contract §7)."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models import BillingInterval, SubscriptionStatus
from backend.app.schemas.common_refs import CustomerRef


class SubscriptionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str
    plan_id: str
    quantity: int = Field(default=1, ge=1)
    start_date: Optional[date] = None
    # None = use the plan's trial_days; 0 = no trial.
    trial_days: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None
    # Default: True when the subscription does not start with a trial.
    generate_first_invoice: Optional[bool] = None


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    quantity: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None
    cancel_at_period_end: Optional[bool] = None


class SubscriptionCancelIn(BaseModel):
    at_period_end: bool = False
    reason: Optional[str] = Field(default=None, max_length=500)


class SubscriptionPlanRef(BaseModel):
    id: str
    name: str
    code: str
    billing_interval: BillingInterval
    interval_count: int
    unit_amount: str
    currency: str
    product_name: str


class SubscriptionOut(BaseModel):
    id: str
    subscription_number: str
    customer: CustomerRef
    plan: SubscriptionPlanRef
    quantity: int
    status: SubscriptionStatus
    start_date: date
    trial_end: Optional[date] = None
    current_period_start: date
    current_period_end: date
    next_billing_date: Optional[date] = None
    cancel_at_period_end: bool
    cancelled_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None
    mrr: str
    created_at: datetime
    updated_at: datetime

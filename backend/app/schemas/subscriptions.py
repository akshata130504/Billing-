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
    billing_frequency: Optional[str] = Field(default=None, max_length=32)
    # None = use the plan's trial_days; 0 = no trial.
    trial_days: Optional[int] = Field(default=None, ge=0)
    auto_renewal: bool = True
    notes: Optional[str] = None
    status: Optional[SubscriptionStatus] = None
    # Default: True when the subscription does not start with a trial.
    generate_first_invoice: Optional[bool] = None


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    quantity: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None
    auto_renewal: Optional[bool] = None
    cancel_at_period_end: Optional[bool] = None
    billing_frequency: Optional[str] = None


class SubscriptionCancelIn(BaseModel):
    at_period_end: bool = False
    # Immediate cancellation only: issue a credit note for the unused, already-invoiced
    # remainder of the current period.
    prorate_credit: bool = False
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
    pricing_model: Optional[str] = "flat"


class SubscriptionOut(BaseModel):
    id: str
    subscription_number: str
    customer: CustomerRef
    plan: SubscriptionPlanRef
    quantity: int
    status: SubscriptionStatus
    billing_frequency: str
    currency: str
    pricing_model: str
    unit_price: str
    subtotal: str
    discount_amount: str
    tax_amount: str
    total_amount: str
    start_date: date
    trial_start: Optional[date] = None
    trial_end: Optional[date] = None
    current_period_start: date
    current_period_end: date
    next_billing_date: Optional[date] = None
    auto_renewal: bool
    cancel_at_period_end: bool
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    paused_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None
    mrr: str
    created_at: datetime
    updated_at: datetime


class SubscriptionSummaryOut(BaseModel):
    total_subscriptions: int
    active_count: int
    trialing_count: int
    paused_count: int
    renewing_soon_count: int
    cancelled_count: int
    draft_count: int = 0
    total_mrr: str

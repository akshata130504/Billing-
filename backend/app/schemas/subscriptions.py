"""Request/response schemas for /subscriptions (contract §7)."""
from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.models import BillingInterval, SubscriptionStatus
from backend.app.schemas.common_refs import CustomerRef


class SubscriptionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str
    # Exactly one of: a legacy plan, or a recurring Plans & Pricing (catalog) offering.
    plan_id: Optional[str] = None
    offering_id: Optional[str] = None
    # Offering subscriptions only: price with this price book (default: the org's
    # default active price book, when it has an entry for the offering).
    price_book_id: Optional[str] = None
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

    @model_validator(mode="after")
    def _one_plan_source(self):
        if bool(self.plan_id) == bool(self.offering_id):
            raise ValueError("Provide exactly one of plan_id (legacy plan) or offering_id (Plans & Pricing plan).")
        if self.price_book_id and not self.offering_id:
            raise ValueError("price_book_id applies to offering_id subscriptions only.")
        return self


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
    # "plan" (legacy plan) or "offering" (Plans & Pricing plan billed via a linked plan).
    source: str = "plan"
    offering_id: Optional[str] = None
    offering_pricing_model: Optional[str] = None


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


class SubscribablePlanOption(BaseModel):
    """One entry of GET /subscriptions/plan-options: a legacy plan or a recurring offering."""

    id: str
    source: str  # "plan" | "offering"
    plan_id: Optional[str] = None
    offering_id: Optional[str] = None
    name: str
    code: str
    product_name: str = ""
    billing_interval: Optional[str] = None
    interval_count: int = 1
    pricing_model: str
    unit_amount: str
    currency: str
    tax_rate_pct: str
    trial_days: int = 0
    pricing_tiers: List[Any] = Field(default_factory=list)
    is_active: bool = True


class SubscriptionSummaryOut(BaseModel):
    total_subscriptions: int
    active_count: int
    trialing_count: int
    paused_count: int
    renewing_soon_count: int
    cancelled_count: int
    draft_count: int = 0
    total_mrr: str

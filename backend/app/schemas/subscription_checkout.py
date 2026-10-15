"""Rooman plan checkout API models. Only a plan CODE comes from the browser; everything else is the
backend's (catalog). The response carries the PUBLIC Razorpay key id, never a secret."""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.organization import UTCDateTime


class CheckoutStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # prices, modules, seats or intervals are never accepted

    plan_code: str = Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_]{1,31}$")


class CheckoutPlanOut(BaseModel):
    code: str
    name: str
    description: str
    amount_minor: int
    currency: str
    interval: str
    interval_count: int
    tax_treatment: Optional[str] = None
    seat_limit: int
    sandbox: bool = False  # a Test Mode sandbox test plan, not a commercial offer


class CheckoutPrefillOut(BaseModel):
    name: str
    email: str


class CheckoutStartOut(BaseModel):
    checkout_attempt_id: str
    razorpay_key_id: str
    razorpay_subscription_id: str
    expires_at: UTCDateTime
    reused: bool  # true when an open checkout for the same plan was returned instead of a new one
    plan: CheckoutPlanOut
    prefill: CheckoutPrefillOut
    organization_name: str


class CheckoutVerifyIn(BaseModel):
    """Exactly the three fields Razorpay Checkout returns. Nothing else is accepted."""

    model_config = ConfigDict(extra="forbid")

    razorpay_payment_id: str = Field(min_length=5, max_length=64, pattern=r"^pay_[A-Za-z0-9]+$")
    razorpay_subscription_id: str = Field(min_length=5, max_length=64, pattern=r"^sub_[A-Za-z0-9]+$")
    razorpay_signature: str = Field(min_length=64, max_length=128, pattern=r"^[A-Fa-f0-9]+$")


class CheckoutVerifyOut(BaseModel):
    status: str = Field(description="active | pending | not_paid - pending is NOT a paid subscription")
    message: str
    plan_code: str

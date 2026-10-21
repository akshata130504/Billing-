"""UPI AutoPay / e-mandate (Razorpay Subscriptions) request and response bodies."""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AutopayMandateOut(BaseModel):
    id: str
    subscription_id: str
    status: str
    gateway_subscription_id: str
    amount: str
    currency: str
    period: str
    interval: int
    total_count: int
    paid_count: int
    start_at: Optional[str] = None
    charge_at: Optional[str] = None
    authorized_at: Optional[str] = None
    ended_at: Optional[str] = None
    last_error: Optional[str] = None
    # Only in the response that (re)issued it: the customer's one-time authorisation page.
    authorization_link: Optional[str] = None


class AutopayStatusOut(BaseModel):
    eligible: bool
    reason: Optional[str] = None
    mandate: Optional[AutopayMandateOut] = None


class PublicAutopayPrefill(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    contact: Optional[str] = None


class PublicAutopayOut(BaseModel):
    status: str
    can_authorize: bool
    organization_name: str
    plan_name: str
    subscription_number: str
    amount: str
    currency: str
    period: str
    interval: int
    total_count: int
    start_at: Optional[str] = None
    authorized_at: Optional[str] = None
    gateway_subscription_id: Optional[str] = None
    key_id: Optional[str] = None
    prefill: PublicAutopayPrefill


class PublicAutopayConfirmIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    razorpay_payment_id: str = Field(..., min_length=1, max_length=64)
    razorpay_subscription_id: str = Field(..., min_length=1, max_length=64)
    razorpay_signature: str = Field(..., min_length=1, max_length=256)

"""Schemas for customer vaulted payment methods and payment attempts."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.payments import (
    CustomerPaymentMethodStatus,
    PaymentAttemptStatus,
    PaymentGateway,
)


class CustomerPaymentMethodCreateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    gateway: PaymentGateway = PaymentGateway.RAZORPAY
    gateway_token: str = Field(..., min_length=1, max_length=120)
    gateway_customer_id: Optional[str] = Field(default=None, max_length=80)
    type: str = Field(default="card", max_length=30)
    card_brand: Optional[str] = Field(default=None, max_length=30)
    last4: Optional[str] = Field(default=None, max_length=4)
    exp_month: Optional[int] = Field(default=None, ge=1, le=12)
    exp_year: Optional[int] = Field(default=None, ge=2024, le=2100)
    is_default: bool = False
    is_autocharge_eligible: bool = True


class CustomerPaymentMethodOut(BaseModel):
    id: str
    customer_id: str
    gateway: PaymentGateway
    gateway_customer_id: Optional[str] = None
    type: str
    card_brand: Optional[str] = None
    last4: Optional[str] = None
    exp_month: Optional[int] = None
    exp_year: Optional[int] = None
    is_default: bool
    is_autocharge_eligible: bool
    status: CustomerPaymentMethodStatus
    created_at: datetime


class PaymentAttemptOut(BaseModel):
    id: str
    invoice_id: str
    customer_id: str
    customer_payment_method_id: Optional[str] = None
    payment_id: Optional[str] = None
    gateway: PaymentGateway
    amount: str
    currency: str
    status: PaymentAttemptStatus
    attempt_number: int
    gateway_attempt_reference: Optional[str] = None
    failure_reason: Optional[str] = None
    failure_category: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    created_at: datetime

"""Request/response schemas for /payments (contract §9)."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models import PaymentGateway, PaymentMethod, PaymentStatus, ReconciliationStatus, RefundStatus
from backend.app.schemas.common_refs import CustomerRef, UserRef
from backend.app.schemas.validators import reject_future_datetime


class AllocationIn(BaseModel):
    invoice_id: str
    amount: Decimal = Field(..., gt=0)


class PaymentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str
    amount: Decimal = Field(..., gt=0)
    method: PaymentMethod
    paid_at: Optional[datetime] = None
    reference: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None
    allocations: Optional[List[AllocationIn]] = None

    @field_validator("method")
    @classmethod
    def _offline_only(cls, v: PaymentMethod) -> PaymentMethod:
        if v == PaymentMethod.RAZORPAY:
            raise ValueError("Online (razorpay) payments are captured through the hosted page, not recorded manually.")
        return v

    @field_validator("paid_at")
    @classmethod
    def _paid_at(cls, v):
        return reject_future_datetime(v, "Payment date")


class PaymentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reference: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None


class AllocationsPut(BaseModel):
    allocations: List[AllocationIn]


class RefundIn(BaseModel):
    amount: Decimal = Field(..., gt=0)
    reason: Optional[str] = Field(default=None, max_length=500)


class AllocationOut(BaseModel):
    id: str
    invoice_id: str
    invoice_number: str
    amount: str


class RefundOut(BaseModel):
    id: str
    amount: str
    status: RefundStatus
    gateway_refund_id: Optional[str] = None
    reason: Optional[str] = None
    created_at: datetime


class PaymentOut(BaseModel):
    id: str
    payment_number: str
    customer: Optional[CustomerRef] = None
    amount: str
    currency: str
    method: PaymentMethod
    gateway: PaymentGateway
    status: PaymentStatus
    reconciliation_status: ReconciliationStatus
    gateway_order_id: Optional[str] = None
    gateway_payment_id: Optional[str] = None
    gateway_signature_verified: bool
    reference: Optional[str] = None
    paid_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    notes: Optional[str] = None
    amount_refunded: str
    amount_allocated: str
    amount_unallocated: str
    allocations: List[AllocationOut] = []
    refunds: List[RefundOut] = []
    recorded_by: Optional[UserRef] = None
    created_at: datetime
    updated_at: datetime


class PaymentCurrencyTotals(BaseModel):
    currency: str
    count: int
    total_collected: str
    pending_amount: str
    total_refunded: str
    unallocated_amount: str


class PaymentsSummary(BaseModel):
    """Money totals across every payment matching the current filters.

    `count` covers every currency; the money fields are in `currency` (the organization's
    base currency) only and `by_currency` has them for every currency (never summed)."""

    count: int
    currency: str = "INR"
    total_collected: str
    pending_amount: str
    total_refunded: str
    unallocated_amount: str
    by_currency: List[PaymentCurrencyTotals] = []


class CurrencyAmount(BaseModel):
    currency: str
    amount: str


class ReconciliationSummary(BaseModel):
    auto_matched: int
    matched: int
    unmatched: int
    exception: int
    total: int
    currency: str = "INR"
    unallocated_amount: str
    unallocated_by_currency: List[CurrencyAmount] = []

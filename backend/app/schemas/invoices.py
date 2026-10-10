"""Request/response schemas for /invoices (contract §8)."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models import InvoiceStatus, PaymentMethod, PaymentStatus
from backend.app.schemas.common_refs import CustomerRef, LineItemIn, LineItemOut, UserRef
from backend.app.schemas.validators import reject_future_datetime

# Technical ceiling only (abuse/overflow prevention) — the business rules define no cap.
_MAX_TEXT_LENGTH = 10000


def _upper_currency(value: Optional[str]) -> Optional[str]:
    return value.upper() if value else value


class InvoiceLineItemIn(LineItemIn):
    """An invoice line as posted by the client. ``id`` is the stored id of an existing line of THIS
    invoice that the client is keeping (it lets the server tell a retained line from a removed and
    re-added one); omit it on new lines. Invoice-specific so the shared LineItemIn contract used by
    quotes and CPQ is unchanged."""

    id: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def _empty_id_to_none(cls, value):
        return None if value == "" else value


def _accept_shared_line_items(value):
    """Python callers may still pass plain LineItemIn objects; pydantic would reject a parent-class
    instance for an InvoiceLineItemIn field, so upgrade them (they simply carry no line id)."""
    if isinstance(value, (list, tuple)):
        return [
            item.model_dump() if isinstance(item, LineItemIn) and not isinstance(item, InvoiceLineItemIn) else item
            for item in value
        ]
    return value


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    discount_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    notes: Optional[str] = Field(default=None, max_length=_MAX_TEXT_LENGTH)
    terms: Optional[str] = Field(default=None, max_length=_MAX_TEXT_LENGTH)
    items: List[InvoiceLineItemIn] = Field(..., min_length=1)

    _currency = field_validator("currency")(_upper_currency)

    @field_validator("items", mode="before")
    @classmethod
    def _shared_line_items(cls, value):
        return _accept_shared_line_items(value)


class InvoiceUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    discount_pct: Optional[Decimal] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = Field(default=None, max_length=_MAX_TEXT_LENGTH)
    terms: Optional[str] = Field(default=None, max_length=_MAX_TEXT_LENGTH)
    items: Optional[List[InvoiceLineItemIn]] = Field(default=None, min_length=1)

    _currency = field_validator("currency")(_upper_currency)

    @field_validator("items", mode="before")
    @classmethod
    def _shared_line_items(cls, value):
        return _accept_shared_line_items(value)


class InvoiceVoidIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class RecordPaymentIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    amount: Decimal = Field(..., gt=0)
    method: PaymentMethod
    paid_at: Optional[datetime] = None
    reference: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None

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


class InvoicePaymentRef(BaseModel):
    id: str
    payment_number: str
    amount: str  # amount allocated to this invoice
    method: PaymentMethod
    paid_at: Optional[datetime] = None
    status: PaymentStatus


class InvoiceOut(BaseModel):
    id: str
    invoice_number: str
    customer: CustomerRef
    subscription_id: Optional[str] = None
    quote_id: Optional[str] = None
    status: InvoiceStatus
    issue_date: date
    due_date: date
    currency: str
    subtotal: str
    discount_pct: str
    discount_amount: str
    tax_amount: str
    cgst_amount: str = "0.00"
    sgst_amount: str = "0.00"
    igst_amount: str = "0.00"
    supply_type: Optional[str] = None
    place_of_supply_code: Optional[str] = None
    place_of_supply_name: Optional[str] = None
    customer_gstin: Optional[str] = None
    supplier_gstin: Optional[str] = None
    total: str
    amount_paid: str
    amount_due: str
    notes: Optional[str] = None
    terms: Optional[str] = None
    items: List[LineItemOut]
    public_url: str
    pdf_url: str
    sent_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None
    last_reminder_at: Optional[datetime] = None
    reminder_count: int
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    days_overdue: int
    # Only set (True/False) right after a /send or /send-reminder call whose
    # org has an SMTP integration configured; None on a plain fetch. Lets the
    # frontend warn when the status flips to "sent" but the email itself
    # didn't actually go out, instead of implying delivery succeeded.
    email_delivery_failed: Optional[bool] = None
    payments: List[InvoicePaymentRef] = []
    approval_request_id: Optional[str] = None
    is_pending_approval: bool = False
    created_by: Optional[UserRef] = None
    created_at: datetime
    updated_at: datetime


class InvoiceCurrencyTotals(BaseModel):
    currency: str
    count: int
    total_outstanding: str
    total_revenue: str


class InvoiceSummaryKPIs(BaseModel):
    total_invoices: int
    draft_count: int
    sent_count: int
    partially_paid_count: int
    paid_count: int
    overdue_count: int
    void_count: int
    # In `currency` (the organization's base currency) only; never summed across currencies.
    currency: str = "INR"
    total_outstanding: str
    total_revenue: str
    by_currency: List[InvoiceCurrencyTotals] = []

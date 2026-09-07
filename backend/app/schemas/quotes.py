"""Quote schemas (contract section 6) plus the InvoiceOut-shaped response of
POST /quotes/{id}/convert and the public hosted-page shapes."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.common_refs import CustomerRef, LineItemIn, LineItemOut, UserRef


class QuoteCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str
    title: Optional[str] = Field(None, max_length=200)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    discount_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    notes: Optional[str] = None
    terms: Optional[str] = None
    items: List[LineItemIn] = Field(..., min_length=1)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v):
        return v.upper() if isinstance(v, str) else v


class QuoteUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: Optional[str] = None
    title: Optional[str] = Field(None, max_length=200)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    discount_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    notes: Optional[str] = None
    terms: Optional[str] = None
    items: Optional[List[LineItemIn]] = Field(None, min_length=1)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v):
        return v.upper() if isinstance(v, str) else v


class QuoteDeclineIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


class QuoteConvertIn(BaseModel):
    issue_date: Optional[date] = None
    due_date: Optional[date] = None


class QuoteOut(BaseModel):
    id: str
    quote_number: str
    customer: CustomerRef
    status: str
    title: Optional[str] = None
    issue_date: date
    expiry_date: Optional[date] = None
    currency: str
    subtotal: str
    discount_pct: str
    discount_amount: str
    tax_amount: str
    total: str
    notes: Optional[str] = None
    terms: Optional[str] = None
    items: List[LineItemOut]
    public_url: Optional[str] = None
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    declined_at: Optional[datetime] = None
    converted_invoice_id: Optional[str] = None
    approval_request_id: Optional[str] = None
    created_by: Optional[UserRef] = None
    created_at: datetime
    updated_at: datetime


class InvoicePaymentRow(BaseModel):
    id: str
    payment_number: str
    amount: str
    method: str
    paid_at: Optional[datetime] = None
    status: str


class InvoiceFromQuoteOut(BaseModel):
    """InvoiceOut per contract section 8, produced when a quote is converted."""

    id: str
    invoice_number: str
    customer: CustomerRef
    subscription_id: Optional[str] = None
    quote_id: Optional[str] = None
    status: str
    issue_date: date
    due_date: date
    currency: str
    subtotal: str
    discount_pct: str
    discount_amount: str
    tax_amount: str
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
    payments: List[InvoicePaymentRow]
    created_by: Optional[UserRef] = None
    created_at: datetime
    updated_at: datetime


# --- public hosted page -----------------------------------------------------------------


class PublicQuoteOrganization(BaseModel):
    name: str
    legal_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    gstin: Optional[str] = None
    logo_url: Optional[str] = None


class PublicQuoteCustomer(BaseModel):
    display_name: str
    company_name: Optional[str] = None
    email: Optional[str] = None
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_postal_code: Optional[str] = None
    billing_country: Optional[str] = None


class PublicQuote(BaseModel):
    quote_number: str
    status: str
    title: Optional[str] = None
    issue_date: date
    expiry_date: Optional[date] = None
    currency: str
    subtotal: str
    discount_pct: str
    discount_amount: str
    tax_amount: str
    total: str
    notes: Optional[str] = None
    terms: Optional[str] = None
    items: List[LineItemOut]
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    declined_at: Optional[datetime] = None
    organization: PublicQuoteOrganization
    customer: PublicQuoteCustomer


class PublicQuoteAcceptIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    accepted_by_name: str = Field(..., min_length=1, max_length=200)


class PublicQuoteDeclineIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


class PublicQuoteStatusOut(BaseModel):
    status: str

"""Customer request/response schemas (contract section 4)."""
import re
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models import CustomerStatus
from backend.app.schemas.common_refs import CustomerRef

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email_format(value: Optional[str]) -> Optional[str]:
    """Light-weight email check shared by the API schemas and the CSV importer."""
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    if not EMAIL_RE.match(value):
        raise ValueError("invalid email address")
    return value.lower()


class ContactIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=40)
    designation: Optional[str] = Field(None, max_length=120)
    is_primary: bool = False

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return validate_email_format(v)


class ContactOut(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None
    is_primary: bool


class _CustomerFields(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=40)
    website: Optional[str] = Field(None, max_length=255)
    gstin: Optional[str] = Field(None, max_length=15)
    pan: Optional[str] = Field(None, max_length=10)
    tax_exempt: Optional[bool] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    payment_terms_days: Optional[int] = Field(None, ge=0, le=365)
    status: Optional[CustomerStatus] = None
    billing_address_line1: Optional[str] = Field(None, max_length=255)
    billing_address_line2: Optional[str] = Field(None, max_length=255)
    billing_city: Optional[str] = Field(None, max_length=120)
    billing_state: Optional[str] = Field(None, max_length=120)
    billing_postal_code: Optional[str] = Field(None, max_length=20)
    billing_country: Optional[str] = Field(None, min_length=2, max_length=2)
    notes: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return validate_email_format(v)

    @field_validator("currency", "billing_country")
    @classmethod
    def _upper(cls, v):
        return v.upper() if isinstance(v, str) else v


class CustomerCreate(_CustomerFields):
    display_name: str = Field(..., min_length=1, max_length=200)
    contacts: List[ContactIn] = Field(default_factory=list)


class CustomerUpdate(_CustomerFields):
    display_name: Optional[str] = Field(None, min_length=1, max_length=200)


class CustomerStats(BaseModel):
    open_invoice_count: int
    outstanding_amount: str
    total_billed: str
    total_paid: str
    active_subscriptions: int


class CustomerOut(BaseModel):
    id: str
    customer_number: str
    display_name: str
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    tax_exempt: bool
    currency: str
    payment_terms_days: int
    status: str
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_postal_code: Optional[str] = None
    billing_country: Optional[str] = None
    notes: Optional[str] = None
    portal_url: Optional[str] = None
    contacts: List[ContactOut]
    stats: Optional[CustomerStats] = None
    created_at: datetime
    updated_at: datetime


# --- minimal rows for /customers/{id}/invoices | payments | subscriptions ---------------


class CustomerInvoiceRow(BaseModel):
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
    sent_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    days_overdue: int
    created_at: datetime
    updated_at: datetime


class CustomerPaymentRow(BaseModel):
    id: str
    payment_number: str
    customer: Optional[CustomerRef] = None
    amount: str
    currency: str
    method: str
    gateway: str
    status: str
    reconciliation_status: str
    reference: Optional[str] = None
    paid_at: Optional[datetime] = None
    amount_refunded: str
    created_at: datetime
    updated_at: datetime


class CustomerSubscriptionPlan(BaseModel):
    id: str
    name: str
    code: str
    billing_interval: str
    interval_count: int
    unit_amount: str
    currency: str
    product_name: str


class CustomerSubscriptionRow(BaseModel):
    id: str
    subscription_number: str
    customer: CustomerRef
    plan: CustomerSubscriptionPlan
    quantity: int
    status: str
    start_date: date
    trial_end: Optional[date] = None
    current_period_start: date
    current_period_end: date
    next_billing_date: Optional[date] = None
    cancel_at_period_end: bool
    created_at: datetime
    updated_at: datetime

"""Schemas for the hosted payment page (/public/invoices) and Razorpay webhooks."""
from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models import InvoiceStatus
from backend.app.schemas.common_refs import LineItemOut
from backend.app.schemas.invoices import InvoicePaymentRef


class PublicOrganization(BaseModel):
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
    pan: Optional[str] = None
    logo_url: Optional[str] = None


class PublicCustomer(BaseModel):
    display_name: str
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_postal_code: Optional[str] = None
    billing_country: Optional[str] = None


class PublicRazorpay(BaseModel):
    enabled: bool
    key_id: Optional[str] = None
    # Set when online payment is switched off for the merchant (e.g. suspended organization).
    unavailable_reason: Optional[str] = None


class PublicInvoice(BaseModel):
    invoice_number: str
    status: InvoiceStatus
    issue_date: date
    due_date: date
    currency: str
    subtotal: str
    discount_pct: str
    discount_amount: str
    tax_amount: str
    # GST heads so the customer's copy matches the tax invoice PDF.
    cgst_amount: str = "0.00"
    sgst_amount: str = "0.00"
    igst_amount: str = "0.00"
    supply_type: Optional[str] = None
    place_of_supply_name: Optional[str] = None
    total: str
    amount_paid: str
    amount_due: str
    items: List[LineItemOut]
    notes: Optional[str] = None
    terms: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    days_overdue: int
    pdf_url: str
    organization: PublicOrganization
    customer: PublicCustomer
    payments: List[InvoicePaymentRef] = []
    razorpay: PublicRazorpay


class RazorpayOrderIn(BaseModel):
    amount: Optional[Decimal] = Field(default=None, gt=0)


class RazorpayPrefill(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    contact: Optional[str] = None


class RazorpayOrderOut(BaseModel):
    order_id: str
    amount: int  # paise
    currency: str
    key_id: str
    payment_id: str
    invoice_number: str
    organization_name: str
    prefill: RazorpayPrefill


class RazorpayVerifyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    razorpay_order_id: str = Field(..., min_length=1)
    razorpay_payment_id: str = Field(..., min_length=1)
    razorpay_signature: str = Field(..., min_length=1)


class RazorpayVerifyOut(BaseModel):
    status: str
    payment_number: str
    invoice_status: InvoiceStatus
    amount_due: str


class WebhookAck(BaseModel):
    received: bool = True

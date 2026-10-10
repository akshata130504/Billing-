"""Quote schemas (contract section 6) plus the InvoiceOut-shaped response of
POST /quotes/{id}/convert and the public hosted-page shapes."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.schemas.common_refs import CustomerRef, LineItemIn, LineItemOut, PublicLineItemOut, StrictRequest, UserRef

# Technical ceiling only (abuse/overflow prevention) — the business rules define no cap.
_MAX_TEXT_LENGTH = 10000


class QuoteLineItemIn(LineItemIn, StrictRequest):
    """A quote line as posted by the client. ``id`` is the stored id of an existing line of THIS
    quote that the client is keeping (it lets the server tell a retained line from a removed and
    re-added one); omit it on new lines. Quote-specific so the shared LineItemIn contract used by
    invoices and CPQ is unchanged."""

    id: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def _empty_id_to_none(cls, value):
        return None if value == "" else value


def _accept_shared_line_items(value):
    """Python callers may still pass plain LineItemIn objects; pydantic would reject a parent-class
    instance for a QuoteLineItemIn field, so upgrade them (they simply carry no line id)."""
    if isinstance(value, (list, tuple)):
        return [
            item.model_dump() if isinstance(item, LineItemIn) and not isinstance(item, QuoteLineItemIn) else item
            for item in value
        ]
    return value


class QuoteCreate(StrictRequest):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str
    title: Optional[str] = Field(None, max_length=200)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    discount_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    notes: Optional[str] = Field(None, max_length=_MAX_TEXT_LENGTH)
    terms: Optional[str] = Field(None, max_length=_MAX_TEXT_LENGTH)
    items: List[QuoteLineItemIn] = Field(..., min_length=1)

    @field_validator("items", mode="before")
    @classmethod
    def _shared_line_items(cls, value):
        return _accept_shared_line_items(value)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v):
        return v.upper() if isinstance(v, str) else v

    @field_validator("issue_date")
    @classmethod
    def _issue_date_not_past(cls, v):
        # Lenient, timezone-agnostic backstop: no organization's local date is earlier than
        # the UTC date at now-14h (UTC-12 is the westernmost zone). The strict check against
        # the organization's own business day lives in quote_service.create_quote.
        from backend.app.services import timezones

        if v and v < (timezones.utc_now() - timedelta(hours=14)).date():
            raise ValueError("Issue date cannot be in the past.")
        return v

    @model_validator(mode="after")
    def _expiry_after_issue(self):
        if self.issue_date and self.expiry_date and self.expiry_date <= self.issue_date:
            raise ValueError("Expiry date must be after the issue date.")
        return self


class QuoteUpdate(StrictRequest):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: Optional[str] = None
    title: Optional[str] = Field(None, max_length=200)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    discount_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    notes: Optional[str] = Field(None, max_length=_MAX_TEXT_LENGTH)
    terms: Optional[str] = Field(None, max_length=_MAX_TEXT_LENGTH)
    items: Optional[List[QuoteLineItemIn]] = Field(None, min_length=1)

    @field_validator("items", mode="before")
    @classmethod
    def _shared_line_items(cls, value):
        return _accept_shared_line_items(value)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v):
        return v.upper() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _expiry_after_issue(self):
        if self.issue_date and self.expiry_date and self.expiry_date <= self.issue_date:
            raise ValueError("Expiry date must be after the issue date.")
        return self


class QuoteDeclineIn(StrictRequest):
    reason: Optional[str] = Field(None, max_length=500)


class QuoteOverrideIn(StrictRequest):
    """Admin override that records the customer's decision on their behalf (e.g. a signed PDF or
    a phone call). The reason is mandatory so the audit trail says why staff, not the customer,
    moved the quote."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(..., min_length=3, max_length=500)


class QuoteConvertIn(StrictRequest):
    issue_date: Optional[date] = None
    due_date: Optional[date] = None


class QuoteToSubscriptionIn(StrictRequest):
    """POST /quotes/{id}/convert-to-subscription."""

    start_date: Optional[date] = None
    # None = the primary plan's trial_days (legacy plans; catalog offerings have none).
    trial_days: Optional[int] = Field(None, ge=0, le=365)
    auto_renewal: bool = True
    # Default: issue the first period invoice when the subscription starts active.
    generate_first_invoice: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=2000)


class QuoteDecisionOut(BaseModel):
    """Who recorded the accept/decline: the customer on their link, or staff via admin override."""

    outcome: str  # accepted | declined
    actor_type: str  # customer | staff
    # "Accepted by customer" | "Declined by customer" | "Marked accepted by admin" | "Marked declined by admin"
    title: Optional[str] = None
    actor_display: Optional[str] = None  # e.g. "Priya Sharma (Acme Corp)" or the admin's name
    name: Optional[str] = None  # the name the customer signed with, or the staff user
    reason: Optional[str] = None
    at: Optional[datetime] = None


class SupplyPreviewOut(BaseModel):
    """The server's GST treatment for this organization -> customer, so form previews
    split tax exactly the way the saved document will."""

    supply_type: str
    charges_gst: bool  # False when the organization has no GSTIN (no GST is charged)
    place_of_supply_code: Optional[str] = None
    place_of_supply_name: Optional[str] = None


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
    cgst_amount: str = "0.00"
    sgst_amount: str = "0.00"
    igst_amount: str = "0.00"
    supply_type: Optional[str] = None
    place_of_supply_code: Optional[str] = None
    place_of_supply_name: Optional[str] = None
    total: str
    notes: Optional[str] = None
    terms: Optional[str] = None
    items: List[LineItemOut]
    public_url: Optional[str] = None
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    declined_at: Optional[datetime] = None
    converted_invoice_id: Optional[str] = None
    converted_subscription_id: Optional[str] = None
    approval_request_id: Optional[str] = None
    # Detail responses only: how the accept/decline was recorded (None until decided).
    customer_decision: Optional[QuoteDecisionOut] = None
    # Only set on the send response: True when the customer email was handed to SMTP,
    # False when it could not be delivered (no email on file, SMTP off or failing).
    email_sent: Optional[bool] = None
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
    items: List[PublicLineItemOut]
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    declined_at: Optional[datetime] = None
    organization: PublicQuoteOrganization
    customer: PublicQuoteCustomer
    # Set when the merchant cannot take decisions right now (e.g. suspended organization).
    actions_unavailable_reason: Optional[str] = None


class PublicQuoteAcceptIn(StrictRequest):
    model_config = ConfigDict(str_strip_whitespace=True)

    accepted_by_name: str = Field(..., min_length=1, max_length=200)


class PublicQuoteDeclineIn(StrictRequest):
    reason: Optional[str] = Field(None, max_length=500)


class PublicQuoteStatusOut(BaseModel):
    status: str

"""Owner actions on the organization's paid Rooman plan."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.organization import UTCDateTime


class CancelPlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["at_period_end", "immediately"]


class CancelPlanOut(BaseModel):
    status: Literal["scheduled", "cancelled"]
    effective_at: UTCDateTime  # scheduled: when access ends; cancelled: when it ended
    already: bool  # true when this request found the cancellation already in place (nothing new was sent)
    message: str


class BilledToOut(BaseModel):
    """The organization's billing identity when the payment was recorded (Settings -> Organization); not live."""

    name: str
    legal_name: Optional[str] = None
    email: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    gstin: Optional[str] = None


class PaymentReceiptOut(BaseModel):
    id: str
    receipt_number: str
    document_type: Literal["payment_receipt"]  # never a tax invoice
    note: str
    status: Literal["paid"]
    kind: Literal["initial", "renewal"]
    cycle_number: Optional[int] = None
    amount_minor: int
    currency: str
    method: Optional[str] = None
    paid_at: UTCDateTime
    issued_at: UTCDateTime
    period_start: Optional[UTCDateTime] = None
    period_end: Optional[UTCDateTime] = None
    plan_code: str
    plan_name: Optional[str] = None
    billing_interval: str
    billing_interval_count: int
    sandbox: bool
    mode: str
    provider_payment_id: str
    provider_invoice_id: Optional[str] = None
    billed_to: BilledToOut


class PaymentReceiptPageOut(BaseModel):
    items: List[PaymentReceiptOut]
    total: int
    page: int
    page_size: int
    total_pages: int

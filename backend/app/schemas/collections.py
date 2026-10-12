"""Request/response schemas for /collections."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models import CollectionActivityType, CollectionStatus, InvoiceStatus, PromiseToPayStatus
from backend.app.schemas.common_refs import CustomerRef, UserRef


class CollectionActivityIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    activity_type: CollectionActivityType
    note: Optional[str] = Field(default=None, max_length=4000)
    activity_at: Optional[datetime] = None
    next_follow_up_at: Optional[datetime] = None


class CollectionActivityOut(BaseModel):
    id: str
    invoice_id: str
    activity_type: CollectionActivityType
    note: Optional[str] = None
    activity_at: datetime
    next_follow_up_at: Optional[datetime] = None
    created_by: Optional[UserRef] = None
    created_at: datetime


class PromiseToPayIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    promised_amount: Decimal = Field(..., gt=0)
    promised_date: date
    note: Optional[str] = Field(default=None, max_length=2000)


class PromiseToPayUpdateIn(BaseModel):
    status: PromiseToPayStatus


class PromiseToPayOut(BaseModel):
    id: str
    invoice_id: str
    promised_amount: str
    promised_date: date
    note: Optional[str] = None
    status: PromiseToPayStatus
    created_by: Optional[UserRef] = None
    created_at: datetime
    updated_at: datetime


class CollectionStatusUpdateIn(BaseModel):
    status: CollectionStatus
    note: Optional[str] = Field(default=None, max_length=2000)


class CollectionInvoiceOut(BaseModel):
    """One row of the collections invoice list."""

    id: str
    invoice_number: str
    customer: CustomerRef
    invoice_status: InvoiceStatus
    issue_date: date
    due_date: date
    total: str
    amount_paid: str
    amount_due: str
    currency: str = "INR"
    days_overdue: int
    aging_bucket: str
    collection_status: CollectionStatus
    last_contact_at: Optional[datetime] = None
    next_follow_up_at: Optional[datetime] = None


class CollectionInvoiceDetailOut(CollectionInvoiceOut):
    activities: List[CollectionActivityOut] = []
    promises: List[PromiseToPayOut] = []


class AgingBucketOut(BaseModel):
    bucket: str
    count: int
    amount: str


class CollectionPipelineEntry(BaseModel):
    status: CollectionStatus
    count: int
    amount: str


class TopOverdueCustomer(BaseModel):
    customer: CustomerRef
    outstanding_amount: str
    overdue_amount: str
    invoice_count: int
    currency: str


class UpcomingDueInvoice(BaseModel):
    id: str
    invoice_number: str
    customer: CustomerRef
    due_date: date
    amount_due: str
    currency: str


class CollectionsKPIs(BaseModel):
    total_outstanding: str
    overdue_amount: str
    current_due: str
    due_in_7_days: str
    due_in_30_days: str
    # currency_totals.collection_rate: net cash collected / invoiced over the last 30 days.
    collection_rate: Optional[str] = None
    overdue_invoice_count: int


class CurrencyCollectionsKPIs(CollectionsKPIs):
    currency: str


class CollectionsDashboardOut(BaseModel):
    # `kpis`, `aging_summary`, `pipeline` and `top_overdue_customers` are in `currency`
    # (default: the organization's base currency); amounts are never summed across
    # currencies. `kpis_by_currency` has the KPIs for every currency in `currencies`.
    currency: str
    currencies: List[str] = []
    kpis: CollectionsKPIs
    kpis_by_currency: List[CurrencyCollectionsKPIs] = []
    aging_summary: List[AgingBucketOut]
    pipeline: List[CollectionPipelineEntry]
    recent_activities: List[CollectionActivityOut]
    top_overdue_customers: List[TopOverdueCustomer]
    upcoming_due_invoices: List[UpcomingDueInvoice]

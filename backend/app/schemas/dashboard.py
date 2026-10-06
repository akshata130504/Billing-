"""Schemas for the control-center read models (contract §10) and admin jobs."""
from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel

from backend.app.schemas.common_refs import CustomerRef
from backend.app.schemas.payments import PaymentOut

DashboardRange = Literal["today", "7_days", "30_days", "3_months", "12_months"]


class DashboardMetrics(BaseModel):
    total_revenue: str
    revenue_change_pct: Optional[str] = None
    outstanding_amount: str
    outstanding_count: int
    overdue_count: int
    active_customers: int
    new_customers: int
    at_risk_amount: str
    at_risk_count: int


class TrendPoint(BaseModel):
    label: str
    period_start: date
    revenue: str
    invoiced: str


class RevenueBlock(BaseModel):
    mrr: str
    arr: str
    mrr_change_pct: Optional[str] = None
    # Currency of `mrr`/`arr` (the org's base currency). Subscriptions billed in other
    # currencies are reported per currency here instead of being summed in.
    mrr_currency: Optional[str] = None
    mrr_other_currencies: Dict[str, str] = {}
    trend: List[TrendPoint]


class PipelineBucket(BaseModel):
    count: int
    amount: str


class Pipeline(BaseModel):
    draft: PipelineBucket
    sent: PipelineBucket
    partially_paid: PipelineBucket
    overdue: PipelineBucket
    paid_this_period: PipelineBucket


class CustomerHealth(BaseModel):
    active: int
    trialing: int
    past_due: int
    paused: int
    cancelled_this_period: int
    # Logo churn for the selected range: customers lost / customers billing at period start.
    churned_customers: int = 0
    customers_at_period_start: int = 0
    churn_rate: Optional[str] = None


class Recovery(BaseModel):
    failed_payments: int
    failed_amount: str
    recovered_amount: str
    reminders_sent: int


ActivityCategory = Literal["billing", "customers", "payments", "system"]
ActivitySeverity = Literal["normal", "warning", "danger", "success"]


class ActivityItem(BaseModel):
    id: str
    title: str
    description: str
    timestamp: datetime
    category: ActivityCategory
    severity: ActivitySeverity
    entity_type: str
    entity_id: Optional[str] = None


class DashboardSummary(BaseModel):
    currency: str
    range: DashboardRange
    period_start: date
    period_end: date
    metrics: DashboardMetrics
    revenue: RevenueBlock
    pipeline: Pipeline
    customer_health: CustomerHealth
    recovery: Recovery
    recent_transactions: List[PaymentOut]
    activity: List[ActivityItem]


ActionCategory = Literal["overdue", "failed_payment", "expiring_trial", "pending_quote", "pending_approval"]
ActionUrgency = Literal["critical", "high", "medium"]
SuggestedAction = Literal["send_reminder", "retry_payment", "convert_trial", "review_quote", "review_approval"]


class ActionItem(BaseModel):
    id: str
    category: ActionCategory
    title: str
    description: str
    amount: Optional[str] = None
    customer: Optional[CustomerRef] = None
    entity_type: str
    entity_id: str
    due_info: str
    urgency: ActionUrgency
    suggested_action: SuggestedAction


class ActionCounts(BaseModel):
    overdue: int
    failed_payment: int
    expiring_trial: int
    pending_quote: int
    pending_approval: int


class ActionCenterResponse(BaseModel):
    items: List[ActionItem]
    counts: ActionCounts


CalendarEventType = Literal["invoice_due", "subscription_renewal", "trial_ending", "quote_expiry"]


class CalendarEvent(BaseModel):
    id: str
    date: date
    type: CalendarEventType
    title: str
    customer: Optional[CustomerRef] = None
    amount: Optional[str] = None
    entity_type: str
    entity_id: str
    status: str


class CalendarResponse(BaseModel):
    month: str
    events: List[CalendarEvent]


# --- server-side summary counters (dashboard_summary_service) -------------------------------------


class QuoteValueByCurrency(BaseModel):
    currency: str
    count: int
    total: str
    open_total: str


class QuotesSummary(BaseModel):
    total_count: int
    by_status: Dict[str, int]
    # KPI tiles: draft, pending_approval, sent (sent+viewed), accepted (accepted/invoiced/converted)
    groups: Dict[str, int]
    value_by_currency: List[QuoteValueByCurrency]
    base_currency: str


class OfferingCounts(BaseModel):
    total: int
    active: int
    inactive: int
    by_type: Dict[str, int]
    active_by_type: Dict[str, int]
    inactive_by_type: Dict[str, int]


class PriceBookCounts(BaseModel):
    total: int
    by_status: Dict[str, int]


class CatalogSummary(BaseModel):
    offerings: OfferingCounts
    price_books: PriceBookCounts


class DealValueByCurrency(BaseModel):
    currency: str
    count: int
    total: str


class DealsSummary(BaseModel):
    total_count: int
    by_status: Dict[str, int]
    # KPI tiles: pending (pending_approval), approved (approved+configured), converted
    groups: Dict[str, int]
    value_by_currency: List[DealValueByCurrency]
    base_currency: str


class InvoiceStatusAmount(BaseModel):
    count: int
    total: str
    amount_due: str


class InvoiceCurrencyTotals(BaseModel):
    currency: str
    count: int
    total: str  # excludes void
    amount_paid: str
    amount_due: str  # excludes draft and void
    by_status: Dict[str, InvoiceStatusAmount]


class InvoicesBlock(BaseModel):
    total_count: int
    by_status: Dict[str, int]
    by_currency: List[InvoiceCurrencyTotals]


class ReceivableTotals(BaseModel):
    currency: str
    open_count: int
    amount_due: str
    overdue_count: int
    overdue_amount: str


class CollectedTotals(BaseModel):
    currency: str
    count: int
    gross: str
    refunded: str
    net: str


class SubscriptionsBlock(BaseModel):
    total_count: int
    by_status: Dict[str, int]


class MrrBlock(BaseModel):
    currency: str
    mrr: str
    arr: str
    by_currency: Dict[str, str]
    subscription_count: int


class QuotesBlock(BaseModel):
    total_count: int
    by_status: Dict[str, int]
    value_by_currency: List[QuoteValueByCurrency]


class CreditNoteCurrencyTotals(BaseModel):
    currency: str
    count: int
    issued_total: str
    applied_total: str
    remaining_balance: str
    voided_total: str
    draft_total: str
    count_by_status: Dict[str, int]


class CreditNotesBlock(BaseModel):
    total_count: int
    count_by_status: Dict[str, int]
    currencies: List[CreditNoteCurrencyTotals]


class CustomersBlock(BaseModel):
    total: int
    active: int
    new_in_period: int


class FinancialSummary(BaseModel):
    base_currency: str
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    invoices: InvoicesBlock
    receivables: List[ReceivableTotals]
    payments_collected: List[CollectedTotals]
    subscriptions: SubscriptionsBlock
    mrr: MrrBlock
    quotes: QuotesBlock
    credit_notes: CreditNotesBlock
    customers: CustomersBlock


class JobsRunResult(BaseModel):
    renewals: int
    trials_converted: int
    marked_overdue: int
    reminders_sent: int
    recurring_expenses_processed: Optional[int] = 0
    dunning_recovered: Optional[int] = 0
    scheduled_changes_applied: Optional[int] = 0


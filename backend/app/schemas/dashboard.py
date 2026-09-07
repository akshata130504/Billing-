"""Schemas for the control-center read models (contract §10) and admin jobs."""
from datetime import date, datetime
from typing import List, Literal, Optional

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


class JobsRunResult(BaseModel):
    renewals: int
    trials_converted: int
    marked_overdue: int
    reminders_sent: int

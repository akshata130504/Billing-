"""Pydantic schemas for Customer Lifecycle."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.lifecycle import CustomerLifecycleStage, HealthStatus


class CustomerLifecycleBase(BaseModel):
    lifecycle_stage: CustomerLifecycleStage = CustomerLifecycleStage.ACTIVE
    health_status: HealthStatus = HealthStatus.HEALTHY
    health_score: int = Field(default=85, ge=0, le=100)
    next_action: Optional[str] = None
    next_action_due: Optional[date] = None
    notes: Optional[str] = None


class CustomerLifecycleUpdate(BaseModel):
    lifecycle_stage: Optional[CustomerLifecycleStage] = None
    health_status: Optional[HealthStatus] = None
    health_score: Optional[int] = Field(default=None, ge=0, le=100)
    next_action: Optional[str] = None
    next_action_due: Optional[date] = None
    notes: Optional[str] = None


class CustomerCurrencyTotals(BaseModel):
    currency: str
    total_spent: Decimal
    amount_due: Decimal


class CustomerLifecycleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    customer_name: str
    customer_number: str
    customer_email: Optional[str] = None
    company_name: Optional[str] = None
    lifecycle_stage: CustomerLifecycleStage
    stage_entered_at: datetime
    health_status: HealthStatus
    health_score: int
    next_action: Optional[str] = None
    next_action_due: Optional[date] = None
    notes: Optional[str] = None

    # Aggregated metrics from real database relationships. total_spent / amount_due are in
    # `currency` (the customer's billing currency) only; other currencies are listed in
    # totals_by_currency and never summed in.
    currency: str = "INR"
    total_spent: Decimal = Decimal("0.00")
    amount_due: Decimal = Decimal("0.00")
    totals_by_currency: List[CustomerCurrencyTotals] = []
    active_subscriptions_count: int = 0
    total_invoices_count: int = 0
    total_quotes_count: int = 0
    total_billable_hours: Decimal = Decimal("0.00")
    last_activity_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class LifecycleKPIs(BaseModel):
    total_customers: int
    new_onboarding_count: int
    active_customers_count: int
    renewal_due_count: int
    at_risk_count: int
    churned_count: int
    expansion_count: int


class TimelineEvent(BaseModel):
    id: str
    event_type: str  # e.g. CUSTOMER_CREATED, QUOTE_ISSUED, SUBSCRIPTION_ACTIVATED, INVOICE_SENT, PAYMENT_RECEIVED, TIMESHEET_LOGGED, STAGE_CHANGED
    title: str
    description: Optional[str] = None
    timestamp: datetime
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    status: Optional[str] = None
    actor_label: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class CustomerLifecycleDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer: Dict[str, Any]
    lifecycle: CustomerLifecycleItem
    timeline: List[TimelineEvent]
    subscriptions: List[Dict[str, Any]]
    quotes: List[Dict[str, Any]]
    invoices: List[Dict[str, Any]]
    payments: List[Dict[str, Any]]
    timesheet_summary: Dict[str, Any]

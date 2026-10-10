"""Pydantic schemas for usage meters, events, and aggregates."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.meters import (
    AggregationType,
    UsageAggregateStatus,
    UsageEventStatus,
)


class UsageMeterCreateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=120)
    unit_name: str = Field(default="unit", max_length=40)
    aggregation_type: AggregationType = AggregationType.SUM
    description: Optional[str] = Field(default=None, max_length=300)
    # Flat per-unit usage rate; omit to leave the meter unpriced (usage rates at 0).
    unit_price: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999999999"), decimal_places=4)


class UsageMeterUpdateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    unit_name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    description: Optional[str] = Field(default=None, max_length=300)
    unit_price: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999999999"), decimal_places=4)
    is_active: Optional[bool] = None


class BillingCycleOut(BaseModel):
    id: str
    subscription_id: str
    cycle_number: int
    period_start: date
    period_end: date
    status: str
    invoice_id: Optional[str] = None
    finalized_at: Optional[datetime] = None


class UsageMeterOut(BaseModel):
    id: str
    code: str
    name: str
    unit_name: str
    aggregation_type: AggregationType
    description: Optional[str] = None
    is_active: bool
    unit_price: Optional[Decimal] = None
    created_at: datetime


class UsageEventIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    meter_code: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)
    quantity: Decimal = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    subscription_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    properties: Optional[Dict[str, Any]] = None


class UsageEventBatchIn(BaseModel):
    events: List[UsageEventIn] = Field(..., min_length=1, max_length=1000)


class UsageEventOut(BaseModel):
    id: str
    meter_id: str
    customer_id: str
    subscription_id: Optional[str] = None
    quantity: str
    timestamp: datetime
    idempotency_key: str
    status: UsageEventStatus
    created_at: datetime
    # Labels for the usage history list (GET /meters/events).
    customer_name: Optional[str] = None
    subscription_number: Optional[str] = None


class UsageAggregateOut(BaseModel):
    id: str
    meter_id: str
    subscription_id: str
    billing_cycle_id: Optional[str] = None
    period_start: date
    period_end: date
    total_quantity: str
    rated_amount: str
    status: UsageAggregateStatus
    finalized_at: Optional[datetime] = None
    invoice_id: Optional[str] = None


class UsageMeterSummaryOut(BaseModel):
    """Running total of one meter's accepted events over a period (usage history)."""
    meter_id: str
    meter_code: str
    meter_name: str
    unit_name: str
    aggregation_type: AggregationType
    event_count: int
    total_quantity: str
    last_event_at: Optional[datetime] = None

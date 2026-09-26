"""Pydantic schemas for subscription changes and proration."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.proration import (
    ProrationEffectiveType,
    SubscriptionChangeStatus,
    SubscriptionChangeType,
)


class SubscriptionChangePreviewIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    target_plan_id: Optional[str] = None
    # Move to a recurring Plans & Pricing offering instead of a legacy plan.
    target_offering_id: Optional[str] = None
    target_quantity: Optional[Decimal] = Field(default=None, gt=0)
    effective_date: Optional[date] = None


class PlanRef(BaseModel):
    id: str
    name: str
    unit_amount: str


class SubscriptionChangePreviewOut(BaseModel):
    subscription_id: str
    change_type: str
    old_plan: PlanRef
    new_plan: PlanRef
    old_quantity: str
    new_quantity: str
    period_start: str
    period_end: str
    effective_date: str
    total_days: int
    days_used: int
    days_remaining: int
    unused_credit: str
    remaining_charge: str
    net_amount: str
    explanation: str


class SubscriptionChangeApplyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    target_plan_id: Optional[str] = None
    target_offering_id: Optional[str] = None
    target_quantity: Optional[Decimal] = Field(default=None, gt=0)
    effective_type: ProrationEffectiveType = ProrationEffectiveType.IMMEDIATE
    effective_date: Optional[date] = None


class SubscriptionChangeOut(BaseModel):
    id: str
    subscription_id: str
    change_type: SubscriptionChangeType
    status: SubscriptionChangeStatus
    effective_type: ProrationEffectiveType
    effective_date: date
    target_plan_id: Optional[str] = None
    target_quantity: Optional[str] = None
    old_plan_amount: str
    new_plan_amount: str
    prorated_credit: str
    prorated_charge: str
    net_amount: str
    invoice_id: Optional[str] = None
    credit_note_id: Optional[str] = None
    applied_at: Optional[datetime] = None
    created_at: datetime

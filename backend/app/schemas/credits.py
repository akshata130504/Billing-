"""Schemas for Credit Notes and Credit Applications."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.credits import CreditNoteStatus
from backend.app.schemas.common_refs import CustomerRef


class CreditNoteLineIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(..., min_length=1, max_length=255)
    amount: Decimal = Field(..., gt=0)
    product_id: Optional[str] = None
    plan_id: Optional[str] = None


class CreditNoteLineOut(BaseModel):
    id: str
    description: str
    amount: str
    quantity: Optional[str] = "1"
    unit_price: Optional[str] = None
    tax_rate_pct: Optional[str] = None


class CreditApplicationOut(BaseModel):
    id: str
    invoice_id: str
    amount: str
    applied_at: datetime


class CreditNoteCreateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str
    reason: Optional[str] = Field(default=None, max_length=500)
    reference: Optional[str] = Field(default=None, max_length=120)
    currency: str = Field(default="INR", max_length=3)
    lines: List[CreditNoteLineIn] = Field(..., min_length=1)


class CreditApplicationIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    invoice_id: str
    amount: Decimal = Field(..., gt=0)


class CreditNoteOut(BaseModel):
    id: str
    credit_note_number: str
    customer_id: str
    customer: Optional[CustomerRef] = None
    status: CreditNoteStatus
    currency: str
    subtotal: str
    total: str
    balance_remaining: str
    reason: Optional[str] = None
    notes: Optional[str] = None
    reference: Optional[str] = None
    created_at: datetime
    lines: List[CreditNoteLineOut] = []
    applications: List[CreditApplicationOut] = []


class CreditNoteListOut(BaseModel):
    items: List[CreditNoteOut]
    total: int

"""Schemas for Credit Notes and Credit Applications."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.credits import CreditNoteStatus
from backend.app.schemas.common_refs import CustomerRef


class CreditNoteLineIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(..., min_length=1, max_length=255)
    amount: Decimal = Field(..., gt=0, description="Pre-tax line amount")
    tax_rate_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
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
    # The invoice being corrected; its frozen GST treatment is applied to the credit note.
    invoice_id: Optional[str] = None
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
    invoice_id: Optional[str] = None
    subtotal: str
    tax_amount: str = "0.00"
    cgst_amount: str = "0.00"
    sgst_amount: str = "0.00"
    igst_amount: str = "0.00"
    supply_type: Optional[str] = None
    place_of_supply_name: Optional[str] = None
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
    # Number of credit notes matching the filters (not just this page).
    total: int
    limit: Optional[int] = None
    offset: Optional[int] = None


class CreditNoteCurrencySummary(BaseModel):
    currency: str
    count: int
    issued_total: str
    applied_total: str
    remaining_balance: str
    voided_total: str
    draft_total: str
    count_by_status: Dict[str, int]


class CreditNoteSummaryFilters(BaseModel):
    customer_id: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class CreditNoteSummaryOut(BaseModel):
    total_count: int
    count_by_status: Dict[str, int]
    currencies: List[CreditNoteCurrencySummary]
    filters: CreditNoteSummaryFilters

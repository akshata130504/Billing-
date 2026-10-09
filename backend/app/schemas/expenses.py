"""Pydantic schemas for Expenses and Recurring Expenses."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.models.expenses import (
    ExpenseStatus,
    RecurringExpenseFrequency,
    RecurringExpenseStatus,
)
from backend.app.schemas.validators import Money


class ExpenseBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    date: date
    category: str = Field(..., min_length=1, max_length=100)
    amount: Money = Field(..., gt=Decimal("0.00"))
    currency: str = Field(default="INR", min_length=3, max_length=3)
    billable: bool = False
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    billable_amount: Optional[Money] = Field(default=None, ge=Decimal("0.00"))
    tax_rate: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"), le=Decimal("100.00"))
    invoice_treatment: Optional[str] = None
    invoice_id: Optional[str] = None
    payment_method: str = Field(default="Cash", max_length=50)
    paid_by: str = Field(default="Self", max_length=200)
    status: ExpenseStatus = ExpenseStatus.RECORDED
    receipt_file_name: Optional[str] = None
    receipt_file_size: Optional[str] = None
    receipt_file_type: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v):
        return v.upper() if isinstance(v, str) else v


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseBatchCreate(BaseModel):
    expenses: List[ExpenseCreate]


class ExpenseUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    date: Optional[date] = None
    category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    amount: Optional[Money] = Field(default=None, gt=Decimal("0.00"))
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    billable: Optional[bool] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    billable_amount: Optional[Money] = Field(default=None, ge=Decimal("0.00"))
    tax_rate: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"), le=Decimal("100.00"))
    invoice_treatment: Optional[str] = None
    invoice_id: Optional[str] = None
    payment_method: Optional[str] = Field(default=None, max_length=50)
    paid_by: Optional[str] = Field(default=None, max_length=200)
    status: Optional[ExpenseStatus] = None
    receipt_file_name: Optional[str] = None
    receipt_file_size: Optional[str] = None
    receipt_file_type: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v):
        return v.upper() if isinstance(v, str) else v


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    description: Optional[str] = None
    date: date
    category: str
    amount: Decimal
    currency: str
    billable: bool
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer: Optional[str] = None  # alias
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    project: Optional[str] = None  # alias
    billable_amount: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    invoice_treatment: Optional[str] = None
    invoice_id: Optional[str] = None
    payment_method: str
    paid_by: str
    status: ExpenseStatus
    receipt_file_name: Optional[str] = None
    receipt_file_size: Optional[str] = None
    receipt_file_type: Optional[str] = None
    has_receipt: bool = False
    receipt_url: Optional[str] = None  # authenticated download endpoint
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ExpenseAddToInvoiceIn(BaseModel):
    """Optional target draft invoice; when omitted a new draft is created for the customer."""

    invoice_id: Optional[str] = None


class ExpenseSummaryKPIs(BaseModel):
    total: Decimal = Decimal("0.00")
    billable: Decimal = Decimal("0.00")
    non_billable: Decimal = Decimal("0.00")
    pending: Decimal = Decimal("0.00")


# Recurring Expenses
class RecurringExpenseBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    amount: Money = Field(..., gt=Decimal("0.00"))
    currency: str = Field(default="INR", min_length=3, max_length=3)
    frequency: RecurringExpenseFrequency = RecurringExpenseFrequency.MONTHLY
    start_date: date
    end_date: Optional[date] = None
    never_ends: bool = True
    next_run: Optional[date] = None
    last_run: Optional[date] = None
    billable: bool = False
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    billable_amount: Optional[Money] = Field(default=None, ge=Decimal("0.00"))
    invoice_treatment: Optional[str] = None
    payment_method: str = Field(default="Cash", max_length=50)
    paid_by: str = Field(default="Self", max_length=200)
    status: RecurringExpenseStatus = RecurringExpenseStatus.ACTIVE

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v):
        return v.upper() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before the start date.")
        return self


class RecurringExpenseCreate(RecurringExpenseBase):
    pass


class RecurringExpenseUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    amount: Optional[Money] = Field(default=None, gt=Decimal("0.00"))
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    frequency: Optional[RecurringExpenseFrequency] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    never_ends: Optional[bool] = None
    next_run: Optional[date] = None
    last_run: Optional[date] = None
    billable: Optional[bool] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    billable_amount: Optional[Money] = Field(default=None, ge=Decimal("0.00"))
    invoice_treatment: Optional[str] = None
    payment_method: Optional[str] = Field(default=None, max_length=50)
    paid_by: Optional[str] = Field(default=None, max_length=200)
    status: Optional[RecurringExpenseStatus] = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v):
        return v.upper() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before the start date.")
        return self


class RecurringExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    category: str
    description: Optional[str] = None
    amount: Decimal
    currency: str
    frequency: RecurringExpenseFrequency
    start_date: date
    end_date: Optional[date] = None
    never_ends: bool
    next_run: Optional[date] = None
    last_run: Optional[date] = None
    billable: bool
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    project: Optional[str] = None
    billable_amount: Optional[Decimal] = None
    invoice_treatment: Optional[str] = None
    payment_method: str
    paid_by: str
    status: RecurringExpenseStatus
    created_at: datetime
    updated_at: datetime


class RecurringExpenseSummaryKPIs(BaseModel):
    active_profiles: int = 0
    monthly_recurring: Decimal = Decimal("0.00")
    billable_recurring: Decimal = Decimal("0.00")
    next_run: Optional[str] = None

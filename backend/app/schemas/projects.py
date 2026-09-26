"""Pydantic schemas for Projects."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.models.projects import BillingMethod, ProjectStatus


class ProjectBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    description: Optional[str] = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    billing_method: BillingMethod = BillingMethod.FIXED_PRICE
    budget: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    project_manager: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before the start date.")
        return self


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    billing_method: Optional[BillingMethod] = None
    budget: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))
    project_manager: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before the start date.")
        return self


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer: Optional[str] = None  # alias for frontend convenience
    description: Optional[str] = None
    status: ProjectStatus
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    billing_method: BillingMethod
    budget: Decimal
    billed: Decimal = Decimal("0.00")
    expenses: Decimal = Decimal("0.00")
    project_manager: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectRead):
    timesheets: List[Dict[str, Any]] = []
    expense_list: List[Dict[str, Any]] = []
    invoices: List[Dict[str, Any]] = []
    payments: List[Dict[str, Any]] = []
    transactions: List[Dict[str, Any]] = []


class ProjectInvoiceCreate(BaseModel):
    """Milestone / progress invoice raised from a project (billed to the project's customer)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    amount: Decimal = Field(..., gt=Decimal("0.00"), le=Decimal("999999999999.99"))
    description: Optional[str] = Field(default=None, max_length=500)
    tax_rate_pct: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _due_after_issue(self):
        if self.issue_date and self.due_date and self.due_date < self.issue_date:
            raise ValueError("Due date cannot be before the invoice date.")
        return self


class ProjectInvoiceOut(BaseModel):
    id: str
    projectId: str
    invoiceNumber: str
    date: str
    dueDate: str
    amount: float
    amountDue: float
    currency: str
    status: str
    rawStatus: str


class ProjectSummaryKPIs(BaseModel):
    total_projects: int = 0
    active_projects: int = 0
    total_budget: Decimal = Decimal("0.00")
    total_billed: Decimal = Decimal("0.00")
    total_expenses: Decimal = Decimal("0.00")

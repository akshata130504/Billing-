"""Pydantic schemas for Timesheets and Time Tracking."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.models.timesheets import TimeEntryStatus

# A day of slack so a user logging time from a different timezone than the
# server isn't blocked from entering "today".
_MAX_FUTURE_DAYS = 1


def _reject_far_future(value: Optional[date]) -> Optional[date]:
    if value is not None and (value - date.today()).days > _MAX_FUTURE_DAYS:
        raise ValueError("Time entry date cannot be in the future.")
    return value


class TimeEntryBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    date: date
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_hours: Decimal = Field(..., gt=Decimal("0.00"), le=Decimal("24.00"))
    description: str = Field(..., min_length=1)
    billable: bool = True
    billing_rate: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))

    @field_validator("date")
    @classmethod
    def _date(cls, v):
        return _reject_far_future(v)

    @model_validator(mode="after")
    def _validate_time_range(self):
        if self.start_time and self.end_time:
            try:
                sh, sm = map(int, self.start_time.split(":")[:2])
                eh, em = map(int, self.end_time.split(":")[:2])
                if (eh * 60 + em) <= (sh * 60 + sm):
                    raise ValueError("End time must be later than start time.")
            except ValueError as e:
                if "End time must be later" in str(e):
                    raise
        return self


class TimeEntryCreate(TimeEntryBase):
    pass


class TimeEntryUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    date: Optional[date] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_hours: Optional[Decimal] = Field(default=None, gt=Decimal("0.00"), le=Decimal("24.00"))
    description: Optional[str] = Field(default=None, min_length=1)
    billable: Optional[bool] = None
    billing_rate: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))

    @field_validator("date")
    @classmethod
    def _date(cls, v):
        return _reject_far_future(v)

    @model_validator(mode="after")
    def _validate_time_range(self):
        if self.start_time and self.end_time:
            try:
                sh, sm = map(int, self.start_time.split(":")[:2])
                eh, em = map(int, self.end_time.split(":")[:2])
                if (eh * 60 + em) <= (sh * 60 + sm):
                    raise ValueError("End time must be later than start time.")
            except ValueError as e:
                if "End time must be later" in str(e):
                    raise
        return self


class TimeEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_number: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    date: date
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_hours: Decimal
    description: str
    billable: bool
    billing_rate: Decimal
    billable_amount: Decimal
    status: TimeEntryStatus
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    rejection_reason: Optional[str] = None
    approved_by_id: Optional[str] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class TimeEntrySummaryKPIs(BaseModel):
    total_hours: Decimal
    billable_hours: Decimal
    non_billable_hours: Decimal
    billable_amount: Decimal
    unbilled_amount: Decimal
    billed_amount: Decimal
    pending_approval_count: int


class WeeklyMatrixRow(BaseModel):
    key: str  # e.g. "PRJ-101:Acme Corp" or user ID
    user_id: str
    user_name: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    daily_hours: Dict[str, Decimal]  # "YYYY-MM-DD" -> Decimal hours
    total_hours: Decimal
    billable_hours: Decimal
    billable_amount: Decimal


class WeeklyTimesheetResponse(BaseModel):
    week_start: date
    week_end: date
    total_hours: Decimal
    billable_hours: Decimal
    non_billable_hours: Decimal
    rows: List[WeeklyMatrixRow]
    day_totals: Dict[str, Decimal]


class TimesheetInvoiceCreate(BaseModel):
    customer_id: str
    time_entry_ids: List[str] = Field(..., min_length=1)
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class TimesheetActionReason(BaseModel):
    reason: Optional[str] = None

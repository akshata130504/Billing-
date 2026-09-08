"""Timesheets and Time Tracking API endpoints."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import (
    CurrentContext,
    get_db,
    require_finance,
    require_viewer,
)
from backend.app.models.timesheets import TimeEntryStatus
from backend.app.schemas.timesheets import (
    TimeEntryCreate,
    TimeEntryRead,
    TimeEntrySummaryKPIs,
    TimeEntryUpdate,
    TimesheetActionReason,
    TimesheetInvoiceCreate,
    WeeklyTimesheetResponse,
)
from backend.app.services import timesheet_service

router = APIRouter()


@router.get("", response_model=List[TimeEntryRead])
def list_time_entries(
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    customer_id: Optional[str] = Query(None, description="Customer filter"),
    project_id: Optional[str] = Query(None, description="Project filter"),
    user_id: Optional[str] = Query(None, description="User filter"),
    billable: Optional[bool] = Query(None, description="Billable filter"),
    status: Optional[TimeEntryStatus] = Query(None, description="Status filter"),
    search: Optional[str] = Query(None, description="Search description or project"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Lists time entries with tenant isolation and search/filtering."""
    return timesheet_service.list_time_entries(
        db,
        ctx,
        start_date=start_date,
        end_date=end_date,
        customer_id=customer_id,
        project_id=project_id,
        user_id=user_id,
        billable=billable,
        status=status,
        search=search,
    )


@router.get("/summary", response_model=TimeEntrySummaryKPIs)
def get_summary_kpis(
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Aggregates total hours, billable amounts, and pending approvals."""
    return timesheet_service.get_timesheet_summary_kpis(db, ctx, start_date=start_date, end_date=end_date)


@router.get("/weekly", response_model=WeeklyTimesheetResponse)
def get_weekly_timesheet(
    week_start: date = Query(..., description="Starting date of the week (Monday)"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Returns weekly matrix breakdown grouped by project and customer."""
    return timesheet_service.get_weekly_matrix(db, ctx, week_start=week_start)


@router.post("", response_model=TimeEntryRead, status_code=status.HTTP_201_CREATED)
def create_time_entry(
    payload: TimeEntryCreate,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Creates a new time entry in the organization."""
    return timesheet_service.create_time_entry(db, payload, ctx)


@router.get("/{entry_id}", response_model=TimeEntryRead)
def get_time_entry(
    entry_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Gets details for a single time entry."""
    return timesheet_service.get_time_entry(db, entry_id, ctx)


@router.patch("/{entry_id}", response_model=TimeEntryRead)
def update_time_entry(
    entry_id: str,
    payload: TimeEntryUpdate,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Updates a time entry with RBAC checks."""
    return timesheet_service.update_time_entry(db, entry_id, payload, ctx)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_entry(
    entry_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Deletes an unbilled time entry."""
    timesheet_service.delete_time_entry(db, entry_id, ctx)
    return None


@router.post("/{entry_id}/submit", response_model=TimeEntryRead)
def submit_time_entry(
    entry_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Submits a time entry for approval."""
    return timesheet_service.submit_time_entry(db, entry_id, ctx)


@router.post("/{entry_id}/approve", response_model=TimeEntryRead)
def approve_time_entry(
    entry_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    """Approves a submitted time entry."""
    return timesheet_service.approve_time_entry(db, entry_id, ctx)


@router.post("/{entry_id}/reject", response_model=TimeEntryRead)
def reject_time_entry(
    entry_id: str,
    payload: Optional[TimesheetActionReason] = None,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    """Rejects a submitted time entry with a reason."""
    reason = payload.reason if payload else None
    return timesheet_service.reject_time_entry(db, entry_id, reason=reason, ctx=ctx)


@router.post("/generate-invoice", response_model=Dict[str, Any])
def generate_invoice(
    payload: TimesheetInvoiceCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    """Converts billable time entries into an invoice."""
    return timesheet_service.generate_invoice_from_timesheets(db, payload, ctx)

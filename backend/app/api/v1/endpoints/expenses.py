"""Expenses and Recurring Expenses API endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import (
    CurrentContext,
    get_db,
    require_admin,
    require_finance,
    require_viewer,
)
from backend.app.schemas.expenses import (
    ExpenseAddToInvoiceIn,
    ExpenseBatchCreate,
    ExpenseCreate,
    ExpenseRead,
    ExpenseSummaryKPIs,
    ExpenseUpdate,
    RecurringExpenseCreate,
    RecurringExpenseRead,
    RecurringExpenseSummaryKPIs,
    RecurringExpenseUpdate,
)
from backend.app.services import expense_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Recurring Expenses (Declared before /{expense_id})
# ---------------------------------------------------------------------------


@router.get("/recurring", response_model=List[RecurringExpenseRead], summary="List recurring expenses")
def list_recurring_expenses(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return expense_service.list_recurring_expenses(db, ctx.organization_id)


@router.get("/recurring/summary", response_model=RecurringExpenseSummaryKPIs, summary="Recurring expense summary KPIs")
def get_recurring_summary(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return expense_service.get_recurring_summary_kpis(db, ctx.organization_id)


@router.post("/recurring", response_model=RecurringExpenseRead, status_code=status.HTTP_201_CREATED, summary="Create a recurring expense profile")
def create_recurring_expense(
    data: RecurringExpenseCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    return expense_service.create_recurring_expense(db, ctx.organization_id, data)


@router.get("/recurring/{rec_id}", response_model=RecurringExpenseRead, summary="Get recurring expense profile")
def get_recurring_expense(
    rec_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    rec = expense_service.get_recurring_expense(db, ctx.organization_id, rec_id)
    return expense_service.serialize_recurring(rec)


@router.patch("/recurring/{rec_id}", response_model=RecurringExpenseRead, summary="Update recurring expense profile")
def update_recurring_expense(
    rec_id: str,
    data: RecurringExpenseUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    return expense_service.update_recurring_expense(db, ctx.organization_id, rec_id, data)


@router.delete("/recurring/{rec_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete recurring expense profile")
def delete_recurring_expense(
    rec_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    expense_service.delete_recurring_expense(db, ctx.organization_id, rec_id)


@router.post("/recurring/{rec_id}/toggle-status", response_model=RecurringExpenseRead, summary="Toggle active/paused status")
def toggle_recurring_status(
    rec_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    return expense_service.toggle_recurring_status(db, ctx.organization_id, rec_id)


# ---------------------------------------------------------------------------
# General Expenses
# ---------------------------------------------------------------------------


@router.get("", response_model=List[ExpenseRead], summary="List expenses")
def list_expenses(
    search: Optional[str] = Query(None, description="Search name, customer, project, category"),
    status: Optional[str] = Query(None, description="Filter by status"),
    customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    category: Optional[str] = Query(None, description="Filter by category"),
    billable: Optional[bool] = Query(None, description="Filter by billable"),
    sort_by: Optional[str] = Query("newest", description="Sorting method"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return expense_service.list_expenses(
        db,
        ctx.organization_id,
        search=search,
        status=status,
        customer_id=customer_id,
        project_id=project_id,
        category=category,
        billable=billable,
        sort_by=sort_by,
    )


@router.get("/summary", response_model=ExpenseSummaryKPIs, summary="Get expense summary KPIs")
def get_expense_summary(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return expense_service.get_summary_kpis(db, ctx.organization_id)


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED, summary="Create an expense")
def create_expense(
    data: ExpenseCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    return expense_service.create_expense(db, ctx.organization_id, data)


@router.post("/batch", summary="Batch import expenses")
def batch_import_expenses(
    data: ExpenseBatchCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    count = expense_service.batch_import_expenses(db, ctx.organization_id, data.expenses)
    return {"imported": count}


@router.get("/{expense_id}", response_model=ExpenseRead, summary="Get an expense")
def get_expense(
    expense_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    expense = expense_service.get_expense(db, ctx.organization_id, expense_id)
    return expense_service.serialize_expense(expense)


@router.patch("/{expense_id}", response_model=ExpenseRead, summary="Update an expense")
def update_expense(
    expense_id: str,
    data: ExpenseUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    return expense_service.update_expense(db, ctx.organization_id, expense_id, data)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an expense")
def delete_expense(
    expense_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    expense_service.delete_expense(db, ctx.organization_id, expense_id)


@router.post(
    "/{expense_id}/add-to-invoice",
    response_model=ExpenseRead,
    summary="Bill the expense as a line on a draft invoice (new draft when no invoice_id)",
)
def add_to_invoice(
    expense_id: str,
    body: ExpenseAddToInvoiceIn = Body(default=ExpenseAddToInvoiceIn()),
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    return expense_service.add_to_invoice(db, ctx, expense_id, invoice_id=body.invoice_id)


@router.post("/{expense_id}/receipt", response_model=ExpenseRead, summary="Upload (or replace) the expense receipt")
async def upload_receipt(
    expense_id: str,
    file: UploadFile = File(...),
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    # Read at most one byte past the limit so an oversized upload is rejected cheaply.
    content = await file.read(expense_service.MAX_RECEIPT_SIZE + 1)
    return expense_service.save_receipt(
        db, ctx.organization_id, expense_id, file.filename or "", file.content_type, content
    )


@router.get("/{expense_id}/receipt", response_class=FileResponse, summary="Download the expense receipt")
def download_receipt(
    expense_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    path, media_type, name = expense_service.get_receipt_file(db, ctx.organization_id, expense_id)
    return FileResponse(path, media_type=media_type, filename=name)

"""Credit notes endpoints."""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.core.exceptions import ValidationAppError
from backend.app.models.credits import CreditNoteStatus
from backend.app.schemas.credits import (
    CreditApplicationIn,
    CreditNoteCreateIn,
    CreditNoteListOut,
    CreditNoteOut,
    CreditNoteSummaryOut,
)
from backend.app.services import credit_service

router = APIRouter()


def _check_range(date_from: Optional[date], date_to: Optional[date]) -> None:
    if date_from and date_to and date_from > date_to:
        raise ValidationAppError("date_from must be on or before date_to.")


@router.get("", response_model=CreditNoteListOut, summary="List credit notes")
def list_credit_notes(
    customer_id: Optional[str] = Query(None),
    status_: Optional[CreditNoteStatus] = Query(None, alias="status"),
    date_from: Optional[date] = Query(None, description="Issue date on or after (inclusive)"),
    date_to: Optional[date] = Query(None, description="Issue date on or before (inclusive)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    _check_range(date_from, date_to)
    filters = dict(customer_id=customer_id, status_=status_, date_from=date_from, date_to=date_to)
    notes = credit_service.list_credit_notes(
        db, organization_id=ctx.organization_id, limit=limit, offset=offset, **filters
    )
    items = [credit_service.serialize_credit_note(cn) for cn in notes]
    # `total` is the number of matching credit notes, not the size of this page.
    total = credit_service.count_credit_notes(db, ctx.organization_id, **filters)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# Declared BEFORE /{credit_note_id} so "summary" is never treated as an id.
@router.get("/summary", response_model=CreditNoteSummaryOut, summary="Credit note totals by currency and status")
def credit_notes_summary(
    customer_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None, alias="from", description="Issue date on or after (inclusive)"),
    date_to: Optional[date] = Query(None, alias="to", description="Issue date on or before (inclusive)"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    _check_range(date_from, date_to)
    return credit_service.credit_notes_summary(
        db, ctx.organization_id, customer_id=customer_id, date_from=date_from, date_to=date_to
    )


@router.post("", response_model=CreditNoteOut, status_code=status.HTTP_201_CREATED, summary="Create a credit note")
def create_credit_note(
    body: CreditNoteCreateIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    cn = credit_service.create_credit_note(
        db,
        ctx=ctx,
        customer_id=body.customer_id,
        lines=[line.model_dump() for line in body.lines],
        reason=body.reason,
        invoice_id=body.invoice_id,
        currency=body.currency,
    )
    # Refresh to load relationships
    cn_full = credit_service.get_credit_note(db, ctx.organization_id, cn.id)
    return credit_service.serialize_credit_note(cn_full)


@router.get("/{credit_note_id}", response_model=CreditNoteOut, summary="Get credit note details")
def get_credit_note(
    credit_note_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    cn = credit_service.get_credit_note(db, ctx.organization_id, credit_note_id)
    return credit_service.serialize_credit_note(cn)


@router.post("/{credit_note_id}/apply", response_model=CreditNoteOut, summary="Apply credit note to an invoice")
def apply_credit_note(
    credit_note_id: str,
    body: CreditApplicationIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    credit_service.apply_credit_note_to_invoice(
        db,
        ctx=ctx,
        credit_note_id=credit_note_id,
        invoice_id=body.invoice_id,
        amount=body.amount,
    )
    cn = credit_service.get_credit_note(db, ctx.organization_id, credit_note_id)
    return credit_service.serialize_credit_note(cn)


@router.post("/{credit_note_id}/void", response_model=CreditNoteOut, summary="Void a credit note")
def void_credit_note(
    credit_note_id: str,
    reason: Optional[str] = Query(None),
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    credit_service.void_credit_note(
        db,
        ctx=ctx,
        credit_note_id=credit_note_id,
        reason=reason,
    )
    cn = credit_service.get_credit_note(db, ctx.organization_id, credit_note_id)
    return credit_service.serialize_credit_note(cn)

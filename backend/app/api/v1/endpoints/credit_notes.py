"""Credit notes endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.models.credits import CreditNoteStatus
from backend.app.schemas.credits import (
    CreditApplicationIn,
    CreditNoteCreateIn,
    CreditNoteListOut,
    CreditNoteOut,
)
from backend.app.services import credit_service

router = APIRouter()


@router.get("", response_model=CreditNoteListOut, summary="List credit notes")
def list_credit_notes(
    customer_id: Optional[str] = Query(None),
    status_: Optional[CreditNoteStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    notes = credit_service.list_credit_notes(
        db,
        organization_id=ctx.organization_id,
        customer_id=customer_id,
        status_=status_,
        limit=limit,
        offset=offset,
    )
    items = [credit_service.serialize_credit_note(cn) for cn in notes]
    return {"items": items, "total": len(items)}


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

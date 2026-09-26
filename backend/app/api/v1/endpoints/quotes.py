"""Quotes API (contract section 6). Mounted at /quotes."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.schemas.common_refs import PaginatedResponse
from backend.app.schemas.quotes import (
    InvoiceFromQuoteOut,
    QuoteConvertIn,
    QuoteCreate,
    QuoteDeclineIn,
    QuoteOut,
    QuoteUpdate,
)
from sqlalchemy import select
from backend.app.services import quote_service as svc
from backend.app.services.pagination import PageParams, page_params
from backend.app.services.quote_pdf import render_quote_pdf

router = APIRouter()


def _page_response(db: Session, ctx: CurrentContext, page) -> dict:
    return {
        "items": svc.serialize_quotes(db, ctx.organization_id, page.items),
        "total": page.total,
        "page": page.page,
        "page_size": page.page_size,
        "total_pages": page.total_pages,
    }


@router.get("", response_model=PaginatedResponse[QuoteOut], summary="List quotes")
def list_quotes(
    search: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_quotes(
        db, ctx, params, search=search, status=status_, customer_id=customer_id, date_from=date_from, date_to=date_to
    )
    return _page_response(db, ctx, page)


@router.post("", response_model=QuoteOut, status_code=status.HTTP_201_CREATED, summary="Create a draft quote")
def create_quote(
    body: QuoteCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    quote = svc.create_quote(db, ctx, body)
    return svc.serialize_quote_full(db, quote)


@router.get("/{quote_id}", response_model=QuoteOut, summary="Get a quote")
def get_quote(
    quote_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    quote = svc.get_quote(db, ctx, quote_id)
    return svc.serialize_quote_full(db, quote)


@router.get(
    "/{quote_id}/pdf",
    response_class=Response,
    summary="Download the quote PDF",
    responses={200: {"content": {"application/pdf": {}}}},
)
def quote_pdf(
    quote_id: str,
    template_id: Optional[str] = Query(None),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    quote = svc.get_quote(db, ctx, quote_id)
    template = None
    if template_id:
        from backend.app.models.customization import DocumentTemplate

        template = db.scalars(
            select(DocumentTemplate).where(
                DocumentTemplate.id == template_id,
                DocumentTemplate.organization_id == ctx.organization_id,
            )
        ).first()
    pdf = render_quote_pdf(quote, ctx.organization, template=template)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="Quote-{quote.quote_number}.pdf"'},
    )


@router.patch("/{quote_id}", response_model=QuoteOut, summary="Update a draft / pending quote")
def update_quote(
    quote_id: str,
    body: QuoteUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    quote = svc.update_quote(db, ctx, quote_id, body)
    return svc.serialize_quote_full(db, quote)


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, summary="Delete a draft quote")
def delete_quote(
    quote_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    svc.delete_quote(db, ctx, quote_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{quote_id}/send", response_model=QuoteOut, summary="Send the quote (or request discount approval)")
@router.post("/{quote_id}/submit", response_model=QuoteOut, summary="Submit quote for approval or sending")
def send_quote(
    quote_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    quote = svc.send_quote(db, ctx, quote_id)
    return svc.serialize_quote_full(db, quote)


@router.post("/{quote_id}/approve", response_model=QuoteOut, summary="Approve a pending quote's discount request")
def approve_quote(
    quote_id: str,
    body: QuoteDeclineIn = Body(default=QuoteDeclineIn()),
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Same guards as /approvals/{id}/approve: admin only, never the requester.
    quote = svc.approve_quote(db, ctx, quote_id, body.reason)
    return svc.serialize_quote_full(db, quote)


@router.post("/{quote_id}/reject", response_model=QuoteOut, summary="Reject a pending quote")
def reject_quote(
    quote_id: str,
    body: QuoteDeclineIn = Body(default=QuoteDeclineIn()),
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    quote = svc.reject_quote(db, ctx, quote_id, body.reason)
    return svc.serialize_quote_full(db, quote)


@router.post("/{quote_id}/mark-viewed", response_model=QuoteOut, summary="Mark quote as viewed")
def mark_viewed(
    quote_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    quote = svc.mark_viewed(db, ctx, quote_id)
    return svc.serialize_quote_full(db, quote)


@router.post("/{quote_id}/mark-accepted", response_model=QuoteOut, summary="Mark a sent quote as accepted")
@router.post("/{quote_id}/accept", response_model=QuoteOut, summary="Accept a quote")
def mark_accepted(
    quote_id: str,
    _body: dict = Body(default={}),
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    quote = svc.mark_accepted(db, ctx, quote_id)
    return svc.serialize_quote_full(db, quote)


@router.post("/{quote_id}/mark-declined", response_model=QuoteOut, summary="Mark a sent quote as declined")
@router.post("/{quote_id}/decline", response_model=QuoteOut, summary="Decline a quote")
def mark_declined(
    quote_id: str,
    body: QuoteDeclineIn = Body(default=QuoteDeclineIn()),
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    quote = svc.mark_declined(db, ctx, quote_id, body.reason)
    return svc.serialize_quote_full(db, quote)


@router.post(
    "/{quote_id}/convert",
    response_model=InvoiceFromQuoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Convert an accepted quote into a draft invoice",
)
@router.post(
    "/{quote_id}/convert-to-invoice",
    response_model=InvoiceFromQuoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Convert an accepted quote into a draft invoice",
)
def convert_quote(
    quote_id: str,
    body: QuoteConvertIn = Body(default=QuoteConvertIn()),
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    invoice = svc.convert_quote(db, ctx, quote_id, body)
    return svc.serialize_invoice(db, invoice)

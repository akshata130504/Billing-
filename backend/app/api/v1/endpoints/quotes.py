"""Quotes API (contract section 6). Mounted at /quotes."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_finance, require_viewer
from backend.app.schemas.common_refs import PaginatedResponse
from backend.app.schemas.quotes import (
    InvoiceFromQuoteOut,
    QuoteConvertIn,
    QuoteCreate,
    QuoteDeclineIn,
    QuoteOut,
    QuoteUpdate,
)
from backend.app.services import quote_service as svc
from backend.app.services.pagination import PageParams, page_params

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
def send_quote(
    quote_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    quote = svc.send_quote(db, ctx, quote_id)
    return svc.serialize_quote_full(db, quote)


@router.post("/{quote_id}/mark-accepted", response_model=QuoteOut, summary="Mark a sent quote as accepted")
def mark_accepted(
    quote_id: str,
    _body: dict = Body(default={}),
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    quote = svc.mark_accepted(db, ctx, quote_id)
    return svc.serialize_quote_full(db, quote)


@router.post("/{quote_id}/mark-declined", response_model=QuoteOut, summary="Mark a sent quote as declined")
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
def convert_quote(
    quote_id: str,
    body: QuoteConvertIn = Body(default=QuoteConvertIn()),
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    invoice = svc.convert_quote(db, ctx, quote_id, body)
    return svc.serialize_invoice(db, invoice)

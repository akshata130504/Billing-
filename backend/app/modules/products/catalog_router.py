"""Catalog Offerings and Price Books API endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.schemas.catalog_cpq import (
    OfferingCreate,
    OfferingOut,
    OfferingUpdate,
    PriceBookCreate,
    PriceBookOut,
    PriceBookUpdate,
)
from backend.app.schemas.common_refs import PaginatedResponse
from backend.app.modules.products import catalog_cpq_service as svc
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


# --- Offerings (Catalog) -------------------------------------------------------------

@router.get("/offerings", response_model=PaginatedResponse[OfferingOut], summary="List offerings")
def list_offerings(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    type_: Optional[str] = Query(None, alias="type"),
    category: Optional[str] = Query(None),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_offerings(db, ctx, params, search=search, is_active=is_active, offering_type=type_, category=category)
    items = [svc.serialize_offering(o) for o in page.items]
    return {"items": items, "total": page.total, "page": page.page, "page_size": page.page_size, "total_pages": page.total_pages}


@router.post("/offerings", response_model=OfferingOut, status_code=status.HTTP_201_CREATED, summary="Create offering")
def create_offering(
    body: OfferingCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    offering = svc.create_offering(db, ctx, body)
    return svc.serialize_offering(offering)


@router.get("/offerings/{offering_id}", response_model=OfferingOut, summary="Get offering")
def get_offering(
    offering_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    offering = svc.get_offering_or_404(db, ctx.organization_id, offering_id)
    return svc.serialize_offering(offering)


@router.patch("/offerings/{offering_id}", response_model=OfferingOut, summary="Update offering")
def update_offering(
    offering_id: str,
    body: OfferingUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    offering = svc.update_offering(db, ctx, offering_id, body)
    return svc.serialize_offering(offering)


@router.delete("/offerings/{offering_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, summary="Archive offering")
def archive_offering(
    offering_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    svc.archive_offering(db, ctx, offering_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/offerings/{offering_id}/unarchive", response_model=OfferingOut, summary="Unarchive offering")
def unarchive_offering(
    offering_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    offering = svc.unarchive_offering(db, ctx, offering_id)
    return svc.serialize_offering(offering)


# --- Price Books ---------------------------------------------------------------------

@router.get("/price-books", response_model=PaginatedResponse[PriceBookOut], summary="List price books")
def list_price_books(
    search: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_price_books(db, ctx, params, search=search, status=status_)
    items = [svc.serialize_price_book(pb) for pb in page.items]
    return {"items": items, "total": page.total, "page": page.page, "page_size": page.page_size, "total_pages": page.total_pages}


@router.post("/price-books", response_model=PriceBookOut, status_code=status.HTTP_201_CREATED, summary="Create price book")
def create_price_book(
    body: PriceBookCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    pb = svc.create_price_book(db, ctx, body)
    return svc.serialize_price_book(pb)


@router.get("/price-books/{pb_id}", response_model=PriceBookOut, summary="Get price book")
def get_price_book(
    pb_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    pb = svc.get_price_book_or_404(db, ctx.organization_id, pb_id)
    return svc.serialize_price_book(pb)


@router.patch("/price-books/{pb_id}", response_model=PriceBookOut, summary="Update price book")
def update_price_book(
    pb_id: str,
    body: PriceBookUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    pb = svc.update_price_book(db, ctx, pb_id, body)
    return svc.serialize_price_book(pb)

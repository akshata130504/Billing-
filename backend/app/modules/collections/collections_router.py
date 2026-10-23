"""/collections — outstanding receivables and collection activities."""
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_finance, require_viewer
from backend.app.schemas.collections import (
    CollectionActivityIn,
    CollectionActivityOut,
    CollectionInvoiceDetailOut,
    CollectionInvoiceOut,
    CollectionStatusUpdateIn,
    CollectionsDashboardOut,
    PromiseToPayIn,
    PromiseToPayOut,
    PromiseToPayUpdateIn,
)
from backend.app.schemas.common import PaginatedResponse
from backend.app.schemas.invoices import InvoiceOut
from backend.app.modules.collections import service as collection_service
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("/dashboard", response_model=CollectionsDashboardOut, summary="Collections dashboard")
def get_dashboard(
    currency: Optional[str] = Query(None, pattern="^[A-Za-z]{3}$", description="Default: the organization's base currency"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return collection_service.dashboard(db, ctx.organization_id, currency)


@router.get("/invoices", response_model=PaginatedResponse[CollectionInvoiceOut], summary="List invoices in collections")
def list_invoices(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    aging_bucket: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    amount_min: Optional[Decimal] = Query(None),
    amount_max: Optional[Decimal] = Query(None),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return collection_service.list_invoices(
        db,
        ctx.organization_id,
        params,
        search=search,
        status=status,
        aging_bucket_filter=aging_bucket,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
    )


@router.get("/invoices/{invoice_id}", response_model=CollectionInvoiceDetailOut, summary="Get a collections invoice")
def get_invoice(
    invoice_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return collection_service.get_invoice_detail(db, ctx.organization_id, invoice_id)


@router.get("/invoices/{invoice_id}/activities", response_model=list[CollectionActivityOut], summary="List activities")
def list_activities(
    invoice_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    detail = collection_service.get_invoice_detail(db, ctx.organization_id, invoice_id)
    return detail["activities"]


@router.post("/invoices/{invoice_id}/activities", response_model=CollectionActivityOut, summary="Record an activity")
def add_activity(
    invoice_id: str,
    body: CollectionActivityIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    activity = collection_service.record_activity(db, ctx, invoice_id, body)
    return collection_service.serialize_activity(activity)


@router.post("/invoices/{invoice_id}/promises", response_model=PromiseToPayOut, summary="Add a promise to pay")
def add_promise(
    invoice_id: str,
    body: PromiseToPayIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    promise = collection_service.create_promise(db, ctx, invoice_id, body)
    return collection_service.serialize_promise(promise)


@router.patch("/promises/{promise_id}", response_model=PromiseToPayOut, summary="Update a promise to pay's status")
def update_promise(
    promise_id: str,
    body: PromiseToPayUpdateIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    promise = collection_service.update_promise_status(db, ctx, promise_id, body.status)
    return collection_service.serialize_promise(promise)


@router.patch("/invoices/{invoice_id}/status", response_model=CollectionInvoiceDetailOut, summary="Set collection status")
def update_status(
    invoice_id: str,
    body: CollectionStatusUpdateIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    collection_service.set_manual_status(db, ctx, invoice_id, body.status, body.note)
    return collection_service.get_invoice_detail(db, ctx.organization_id, invoice_id)


@router.post("/invoices/{invoice_id}/send-reminder", response_model=InvoiceOut, summary="Send a payment reminder")
def send_reminder(
    invoice_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    from backend.app.services import invoice_service

    invoice = collection_service.send_reminder(db, ctx, invoice_id)
    return invoice_service.serialize_invoice(invoice)

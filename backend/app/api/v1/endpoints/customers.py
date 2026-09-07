"""Customers API (contract section 4). Mounted at /customers."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.schemas.common_refs import PaginatedResponse
from backend.app.schemas.customers import (
    ContactIn,
    CustomerCreate,
    CustomerInvoiceRow,
    CustomerOut,
    CustomerPaymentRow,
    CustomerSubscriptionRow,
    CustomerUpdate,
)
from backend.app.services import customer_service as svc
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("", response_model=PaginatedResponse[CustomerOut], summary="List customers")
def list_customers(
    search: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_customers(db, ctx, params, search=search, status=status_)
    return page.to_response(svc.serialize_customer)


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED, summary="Create a customer")
def create_customer(
    body: CustomerCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    customer = svc.create_customer(db, ctx, body)
    return svc.serialize_customer(customer)


@router.get("/{customer_id}", response_model=CustomerOut, summary="Get a customer with stats")
def get_customer(
    customer_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    customer = svc.get_customer_or_404(db, ctx.organization_id, customer_id)
    stats = svc.customer_stats(db, ctx.organization_id, customer.id)
    return svc.serialize_customer(customer, stats=stats)


@router.patch("/{customer_id}", response_model=CustomerOut, summary="Update a customer")
def update_customer(
    customer_id: str,
    body: CustomerUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    customer = svc.update_customer(db, ctx, customer_id, body)
    return svc.serialize_customer(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, summary="Delete a customer")
def delete_customer(
    customer_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    svc.delete_customer(db, ctx, customer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{customer_id}/contacts", response_model=CustomerOut, summary="Replace the customer's contacts")
def set_contacts(
    customer_id: str,
    body: List[ContactIn],
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    customer = svc.set_contacts(db, ctx, customer_id, body)
    return svc.serialize_customer(customer)


@router.get("/{customer_id}/invoices", response_model=PaginatedResponse[CustomerInvoiceRow], summary="Customer invoices")
def customer_invoices(
    customer_id: str,
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_customer_invoices(db, ctx, customer_id, params)
    return page.to_response(svc.serialize_invoice_row)


@router.get("/{customer_id}/payments", response_model=PaginatedResponse[CustomerPaymentRow], summary="Customer payments")
def customer_payments(
    customer_id: str,
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_customer_payments(db, ctx, customer_id, params)
    return page.to_response(svc.serialize_payment_row)


@router.get(
    "/{customer_id}/subscriptions",
    response_model=PaginatedResponse[CustomerSubscriptionRow],
    summary="Customer subscriptions",
)
def customer_subscriptions(
    customer_id: str,
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_customer_subscriptions(db, ctx, customer_id, params)
    return page.to_response(svc.serialize_subscription_row)

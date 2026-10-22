"""/payments (contract §9). The reconciliation summary route is declared before /{payment_id}."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.schemas.common import PaginatedResponse
from backend.app.schemas.payments import (
    AllocationIn,
    AllocationsPut,
    PaymentCreate,
    PaymentOut,
    PaymentsSummary,
    PaymentUpdate,
    ReconciliationSummary,
    RefundIn,
)
from backend.app.services import idempotency_service
from backend.app.modules.payments import service as payment_service
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("", response_model=PaginatedResponse[PaymentOut], summary="List payments")
def list_payments(
    search: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    method: Optional[str] = Query(None),
    gateway: Optional[str] = Query(None),
    reconciliation_status: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = payment_service.list_payments(
        db,
        ctx.organization_id,
        params,
        search=search,
        status=status_,
        method=method,
        gateway=gateway,
        reconciliation_status=reconciliation_status,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
    )
    return page.to_response(payment_service.serialize_payment)


def _payment_out(db: Session, payment) -> dict:
    """A saved payment plus non-blocking warnings (e.g. a reference already used elsewhere)."""
    out = PaymentOut.model_validate(payment_service.serialize_payment(payment))
    out.warnings = payment_service.duplicate_reference_warnings(db, payment)
    return out.model_dump(mode="json")


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED, summary="Record a payment")
def create_payment(
    body: PaymentCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=128),
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    """Send an optional `Idempotency-Key` header to make retries safe: a repeated key
    with the same body returns the original payment instead of recording another."""
    status_code, out = idempotency_service.run_idempotent(
        db,
        organization_id=ctx.organization_id,
        key=idempotency_key,
        request_path="/payments",
        request_method="POST",
        params={"path": "/payments", "body": body.model_dump(mode="json")},
        handler=lambda: _payment_out(db, payment_service.create_payment(db, ctx, body)),
        status_code=status.HTTP_201_CREATED,
    )
    return JSONResponse(status_code=status_code, content=out)


# Declared BEFORE /{payment_id} so "summary" is never treated as an id.
@router.get("/summary", response_model=PaymentsSummary, summary="Money totals for the filtered payments")
def payments_summary(
    search: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    method: Optional[str] = Query(None),
    gateway: Optional[str] = Query(None),
    reconciliation_status: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return payment_service.payments_summary(
        db,
        ctx.organization_id,
        search=search,
        status=status_,
        method=method,
        gateway=gateway,
        reconciliation_status=reconciliation_status,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
    )


# Declared BEFORE /{payment_id} so "reconciliation" is never treated as an id.
@router.get("/reconciliation/summary", response_model=ReconciliationSummary, summary="Reconciliation status counts")
def reconciliation_summary(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return payment_service.reconciliation_summary(db, ctx.organization_id)


@router.get("/{payment_id}", response_model=PaymentOut, summary="Get a payment")
def get_payment(
    payment_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return payment_service.serialize_payment(payment_service.get_payment(db, ctx.organization_id, payment_id))


@router.patch("/{payment_id}", response_model=PaymentOut, summary="Edit payment reference/notes")
def update_payment(
    payment_id: str,
    body: PaymentUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    payment = payment_service.get_payment(db, ctx.organization_id, payment_id)
    return _payment_out(db, payment_service.update_payment(db, ctx, payment, body))


@router.put("/{payment_id}/allocations", response_model=PaymentOut, summary="Replace the payment's invoice allocations")
def set_allocations(
    payment_id: str,
    body: AllocationsPut,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    payment = payment_service.get_payment(db, ctx.organization_id, payment_id)
    return payment_service.serialize_payment(payment_service.set_allocations(db, ctx, payment, body.allocations))


@router.post(
    "/{payment_id}/allocations/add",
    response_model=PaymentOut,
    summary="Allocate part of the payment's unallocated amount to an invoice (existing allocations are kept)",
)
def add_allocation(
    payment_id: str,
    body: AllocationIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    payment = payment_service.get_payment(db, ctx.organization_id, payment_id)
    return payment_service.serialize_payment(payment_service.add_allocation(db, ctx, payment, body))


@router.post("/{payment_id}/refund", response_model=PaymentOut, summary="Refund (part of) a payment")
def refund_payment(
    payment_id: str,
    body: RefundIn,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payment = payment_service.get_payment(db, ctx.organization_id, payment_id)
    return payment_service.serialize_payment(payment_service.refund_payment(db, ctx, payment, body.amount, body.reason))

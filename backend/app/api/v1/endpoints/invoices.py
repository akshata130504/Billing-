"""/invoices (contract §8)."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import Response as RawResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_finance, require_viewer
from backend.app.models import Payment, PaymentAllocation
from backend.app.schemas.common import PaginatedResponse
from backend.app.schemas.invoices import (
    InvoiceCreate,
    InvoiceOut,
    InvoiceSummaryKPIs,
    InvoiceUpdate,
    InvoiceVoidIn,
    RecordPaymentIn,
)
from backend.app.schemas.payments import PaymentOut
from backend.app.services import invoice_service, payment_service
from backend.app.services.invoice_pdf import render_invoice_pdf
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("", response_model=PaginatedResponse[InvoiceOut], summary="List invoices")
def list_invoices(
    search: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    overdue_only: bool = Query(False),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = invoice_service.list_invoices(
        db,
        ctx.organization_id,
        params,
        search=search,
        status=status_,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        overdue_only=overdue_only,
    )
    return page.to_response(lambda inv: invoice_service.serialize_invoice(inv, include_payments=False))


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED, summary="Create a draft invoice")
def create_invoice(
    body: InvoiceCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    invoice = invoice_service.create_invoice(db, ctx, body)
    return invoice_service.serialize_invoice(invoice)


@router.get("/summary", response_model=InvoiceSummaryKPIs, summary="Get invoice summary KPIs and status counts")
def get_invoices_summary(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return invoice_service.get_invoices_summary(db, ctx.organization_id)


@router.get("/{invoice_id}", response_model=InvoiceOut, summary="Get an invoice")
def get_invoice(
    invoice_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return invoice_service.serialize_invoice(invoice_service.get_invoice(db, ctx.organization_id, invoice_id))


@router.patch("/{invoice_id}", response_model=InvoiceOut, summary="Edit a draft invoice")
def update_invoice(
    invoice_id: str,
    body: InvoiceUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    invoice = invoice_service.get_invoice(db, ctx.organization_id, invoice_id)
    return invoice_service.serialize_invoice(invoice_service.update_invoice(db, ctx, invoice, body))


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, summary="Delete a draft invoice")
def delete_invoice(
    invoice_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    invoice = invoice_service.get_invoice(db, ctx.organization_id, invoice_id)
    invoice_service.delete_invoice(db, ctx, invoice)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{invoice_id}/send", response_model=InvoiceOut, summary="Issue the invoice and email the customer")
def send_invoice(
    invoice_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    invoice = invoice_service.get_invoice(db, ctx.organization_id, invoice_id)
    return invoice_service.serialize_invoice(invoice_service.send_invoice(db, ctx, invoice))


@router.post("/{invoice_id}/send-reminder", response_model=InvoiceOut, summary="Send a payment reminder")
def send_reminder(
    invoice_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    invoice = invoice_service.get_invoice(db, ctx.organization_id, invoice_id)
    return invoice_service.serialize_invoice(invoice_service.send_reminder(db, invoice, ctx=ctx))


@router.post("/{invoice_id}/void", response_model=InvoiceOut, summary="Void an unpaid invoice")
def void_invoice(
    invoice_id: str,
    body: InvoiceVoidIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    invoice = invoice_service.get_invoice(db, ctx.organization_id, invoice_id)
    return invoice_service.serialize_invoice(invoice_service.void_invoice(db, ctx, invoice, body.reason))


@router.post(
    "/{invoice_id}/record-payment",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record an offline payment against the invoice",
)
def record_payment(
    invoice_id: str,
    body: RecordPaymentIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    invoice = invoice_service.get_invoice(db, ctx.organization_id, invoice_id)
    payment = payment_service.record_invoice_payment(db, ctx, invoice, body)
    return payment_service.serialize_payment(payment)


@router.get(
    "/{invoice_id}/payments",
    response_model=List[PaymentOut],
    summary="List payments allocated to this invoice",
)
def list_invoice_payments(
    invoice_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    invoice = invoice_service.get_invoice(db, ctx.organization_id, invoice_id)
    allocations = db.scalars(
        select(PaymentAllocation).where(
            PaymentAllocation.organization_id == ctx.organization_id,
            PaymentAllocation.invoice_id == invoice.id,
        )
    ).all()
    payment_ids = [a.payment_id for a in allocations]
    if not payment_ids:
        return []
    payments = db.scalars(
        select(Payment).where(
            Payment.organization_id == ctx.organization_id,
            Payment.id.in_(payment_ids),
        )
    ).all()
    return [payment_service.serialize_payment(p) for p in payments]


@router.get("/{invoice_id}/pdf", response_class=RawResponse, summary="Download the invoice PDF", responses={200: {"content": {"application/pdf": {}}}})
def invoice_pdf(
    invoice_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    invoice = invoice_service.get_invoice(db, ctx.organization_id, invoice_id)
    pdf = render_invoice_pdf(invoice, ctx.organization)
    return RawResponse(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.invoice_number}.pdf"'},
    )

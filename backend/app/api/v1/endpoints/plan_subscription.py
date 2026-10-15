"""The organization's paid Rooman plan. Mounted at /plan-subscription.

    GET  /receipts                 Finance, Admin, Owner: the organization's payment receipts (newest first, pages)
    GET  /receipts/{id}            one receipt (another organization's id answers 404)
    GET  /receipts/{id}/pdf        the receipt as a PDF - a payment receipt, not a tax invoice
    POST /cancel   Owner only. body {"mode": "at_period_end" | "immediately"}
                   at_period_end: paid access continues to the end of the current period, then read-only.
                   immediately:   access ends now (read-only at once); no automatic refund.
                   Applied only after Razorpay confirms (services/platform_cancellation_service.py).

Not offered, because Razorpay has no API for it: undoing a scheduled cancellation, or restarting a cancelled
plan (choose a plan again instead, once the current paid period has ended).
"""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response as RawResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_tenant_user
from backend.app.core.exceptions import NotFoundError
from backend.app.core.rate_limit import limiter, public_action_rate_limit
from backend.app.models import MemberRole
from backend.app.schemas.plan_subscription import CancelPlanIn, CancelPlanOut, PaymentReceiptOut, PaymentReceiptPageOut
from backend.app.services import platform_cancellation_service, platform_receipt_service as receipts

router = APIRouter()

# Payment receipts for Rooman plan payments: Finance, Admin and Owner of the organization (its own receipts only).
receipt_reader = require_tenant_user(MemberRole.FINANCE)


@router.get("/receipts", response_model=PaymentReceiptPageOut, summary="Payment receipts for the organization's Rooman plan")
def list_receipts(page: int = Query(default=1, ge=1, le=10_000), page_size: int = Query(default=25, ge=1, le=100),
                  ctx: CurrentContext = Depends(receipt_reader), db: Session = Depends(get_db)):
    return receipts.list_receipts(db, ctx.organization_id, page=page, page_size=page_size)


def _receipt(db: Session, ctx: CurrentContext, receipt_id: str):
    row = receipts.get_receipt(db, ctx.organization_id, receipt_id)
    if row is None:
        raise NotFoundError("Receipt not found.")
    return row


@router.get("/receipts/{receipt_id}", response_model=PaymentReceiptOut, summary="One payment receipt")
def get_receipt(receipt_id: str, ctx: CurrentContext = Depends(receipt_reader), db: Session = Depends(get_db)):
    return receipts.receipt_out(_receipt(db, ctx, receipt_id))


@router.get("/receipts/{receipt_id}/pdf", response_class=RawResponse, summary="Download a payment receipt (PDF)",
            responses={200: {"content": {"application/pdf": {}}}})
def receipt_pdf(receipt_id: str, ctx: CurrentContext = Depends(receipt_reader), db: Session = Depends(get_db)):
    from backend.app.services.platform_receipt_pdf import render_receipt_pdf

    row = _receipt(db, ctx, receipt_id)
    return RawResponse(content=render_receipt_pdf(row), media_type="application/pdf",
                       headers={"Content-Disposition": f'attachment; filename="{row.receipt_number}.pdf"'})


@router.post("/cancel", response_model=CancelPlanOut, summary="Cancel the organization's Rooman plan (Owner)")
@limiter.limit(public_action_rate_limit)
def cancel_plan(request: Request, body: CancelPlanIn,
                ctx: CurrentContext = Depends(require_tenant_user(MemberRole.OWNER)),
                db: Session = Depends(get_db)):
    return CancelPlanOut(**platform_cancellation_service.cancel_subscription(
        db, ctx.organization_id, body.mode, requested_by=ctx.user.id))

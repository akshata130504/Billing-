"""/public/autopay - the customer's UPI AutoPay / e-mandate authorisation page (no authentication; the
opaque one-time token from the AutoPay link is the credential, stored only as its SHA-256)."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.rate_limit import limiter, public_action_rate_limit, public_rate_limit
from backend.app.schemas.autopay import PublicAutopayConfirmIn, PublicAutopayOut
from backend.app.services import autopay_service, org_lifecycle

router = APIRouter()


@router.get("/{token}", response_model=PublicAutopayOut, summary="AutoPay authorisation view")
@limiter.limit(public_rate_limit)
def public_autopay(request: Request, token: str, db: Session = Depends(get_db)):
    row = autopay_service.get_by_token(db, token)
    org_lifecycle.assert_customer_pages_visible(db, row.organization_id)
    return autopay_service.public_view(db, row)


@router.post("/{token}/confirm", response_model=PublicAutopayOut, summary="Verify the Checkout authorisation")
@limiter.limit(public_action_rate_limit)
def confirm_autopay(request: Request, token: str, body: PublicAutopayConfirmIn, db: Session = Depends(get_db)):
    row = autopay_service.get_by_token(db, token)
    org_lifecycle.assert_payment_collection_allowed(db, row.organization_id)
    row = autopay_service.confirm_authorization(
        db, row, payment_id=body.razorpay_payment_id, subscription_id=body.razorpay_subscription_id,
        signature=body.razorpay_signature,
    )
    return autopay_service.public_view(db, row)

"""Start buying a Rooman plan. Mounted at /subscription-checkout.

    GET  /sandbox-plans
                   Any member: the sandbox TEST plans, only while the sandbox is allowed
                   (platform_razorpay.sandbox_readiness: PLATFORM_SANDBOX_PLANS_ENABLED, a local environment
                   and Test Mode keys); otherwise an empty list. Never part of the public catalog.
    POST /         Owner only (a member of the organization, never a platform grant)
                   body {"plan_code": "..."} -> what Razorpay Standard Checkout needs
    POST /verify   Owner only: the Checkout result {razorpay_payment_id, razorpay_subscription_id,
                   razorpay_signature}. Verified on the server (services/platform_payment_service.py); the
                   plan starts only when Razorpay confirms the first payment, otherwise "pending".

Reachable while the free trial has ended (api/deps.py exempts it from the read-only mode, nothing
else). Starting a checkout pays, grants and unlocks nothing. The browser's Checkout result is not proof
of payment: /verify checks its signature and asks Razorpay; the platform webhook does the same when the
browser never comes back (api/v1/endpoints/platform_webhooks.py).
"""
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_tenant_user
from backend.app.api.v1.endpoints.platform_plans import plan_body
from backend.app.core.plan_catalog import catalog
from backend.app.core.rate_limit import limiter, public_action_rate_limit
from backend.app.models import MemberRole
from backend.app.schemas.plan_catalog import PublicCatalogOut
from backend.app.schemas.subscription_checkout import CheckoutStartIn, CheckoutStartOut, CheckoutVerifyIn, CheckoutVerifyOut
from backend.app.services import platform_checkout_service, platform_payment_service, platform_razorpay

router = APIRouter()


@router.get("/sandbox-plans", response_model=PublicCatalogOut, summary="Sandbox TEST plans (local Test Mode only)")
def sandbox_plans(response: Response, ctx: CurrentContext = Depends(require_tenant_user(MemberRole.VIEWER))):
    response.headers["Cache-Control"] = "no-store"  # follows the sandbox switch immediately
    cat = catalog()
    plans = cat.sandbox_plans() if platform_razorpay.sandbox_readiness() is None else ()
    return {"catalog_version": cat.version, "plans": [plan_body(p) for p in plans]}


@router.post("", response_model=CheckoutStartOut, status_code=status.HTTP_201_CREATED,
             summary="Start a Rooman plan checkout (Owner)")
@limiter.limit(public_action_rate_limit)
def start_checkout(request: Request, body: CheckoutStartIn,
                   ctx: CurrentContext = Depends(require_tenant_user(MemberRole.OWNER)),
                   db: Session = Depends(get_db)):
    return CheckoutStartOut(**platform_checkout_service.start_checkout(db, ctx, body.plan_code))


@router.post("/verify", response_model=CheckoutVerifyOut, summary="Verify a Rooman plan Checkout result (Owner)")
@limiter.limit(public_action_rate_limit)
def verify_checkout(request: Request, body: CheckoutVerifyIn,
                    ctx: CurrentContext = Depends(require_tenant_user(MemberRole.OWNER)),
                    db: Session = Depends(get_db)):
    return CheckoutVerifyOut(**platform_payment_service.verify_checkout_callback(
        db, ctx.organization_id, payment_id=body.razorpay_payment_id,
        subscription_id=body.razorpay_subscription_id, signature=body.razorpay_signature))

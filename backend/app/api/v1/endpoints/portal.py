"""Customer Portal endpoints: settings, customer authentication, self-service dashboard, and actions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import Response as RawResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_viewer
from backend.app.core.exceptions import UnauthorizedError, ValidationAppError
from backend.app.models.invoices import Invoice
from backend.app.models.identity import Organization
from backend.app.models.payments import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    PaymentGateway,
)
from backend.app.models.portal import (
    CustomerPortalSettings,
    CustomerPortalUser,
)
from backend.app.models.subscriptions import Subscription
from backend.app.schemas.portal import (
    CustomerPortalSettingsOut,
    CustomerPortalSettingsUpdate,
    PortalAuthOut,
    PortalDashboardOut,
    PortalLoginIn,
    PortalSignupIn,
    PortalUserOut,
)
from backend.app.services import (
    customer_portal_service,
    subscription_service,
    trial_service,
)
from backend.app.services.invoice_pdf import render_invoice_pdf

router = APIRouter()


def get_current_portal_user(
    x_portal_token: Optional[str] = Header(None, alias="X-Portal-Token"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> CustomerPortalUser:
    """Dependency for authenticating customer portal requests via portal session token."""
    token = x_portal_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Portal authentication token required via X-Portal-Token or Authorization header.",
        )

    try:
        return customer_portal_service.authenticate_portal_session(db, token)
    except UnauthorizedError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


# --- Admin Portal Settings Endpoints ---


@router.get("/settings", response_model=CustomerPortalSettingsOut, summary="Get customer portal settings")
def get_portal_settings(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    settings = customer_portal_service.get_or_create_portal_settings(db, ctx.organization_id)
    return CustomerPortalSettingsOut.model_validate(settings)


@router.patch("/settings", response_model=CustomerPortalSettingsOut, summary="Update customer portal settings")
def update_portal_settings(
    body: CustomerPortalSettingsUpdate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    settings = customer_portal_service.update_portal_settings(db, ctx.organization_id, body)
    db.commit()
    return CustomerPortalSettingsOut.model_validate(settings)


# --- Customer Portal Auth Endpoints ---


@router.post("/auth/signup", response_model=PortalUserOut, status_code=status.HTTP_201_CREATED, summary="Customer portal self sign-up")
def portal_signup(
    body: PortalSignupIn,
    db: Session = Depends(get_db),
):
    user = customer_portal_service.portal_signup(db, body)
    db.commit()
    return PortalUserOut.model_validate(user)


@router.post("/auth/login", response_model=PortalAuthOut, summary="Customer portal login")
def portal_login(
    body: PortalLoginIn,
    db: Session = Depends(get_db),
):
    token, user = customer_portal_service.portal_login(db, body)
    db.commit()
    return PortalAuthOut(
        token=token,
        expires_at=user.sessions[-1].expires_at if user.sessions else None,
        user=PortalUserOut.model_validate(user),
        customer_display_name=user.customer.display_name if user.customer else "",
    )


# --- Customer Self-Service Endpoints ---


@router.get("/dashboard", response_model=PortalDashboardOut, summary="Customer portal dashboard summary")
def get_portal_dashboard(
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
    return customer_portal_service.get_customer_dashboard(db, user)


@router.get("/invoices", response_model=List[Dict[str, Any]], summary="Customer portal invoice list")
def list_portal_invoices(
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
    invoices = list(
        db.scalars(
            select(Invoice)
            .where(
                Invoice.organization_id == user.organization_id,
                Invoice.customer_id == user.customer_id,
            )
            .order_by(desc(Invoice.issue_date))
        ).all()
    )
    return [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "issue_date": str(inv.issue_date),
            "due_date": str(inv.due_date),
            "total": str(inv.total),
            "amount_paid": str(inv.amount_paid),
            "amount_due": str(inv.amount_due),
            "status": inv.status.value,
            "public_token": inv.public_token,
        }
        for inv in invoices
    ]


@router.get("/invoices/{invoice_id}/pdf", response_class=RawResponse, summary="Download invoice PDF from customer portal")
def download_portal_invoice_pdf(
    invoice_id: str,
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
    """Secure authenticated PDF download scoped strictly to user tenant and customer."""
    invoice = db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.items), selectinload(Invoice.customer))
        .where(
            Invoice.id == invoice_id,
            Invoice.organization_id == user.organization_id,
            Invoice.customer_id == user.customer_id,
        )
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    org = db.get(Organization, user.organization_id)
    pdf = render_invoice_pdf(invoice, org)
    return RawResponse(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'},
    )


@router.get("/invoices/{invoice_id}/signed-url", summary="Generate signed short-lived invoice download URL")
def get_signed_invoice_download_url(
    invoice_id: str,
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
    """Generates a cryptographic HMAC-SHA256 signed temporary download token."""
    invoice = db.scalars(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.organization_id == user.organization_id,
            Invoice.customer_id == user.customer_id,
        )
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    token = customer_portal_service.generate_signed_document_token(
        organization_id=user.organization_id,
        customer_id=user.customer_id,
        invoice_id=invoice.id,
        expires_in_seconds=300,
    )
    return {"token": token, "expires_in_seconds": 300}


@router.get("/invoices/signed-download", response_class=RawResponse, summary="Download invoice via signed token")
def download_signed_invoice_pdf(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Public signed download endpoint validating HMAC signature and expiry without session headers."""
    try:
        org_id, cust_id, inv_id = customer_portal_service.verify_signed_document_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    invoice = db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.items), selectinload(Invoice.customer))
        .where(
            Invoice.id == inv_id,
            Invoice.organization_id == org_id,
            Invoice.customer_id == cust_id,
        )
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    org = db.get(Organization, org_id)
    pdf = render_invoice_pdf(invoice, org)
    return RawResponse(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'},
    )


@router.get("/subscriptions", response_model=List[Dict[str, Any]], summary="Customer portal subscription list")
def list_portal_subscriptions(
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
    subs = list(
        db.scalars(
            select(Subscription)
            .options(joinedload(Subscription.plan))
            .where(
                Subscription.organization_id == user.organization_id,
                Subscription.customer_id == user.customer_id,
            )
            .order_by(desc(Subscription.created_at))
        ).all()
    )
    return [
        {
            "id": s.id,
            "subscription_number": s.subscription_number,
            "plan_name": s.plan.name if s.plan else "",
            "quantity": s.quantity,
            "status": s.status.value,
            "current_period_start": str(s.current_period_start),
            "current_period_end": str(s.current_period_end),
            "trial_end": str(s.trial_end) if s.trial_end else None,
        }
        for s in subs
    ]


@router.get("/payment-methods", response_model=List[Dict[str, Any]], summary="Customer portal saved payment methods")
def list_portal_payment_methods(
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
    methods = list(
        db.scalars(
            select(CustomerPaymentMethod).where(
                CustomerPaymentMethod.organization_id == user.organization_id,
                CustomerPaymentMethod.customer_id == user.customer_id,
                CustomerPaymentMethod.status == CustomerPaymentMethodStatus.ACTIVE,
            )
        ).all()
    )
    return [
        {
            "id": m.id,
            "type": m.type,
            "card_brand": m.card_brand,
            "last4": m.last4,
            "is_default": m.is_default,
        }
        for m in methods
    ]


@router.post("/subscriptions/{subscription_id}/trial/extend", summary="Customer portal trial self-service extension")
def customer_portal_extend_trial(
    subscription_id: str,
    days: Optional[int] = Query(None, ge=1, le=30),
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
    sub = db.scalars(
        select(Subscription).where(
            Subscription.id == subscription_id,
            Subscription.organization_id == user.organization_id,
            Subscription.customer_id == user.customer_id,
        )
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found for this customer.")

    tp = trial_service.extend_trial(
        db,
        sub,
        days=days,
        is_customer_initiated=True,
    )
    db.commit()
    return {
        "status": "success",
        "message": "Trial extended successfully.",
        "trial_end": str(sub.trial_end),
        "extension_count": tp.extension_count,
        "max_extensions_allowed": tp.max_extensions_allowed,
    }


@router.post("/subscriptions/{subscription_id}/trial/convert", summary="Customer portal trial early conversion")
def customer_portal_convert_trial(
    subscription_id: str,
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
    sub = db.scalars(
        select(Subscription).where(
            Subscription.id == subscription_id,
            Subscription.organization_id == user.organization_id,
            Subscription.customer_id == user.customer_id,
        )
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found for this customer.")

    sub, invoice, attempt, succeeded, message = trial_service.convert_trial_to_live(
        db,
        sub,
        actor_label=user.email,
    )
    db.commit()
    return {
        "status": sub.status.value,
        "message": message,
        "invoice_id": invoice.id if invoice else None,
        "payment_succeeded": succeeded,
    }

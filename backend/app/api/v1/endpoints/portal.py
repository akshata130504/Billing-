"""Customer Portal endpoints: settings, customer authentication, self-service dashboard, and actions."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import Response as RawResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_viewer
from backend.app.core.exceptions import UnauthorizedError, ValidationAppError
from backend.app.core.rate_limit import auth_rate_limit, limiter, public_rate_limit
from backend.app.models.customers import Customer
from backend.app.models.invoices import Invoice
from backend.app.models.identity import Organization
from backend.app.models.payments import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    Payment,
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
    PortalActivateIn,
    PortalAuthOut,
    PortalDashboardOut,
    PortalInvitationValidateOut,
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


@router.post("/auth/signup", status_code=status.HTTP_403_FORBIDDEN, summary="Customer portal self sign-up (disabled)")
@limiter.limit(auth_rate_limit)
def portal_signup(
    request: Request,
    body: PortalSignupIn,
    db: Session = Depends(get_db),
):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public customer sign-up is disabled. Access to the Customer Portal is by invitation only.",
    )


@router.get("/auth/invitation", response_model=PortalInvitationValidateOut, summary="Validate portal activation invitation token")
@limiter.limit(public_rate_limit)
def validate_portal_invitation(
    request: Request,
    token: str = Query(..., description="Activation invitation token"),
    db: Session = Depends(get_db),
):
    return customer_portal_service.validate_portal_invitation_token(db, token)


@router.post("/auth/activate", response_model=PortalAuthOut, summary="Activate customer portal account and set password")
@limiter.limit(auth_rate_limit)
def activate_portal_account(
    request: Request,
    body: PortalActivateIn,
    db: Session = Depends(get_db),
):
    token, user = customer_portal_service.activate_portal_account(
        db,
        raw_token=body.token,
        password=body.password,
        display_name=body.display_name,
    )
    db.commit()
    return PortalAuthOut(
        token=token,
        expires_at=user.sessions[-1].expires_at if user.sessions else None,
        user=PortalUserOut.model_validate(user),
        customer_display_name=user.customer.display_name if user.customer else "",
    )


@router.post("/auth/login", response_model=PortalAuthOut, summary="Customer portal login")
@limiter.limit(auth_rate_limit)
def portal_login(
    request: Request,
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


@router.post("/auth/logout", summary="Customer portal logout")
def portal_logout(
    x_portal_token: Optional[str] = Header(None, alias="X-Portal-Token"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    token = x_portal_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    if token:
        customer_portal_service.portal_logout(db, token)
        db.commit()
    return {"status": "success", "message": "Logged out successfully."}


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


@router.get("/invoices/signed-download", response_class=RawResponse, summary="Download invoice via signed token")
@limiter.limit(public_rate_limit)
def download_signed_invoice_pdf(
    request: Request,
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


@router.get("/invoices/{invoice_id}", response_model=Dict[str, Any], summary="Customer portal invoice detail")
def get_portal_invoice(
    invoice_id: str,
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
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

    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "issue_date": str(invoice.issue_date),
        "due_date": str(invoice.due_date),
        "status": invoice.status.value,
        "currency": invoice.currency,
        "subtotal": str(invoice.subtotal),
        "tax_amount": str(invoice.tax_amount),
        "total": str(invoice.total),
        "amount_paid": str(invoice.amount_paid),
        "amount_due": str(invoice.amount_due),
        "public_token": invoice.public_token,
        "notes": invoice.notes,
        "terms": invoice.terms,
        "place_of_supply_name": invoice.place_of_supply_name,
        "customer_gstin": invoice.customer_gstin,
        "items": [
            {
                "id": item.id,
                "description": item.description,
                "quantity": float(item.quantity),
                "unit_price": float(item.unit_price),
                "amount": float(item.amount),
                "tax_rate_pct": float(item.tax_rate_pct),
                "hsn_sac_code": item.hsn_sac_code,
            }
            for item in (invoice.items or [])
        ],
    }


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


@router.get("/payments", response_model=List[Dict[str, Any]], summary="Customer portal payment history")
def list_portal_payments(
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
    payments = list(
        db.scalars(
            select(Payment)
            .where(
                Payment.organization_id == user.organization_id,
                Payment.customer_id == user.customer_id,
            )
            .order_by(desc(Payment.created_at))
        ).all()
    )
    return [
        {
            "id": p.id,
            "payment_number": p.payment_number,
            "amount": str(p.amount),
            "currency": p.currency,
            "method": p.method.value if hasattr(p.method, "value") else str(p.method),
            "gateway": p.gateway.value if hasattr(p.gateway, "value") else str(p.gateway),
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "reconciliation_status": p.reconciliation_status.value if hasattr(p.reconciliation_status, "value") else str(p.reconciliation_status),
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "gateway_payment_id": p.gateway_payment_id,
        }
        for p in payments
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


@router.get("/profile", response_model=Dict[str, Any], summary="Customer portal profile details")
def get_portal_profile(
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
):
    cust = db.scalars(
        select(Customer)
        .options(selectinload(Customer.contacts))
        .where(
            Customer.id == user.customer_id,
            Customer.organization_id == user.organization_id,
        )
    ).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found.")

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
        },
        "customer": {
            "id": cust.id,
            "customer_number": cust.customer_number,
            "display_name": cust.display_name,
            "company_name": cust.company_name,
            "email": cust.email,
            "phone": cust.phone,
            "website": cust.website,
            "gstin": cust.gstin,
            "pan": cust.pan,
            "currency": cust.currency,
            "billing_address_line1": cust.billing_address_line1,
            "billing_address_line2": cust.billing_address_line2,
            "billing_city": cust.billing_city,
            "billing_state": cust.billing_state,
            "billing_postal_code": cust.billing_postal_code,
            "billing_country": cust.billing_country,
        },
        "contacts": [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "designation": c.designation,
                "is_primary": c.is_primary,
            }
            for c in (cust.contacts or [])
        ],
    }


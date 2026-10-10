"""Hosted Payment Pages & Checkout Sessions API endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_finance, require_viewer
from backend.app.core.rate_limit import limiter, public_action_rate_limit, public_rate_limit
from backend.app.models.checkout import (
    CheckoutSession,
    CheckoutSessionStatus,
    CheckoutTemplate,
)
from backend.app.schemas.checkout import (
    CheckoutConfirmIn,
    CheckoutConfirmOut,
    CheckoutSessionCreate,
    CheckoutSessionOut,
    CheckoutTemplateCreate,
    CheckoutTemplateOut,
    CheckoutTemplateUpdate,
    PublicCheckoutView,
)
from backend.app.schemas.common import PaginatedResponse
from backend.app.services import checkout_service
from backend.app.services.email import frontend_url
from backend.app.services.pagination import PageParams, page_params, paginate

router = APIRouter()


# --- Admin / Internal Endpoints ---


@router.post("/sessions", response_model=CheckoutSessionOut, status_code=status.HTTP_201_CREATED, summary="Generate hosted checkout session")
def create_checkout_session(
    body: CheckoutSessionCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    session = checkout_service.create_checkout_session(db, ctx.organization_id, body)
    db.commit()
    raw_token = getattr(session, "raw_token", session.token)
    return CheckoutSessionOut(
        id=session.id,
        organization_id=session.organization_id,
        token=raw_token,
        # Absolute, like every other public link (invoice/quote public_url).
        checkout_url=frontend_url(f"checkout/{raw_token}"),
        purpose=session.purpose.value,
        status=session.status.value,
        amount=session.amount,
        currency=session.currency,
        expires_at=session.expires_at,
        customer_id=session.customer_id,
        invoice_id=session.invoice_id,
        subscription_id=session.subscription_id,
        plan_id=session.plan_id,
        payment_attempt_id=session.payment_attempt_id,
        payment_id=session.payment_id,
        save_payment_method=session.save_payment_method,
        completed_at=session.completed_at,
        created_at=session.created_at,
    )


@router.get("/sessions", response_model=PaginatedResponse[CheckoutSessionOut], summary="List checkout sessions")
def list_checkout_sessions(
    status_: Optional[str] = Query(None, alias="status"),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    query = (
        select(CheckoutSession)
        .where(CheckoutSession.organization_id == ctx.organization_id)
        .order_by(desc(CheckoutSession.created_at))
    )
    if status_:
        query = query.where(CheckoutSession.status == status_)

    page = paginate(db, query, params)
    return page.to_response(
        lambda s: CheckoutSessionOut(
            id=s.id,
            organization_id=s.organization_id,
            token=checkout_service.masked_reference(s.token),
            checkout_url=None,
            purpose=s.purpose.value,
            status=s.status.value,
            amount=s.amount,
            currency=s.currency,
            expires_at=s.expires_at,
            customer_id=s.customer_id,
            invoice_id=s.invoice_id,
            subscription_id=s.subscription_id,
            plan_id=s.plan_id,
            payment_attempt_id=s.payment_attempt_id,
            payment_id=s.payment_id,
            save_payment_method=s.save_payment_method,
            completed_at=s.completed_at,
            created_at=s.created_at,
        )
    )


@router.get("/templates", response_model=List[CheckoutTemplateOut], summary="List checkout templates")
def list_checkout_templates(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    items = list(
        db.scalars(
            select(CheckoutTemplate)
            .where(CheckoutTemplate.organization_id == ctx.organization_id)
            .order_by(desc(CheckoutTemplate.is_default), CheckoutTemplate.name)
        ).all()
    )
    return [CheckoutTemplateOut.model_validate(t) for t in items]


@router.post("/templates", response_model=CheckoutTemplateOut, status_code=status.HTTP_201_CREATED, summary="Create checkout template")
def create_checkout_template(
    body: CheckoutTemplateCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    tmpl = CheckoutTemplate(
        organization_id=ctx.organization_id,
        name=body.name,
        template_type=body.template_type,
        primary_color=body.primary_color,
        accent_color=body.accent_color,
        logo_url=body.logo_url,
        button_text=body.button_text,
        allow_quantity_edit=body.allow_quantity_edit,
        show_order_summary=body.show_order_summary,
        redirect_url=body.redirect_url,
        thank_you_message=body.thank_you_message,
        error_message_template=body.error_message_template,
        custom_fields=body.custom_fields,
        is_default=body.is_default,
    )
    db.add(tmpl)
    db.commit()
    return CheckoutTemplateOut.model_validate(tmpl)


# --- Public Endpoints (Token-Authenticated) ---


@router.get("/public/{token}", response_model=PublicCheckoutView, summary="Public checkout display view")
@limiter.limit(public_rate_limit)
def get_public_checkout(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    view = checkout_service.get_public_checkout_view(db, token)
    db.commit()
    return view


@router.post("/public/{token}/confirm", response_model=CheckoutConfirmOut, summary="Public checkout payment confirmation")
@limiter.limit(public_action_rate_limit)
def confirm_public_checkout(
    request: Request,
    token: str,
    body: CheckoutConfirmIn,
    db: Session = Depends(get_db),
):
    out = checkout_service.confirm_checkout_payment(db, token, body)
    db.commit()
    return out

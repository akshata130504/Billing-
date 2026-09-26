"""/subscriptions (contract §7)."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_finance, require_viewer
from backend.app.core.exceptions import InvalidStateError
from backend.app.models import SubscriptionStatus
from backend.app.schemas.common import PaginatedResponse
from backend.app.schemas.invoices import InvoiceOut
from backend.app.schemas.subscriptions import (
    SubscriptionCancelIn,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionSummaryOut,
    SubscriptionUpdate,
)
from backend.app.services import invoice_service, subscription_service
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("/summary", response_model=SubscriptionSummaryOut, summary="Get subscription KPI summary")
def subscriptions_summary(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return subscription_service.get_subscriptions_summary(db, ctx.organization_id)


@router.get("", response_model=PaginatedResponse[SubscriptionOut], summary="List subscriptions")
def list_subscriptions(
    search: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[str] = Query(None),
    plan_id: Optional[str] = Query(None),
    billing_frequency: Optional[str] = Query(None),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = subscription_service.list_subscriptions(
        db,
        ctx.organization_id,
        params,
        search=search,
        status=status_,
        customer_id=customer_id,
        plan_id=plan_id,
        billing_frequency=billing_frequency,
    )
    return page.to_response(subscription_service.serialize_subscription)


@router.post("", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED, summary="Create a subscription")
def create_subscription(
    body: SubscriptionCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    return subscription_service.serialize_subscription(subscription_service.create_subscription(db, ctx, body))


@router.get("/{subscription_id}", response_model=SubscriptionOut, summary="Get a subscription")
def get_subscription(
    subscription_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return subscription_service.serialize_subscription(
        subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    )


@router.patch("/{subscription_id}", response_model=SubscriptionOut, summary="Update quantity / notes / auto_renewal / cancel_at_period_end")
def update_subscription(
    subscription_id: str,
    body: SubscriptionUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    return subscription_service.serialize_subscription(subscription_service.update_subscription(db, ctx, sub, body))


@router.post("/{subscription_id}/activate", response_model=SubscriptionOut, summary="Activate draft subscription")
def activate_subscription(
    subscription_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    return subscription_service.serialize_subscription(subscription_service.activate_subscription(db, ctx, sub))


@router.post("/{subscription_id}/pause", response_model=SubscriptionOut, summary="Pause")
def pause_subscription(
    subscription_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    return subscription_service.serialize_subscription(subscription_service.pause_subscription(db, ctx, sub))


@router.post("/{subscription_id}/resume", response_model=SubscriptionOut, summary="Resume (period restarts today)")
def resume_subscription(
    subscription_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    return subscription_service.serialize_subscription(subscription_service.resume_subscription(db, ctx, sub))


@router.post("/{subscription_id}/renew", response_model=SubscriptionOut, summary="Manual period renewal")
def renew_subscription(
    subscription_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    if sub.status != SubscriptionStatus.ACTIVE:
        raise InvalidStateError(f"Only active subscriptions can be renewed; this one is {sub.status.value}.")
    if not subscription_service.is_renewal_due(sub):
        # A manual renewal must not bill the next period early: it is only a catch-up
        # for a renewal the scheduler has not processed yet.
        raise InvalidStateError(
            "This subscription is not due for renewal yet"
            + (f" (next billing date {sub.next_billing_date.isoformat()})." if sub.next_billing_date else ".")
        )
    subscription_service.renew_subscription(db, sub, actor_label=ctx.user.full_name, only_if_due=True)
    db.commit()
    return subscription_service.serialize_subscription(subscription_service.get_subscription(db, ctx.organization_id, subscription_id))


@router.post("/{subscription_id}/cancel", response_model=SubscriptionOut, summary="Cancel now or at period end")
def cancel_subscription(
    subscription_id: str,
    body: SubscriptionCancelIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    return subscription_service.serialize_subscription(
        subscription_service.cancel_subscription(
            db,
            ctx,
            sub,
            at_period_end=body.at_period_end,
            reason=body.reason,
            prorate_credit=body.prorate_credit,
        )
    )


@router.post(
    "/{subscription_id}/generate-invoice",
    response_model=InvoiceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Issue the invoice for the current period (idempotent per period)",
)
def generate_invoice(
    subscription_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    return invoice_service.serialize_invoice(subscription_service.generate_invoice(db, ctx, sub))


@router.get("/{subscription_id}/invoices", response_model=PaginatedResponse[InvoiceOut], summary="Invoices of a subscription")
def subscription_invoices(
    subscription_id: str,
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    page = invoice_service.list_invoices(db, ctx.organization_id, params, subscription_id=sub.id)
    return page.to_response(lambda inv: invoice_service.serialize_invoice(inv, include_payments=False))

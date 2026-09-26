"""Subscription changes and proration API endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.schemas.common_refs import money_str
from backend.app.schemas.proration import (
    SubscriptionChangeApplyIn,
    SubscriptionChangeOut,
    SubscriptionChangePreviewIn,
    SubscriptionChangePreviewOut,
)
from backend.app.services import subscription_change_service

router = APIRouter()


def _serialize_change(sc) -> dict:
    return {
        "id": sc.id,
        "subscription_id": sc.subscription_id,
        "change_type": sc.change_type,
        "status": sc.status,
        "effective_type": sc.effective_type,
        "effective_date": sc.effective_date,
        "target_plan_id": sc.target_plan_id,
        "target_quantity": str(sc.target_quantity) if sc.target_quantity is not None else None,
        "old_plan_amount": money_str(sc.old_plan_amount),
        "new_plan_amount": money_str(sc.new_plan_amount),
        "prorated_credit": money_str(sc.prorated_credit),
        "prorated_charge": money_str(sc.prorated_charge),
        "net_amount": money_str(sc.net_amount),
        "invoice_id": sc.invoice_id,
        "credit_note_id": sc.credit_note_id,
        "applied_at": sc.applied_at,
        "created_at": sc.created_at,
    }


@router.post(
    "/subscriptions/{subscription_id}/changes/preview",
    response_model=SubscriptionChangePreviewOut,
    summary="Preview subscription change and proration calculation",
)
def preview_change(
    subscription_id: str,
    body: SubscriptionChangePreviewIn,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return subscription_change_service.preview_subscription_change(
        db,
        organization_id=ctx.organization_id,
        subscription_id=subscription_id,
        target_plan_id=subscription_change_service.resolve_target_plan_id(
            db, ctx.organization_id, body.target_plan_id, body.target_offering_id
        ),
        target_quantity=body.target_quantity,
        effective_date=body.effective_date,
    )


@router.post(
    "/subscriptions/{subscription_id}/changes",
    response_model=SubscriptionChangeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Apply or schedule subscription upgrade, downgrade, or quantity change",
)
def apply_change(
    subscription_id: str,
    body: SubscriptionChangeApplyIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sc = subscription_change_service.apply_subscription_change(
        db,
        ctx=ctx,
        subscription_id=subscription_id,
        target_plan_id=subscription_change_service.resolve_target_plan_id(
            db, ctx.organization_id, body.target_plan_id, body.target_offering_id
        ),
        target_quantity=body.target_quantity,
        effective_type=body.effective_type,
        effective_date=body.effective_date,
    )
    return _serialize_change(sc)


@router.get(
    "/subscriptions/{subscription_id}/changes",
    response_model=List[SubscriptionChangeOut],
    summary="List change and proration history for a subscription",
)
def list_changes(
    subscription_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    changes = subscription_change_service.list_subscription_changes(
        db, organization_id=ctx.organization_id, subscription_id=subscription_id
    )
    return [_serialize_change(sc) for sc in changes]


@router.post(
    "/subscriptions/{subscription_id}/changes/{change_id}/cancel",
    response_model=SubscriptionChangeOut,
    summary="Cancel a scheduled subscription change",
)
def cancel_change(
    subscription_id: str,
    change_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    sc = subscription_change_service.cancel_scheduled_change(
        db, ctx=ctx, change_id=change_id
    )
    return _serialize_change(sc)

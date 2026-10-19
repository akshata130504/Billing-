"""Trial management endpoints for extensions, conversions, reports, and lifecycle operations."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_finance, require_viewer
from backend.app.models.trials import TrialPeriod, TrialPeriodStatus
from backend.app.schemas.common import PaginatedResponse
from backend.app.schemas.subscriptions import SubscriptionOut
from backend.app.schemas.trials import (
    TrialConversionResultOut,
    TrialConvertIn,
    TrialDetailOut,
    TrialExtensionIn,
    TrialFallbackIn,
    TrialPeriodOut,
    TrialReportsOut,
)
from backend.app.services import subscription_service, timezones, trial_service
from backend.app.services.pagination import PageParams, page_params, paginate

router = APIRouter()


@router.get("/reports", response_model=TrialReportsOut, summary="Get trial acquisition insights report")
def get_trial_reports(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return trial_service.get_trial_reports(
        db,
        ctx.organization_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("/evaluate", response_model=Dict[str, int], summary="Evaluate expiring and ended trials")
def evaluate_trials(
    today: Optional[date] = Query(None),
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    stats = trial_service.evaluate_expiring_trials(db, today=today, org_id=ctx.organization_id)
    db.commit()
    return stats


@router.get("", response_model=PaginatedResponse[TrialPeriodOut], summary="List trial periods")
def list_trials(
    status_: Optional[str] = Query(None, alias="status"),
    expiring_soon: bool = Query(False, description="Filter trials expiring within the next 7 days"),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    query = (
        select(TrialPeriod)
        .where(TrialPeriod.organization_id == ctx.organization_id)
        .order_by(desc(TrialPeriod.created_at))
    )

    if status_:
        query = query.where(TrialPeriod.status == status_)

    if expiring_soon:
        today = timezones.org_today(ctx.organization)
        query = query.where(
            TrialPeriod.status == TrialPeriodStatus.ACTIVE,
            TrialPeriod.trial_end_date <= today + timedelta(days=7),
            TrialPeriod.trial_end_date >= today,
        )

    # Count and page
    page = paginate(db, query, params)
    return page.to_response(lambda tp: TrialPeriodOut.model_validate(tp))


@router.get("/{subscription_id}", response_model=TrialDetailOut, summary="Get subscription trial details")
def get_subscription_trial(
    subscription_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    tp = trial_service.get_or_create_trial_period(db, sub)
    return trial_service.serialize_trial_detail(tp)


@router.post("/{subscription_id}/extend", response_model=TrialPeriodOut, summary="Extend subscription trial")
def extend_subscription_trial(
    subscription_id: str,
    body: TrialExtensionIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    tp = trial_service.extend_trial(
        db,
        sub,
        days=body.days,
        new_expiration_date=body.new_expiration_date,
        reason=body.reason,
        admin_override=body.admin_override,
        extended_by_id=ctx.user_id,
    )
    db.commit()
    return TrialPeriodOut.model_validate(tp)


@router.post("/{subscription_id}/convert", response_model=TrialConversionResultOut, summary="Convert trial to live subscription")
def convert_subscription_trial(
    subscription_id: str,
    body: TrialConvertIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    actor_label = ctx.user.email if ctx.user else "system"
    sub, invoice, attempt, succeeded, message = trial_service.convert_trial_to_live(
        db,
        sub,
        payment_method_id=body.payment_method_id,
        generate_first_invoice=body.generate_first_invoice,
        actor_label=actor_label,
    )
    db.commit()
    return TrialConversionResultOut(
        subscription_id=sub.id,
        status=sub.status.value,
        converted_at=sub.updated_at,
        invoice_id=invoice.id if invoice else None,
        payment_attempt_id=attempt.id if attempt else None,
        payment_succeeded=succeeded,
        message=message,
    )


@router.post("/{subscription_id}/fallback", response_model=SubscriptionOut, summary="Move trial to fallback free plan")
def apply_fallback_plan(
    subscription_id: str,
    body: TrialFallbackIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    sub = subscription_service.get_subscription(db, ctx.organization_id, subscription_id)
    actor_label = ctx.user.email if ctx.user else "system"
    sub = trial_service.move_to_fallback_plan(
        db,
        sub,
        fallback_plan_id=body.fallback_plan_id,
        actor_label=actor_label,
    )
    db.commit()
    return subscription_service.serialize_subscription(sub)

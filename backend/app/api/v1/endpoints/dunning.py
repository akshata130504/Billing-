"""Dunning management API endpoints: policies, cases, retries, pause/stop controls, and recovery metrics."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.core.exceptions import NotFoundAppError
from backend.app.models.dunning import DunningCase
from backend.app.schemas.dunning import (
    DunningCaseDetailOut,
    DunningCaseOut,
    DunningCasePauseIn,
    DunningCaseStopIn,
    DunningMetricsOut,
    DunningPolicyCreate,
    DunningPolicyOut,
    DunningPolicyUpdate,
    ExpiringCardNoticeOut,
)
from backend.app.services import dunning_service

router = APIRouter(prefix="/dunning", tags=["Dunning Management"])


# --- Policy Management ---

@router.get("/policies", response_model=List[DunningPolicyOut])
def list_dunning_policies(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> List[DunningPolicyOut]:
    """Lists all configured dunning recovery policies for the organization."""
    return dunning_service.list_policies(db, ctx.organization_id)


@router.post("/policies", response_model=DunningPolicyOut)
def create_dunning_policy(
    data: DunningPolicyCreate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DunningPolicyOut:
    """Creates a new dunning recovery policy."""
    policy = dunning_service.create_policy(db, ctx.organization_id, data)
    db.commit()
    db.refresh(policy)
    return policy


@router.put("/policies/{policy_id}", response_model=DunningPolicyOut)
def update_dunning_policy(
    policy_id: str,
    data: DunningPolicyUpdate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DunningPolicyOut:
    """Updates an existing dunning recovery policy."""
    policy = dunning_service.update_policy(db, policy_id, ctx.organization_id, data)
    db.commit()
    db.refresh(policy)
    return policy


# --- Case Operations ---

@router.get("/cases", response_model=List[DunningCaseOut])
def list_dunning_cases(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by case status"),
    customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
) -> List[DunningCaseOut]:
    """Lists dunning cases with optional status or customer filters."""
    query = (
        select(DunningCase)
        .where(DunningCase.organization_id == ctx.organization_id)
        .order_by(desc(DunningCase.created_at))
    )
    if status:
        query = query.where(DunningCase.status == status)
    if customer_id:
        query = query.where(DunningCase.customer_id == customer_id)

    return list(db.scalars(query).all())


@router.get("/cases/{case_id}", response_model=DunningCaseDetailOut)
def get_dunning_case_detail(
    case_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> DunningCaseDetailOut:
    """Retrieves full details for a dunning case, including attempts and communication log."""
    case = db.scalars(
        select(DunningCase)
        .options(
            joinedload(DunningCase.policy),
            joinedload(DunningCase.customer),
            joinedload(DunningCase.invoice),
            joinedload(DunningCase.attempts),
            joinedload(DunningCase.communications),
        )
        .where(
            DunningCase.id == case_id,
            DunningCase.organization_id == ctx.organization_id,
        )
    ).unique().first()
    if not case:
        raise NotFoundAppError("Dunning case not found.")

    return DunningCaseDetailOut(
        id=case.id,
        case_number=case.case_number,
        policy_id=case.policy_id,
        customer_id=case.customer_id,
        subscription_id=case.subscription_id,
        invoice_id=case.invoice_id,
        status=case.status,
        trigger_reason=case.trigger_reason,
        amount_due=case.amount_due,
        currency=case.currency,
        attempt_count=case.attempt_count,
        max_attempts=case.max_attempts,
        next_retry_at=case.next_retry_at,
        paused_at=case.paused_at,
        pause_reason=case.pause_reason,
        stopped_at=case.stopped_at,
        stop_reason=case.stop_reason,
        recovered_at=case.recovered_at,
        recovered_by_payment_id=case.recovered_by_payment_id,
        finalized_at=case.finalized_at,
        final_action_taken=case.final_action_taken,
        created_at=case.created_at,
        updated_at=case.updated_at,
        policy=DunningPolicyOut.model_validate(case.policy) if case.policy else None,
        customer_name=case.customer.display_name if case.customer else None,
        invoice_number=case.invoice.invoice_number if case.invoice else None,
        attempts=case.attempts,
        communications=case.communications,
    )


@router.post("/cases/{case_id}/pause", response_model=DunningCaseOut)
def pause_dunning_case(
    case_id: str,
    data: DunningCasePauseIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
) -> DunningCaseOut:
    """Pauses an active dunning case."""
    case = dunning_service.pause_dunning_case(db, case_id, ctx.organization_id, data)
    db.commit()
    db.refresh(case)
    return case


@router.post("/cases/{case_id}/resume", response_model=DunningCaseOut)
def resume_dunning_case(
    case_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
) -> DunningCaseOut:
    """Resumes a paused dunning case and schedules retry."""
    case = dunning_service.resume_dunning_case(db, case_id, ctx.organization_id)
    db.commit()
    db.refresh(case)
    return case


@router.post("/cases/{case_id}/stop", response_model=DunningCaseOut)
def stop_dunning_case(
    case_id: str,
    data: DunningCaseStopIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
) -> DunningCaseOut:
    """Stops dunning for an invoice and optionally applies final action."""
    case = dunning_service.stop_dunning_case(db, case_id, ctx.organization_id, data)
    db.commit()
    db.refresh(case)
    return case


@router.post("/cases/{case_id}/retry-now", response_model=DunningCaseDetailOut)
def trigger_immediate_retry(
    case_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
) -> DunningCaseDetailOut:
    """Forces an immediate retry attempt for an active dunning case."""
    from backend.app.services import org_lifecycle

    org_lifecycle.assert_billing_collection_allowed(db, ctx.organization_id)  # charges the card
    case = db.scalars(
        select(DunningCase).where(
            DunningCase.id == case_id,
            DunningCase.organization_id == ctx.organization_id,
        )
    ).first()
    if not case:
        raise NotFoundAppError("Dunning case not found.")

    # Force next_retry_at to past to trigger in batch executor
    from backend.app.models.base import utcnow
    case.next_retry_at = utcnow()
    db.flush()

    dunning_service.execute_dunning_retries(db, ctx.organization_id)
    db.commit()
    db.refresh(case)
    return get_dunning_case_detail(case.id, ctx, db)


@router.post("/subscriptions/{subscription_id}/reactivate")
def reactivate_cancelled_subscription(
    subscription_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    """In-term reactivation of a dunning-cancelled subscription without changing billing cycle."""
    sub = dunning_service.reactivate_dunning_cancelled_subscription(db, subscription_id, ctx.organization_id, ctx=ctx)
    db.commit()
    return {"status": "success", "message": "Subscription reactivated successfully.", "subscription_id": sub.id}


# --- Analytics & Pre-Dunning ---

@router.get("/metrics", response_model=DunningMetricsOut)
def get_dunning_metrics(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> DunningMetricsOut:
    """Returns real-time dunning recovery metrics, revenue recovered, and amount at risk."""
    return dunning_service.get_dunning_metrics(db, ctx.organization_id)


@router.get("/expiring-cards", response_model=List[ExpiringCardNoticeOut])
def get_expiring_cards_for_pre_dunning(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=90, description="Threshold in days to check for expiring cards"),
) -> List[ExpiringCardNoticeOut]:
    """Identifies vault cards expiring within the threshold for proactive customer notification."""
    return dunning_service.check_pre_dunning_expiring_cards(db, ctx.organization_id, days_threshold=days)

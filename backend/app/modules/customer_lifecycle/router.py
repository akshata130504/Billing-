"""Customer Lifecycle API endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.app.api.deps import (
    CurrentContext,
    get_db,
    require_admin,
    require_finance,
    require_viewer,
)
from backend.app.models.lifecycle import CustomerLifecycleStage, HealthStatus
from backend.app.schemas.lifecycle import (
    CustomerLifecycleDetail,
    CustomerLifecycleItem,
    CustomerLifecycleUpdate,
    LifecycleKPIs,
    TimelineEvent,
)
from backend.app.modules.customer_lifecycle import service as lifecycle_service

router = APIRouter()


@router.get("", response_model=List[CustomerLifecycleItem])
def list_lifecycles(
    response: Response,
    stage: Optional[CustomerLifecycleStage] = Query(None, description="Filter by lifecycle stage"),
    health: Optional[HealthStatus] = Query(None, description="Filter by health status"),
    search: Optional[str] = Query(None, description="Search by customer name/number/email"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Lists one page of customer lifecycles with aggregated health/financial indicators.

    The body stays a plain list (backwards compatible); the total matching count is in the
    `X-Total-Count` header for pagination controls.
    """
    total = lifecycle_service.count_customer_lifecycles(db, ctx, stage=stage, health=health, search=search)
    response.headers["X-Total-Count"] = str(total)
    return lifecycle_service.list_customer_lifecycles(
        db, ctx, stage=stage, health=health, search=search, page=page, page_size=page_size
    )


@router.get("/kpis", response_model=LifecycleKPIs)
def get_kpis(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Returns real-time KPI metrics for the customer lifecycle dashboard."""
    return lifecycle_service.get_lifecycle_kpis(db, ctx)


@router.get("/{customer_id}", response_model=CustomerLifecycleDetail)
def get_customer_lifecycle_detail(
    customer_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Returns comprehensive 360-degree customer lifecycle view."""
    return lifecycle_service.get_customer_lifecycle_detail(db, ctx, customer_id=customer_id)


@router.get("/{customer_id}/timeline", response_model=List[TimelineEvent])
def get_customer_timeline(
    customer_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Returns chronological customer lifecycle timeline events from database."""
    return lifecycle_service.get_customer_lifecycle_timeline(db, ctx, customer_id=customer_id)


@router.patch("/{customer_id}", response_model=CustomerLifecycleItem)
def update_customer_lifecycle(
    customer_id: str,
    payload: CustomerLifecycleUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    """Updates customer lifecycle stage, health, next action and notes."""
    return lifecycle_service.update_customer_lifecycle_stage(db, ctx, customer_id=customer_id, data=payload)

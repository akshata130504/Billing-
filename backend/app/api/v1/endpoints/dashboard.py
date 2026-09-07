"""Control-center read models: /dashboard/summary, /action-center, /calendar, /activity (contract §10)."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_viewer
from backend.app.schemas.common import PaginatedResponse
from backend.app.schemas.dashboard import (
    ActionCenterResponse,
    ActivityItem,
    CalendarResponse,
    DashboardRange,
    DashboardSummary,
)
from backend.app.services import dashboard_service
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("/dashboard/summary", response_model=DashboardSummary, summary="Dashboard KPIs, trend, pipeline and recent activity")
def dashboard_summary(
    range_: DashboardRange = Query("30_days", alias="range"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return dashboard_service.dashboard_summary(db, ctx.organization, range_)


@router.get("/action-center", response_model=ActionCenterResponse, summary="Things that need attention right now")
def action_center(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return dashboard_service.action_center(db, ctx.organization_id)


@router.get("/calendar", response_model=CalendarResponse, summary="Billing events for a month")
def calendar(
    month: Optional[str] = Query(None, description="YYYY-MM (defaults to the current month)"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return dashboard_service.calendar_events(db, ctx.organization_id, month)


@router.get("/activity", response_model=PaginatedResponse[ActivityItem], summary="Activity feed derived from the audit log")
def activity(
    category: str = Query("all", pattern="^(all|billing|customers|payments|system)$"),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = dashboard_service.list_activity(db, ctx.organization_id, params, category)
    return page.to_response(dashboard_service.activity_item)

"""Control-center read models: /dashboard/summary, /action-center, /calendar, /activity (contract §10)."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_viewer
from backend.app.schemas.common import PaginatedResponse
from backend.app.schemas.dashboard import (
    ActionCenterResponse,
    ActivityItem,
    CalendarResponse,
    CatalogSummary,
    DashboardRange,
    DashboardSummary,
    DealsSummary,
    FinancialSummary,
    QuotesSummary,
)
from backend.app.services import dashboard_service, dashboard_summary_service, timezones
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("/dashboard/summary", response_model=DashboardSummary, summary="Dashboard KPIs, trend, pipeline and recent activity")
def dashboard_summary(
    range_: DashboardRange = Query("30_days", alias="range"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return dashboard_service.dashboard_summary(db, ctx.organization, range_)


@router.get(
    "/dashboard/financial-summary",
    response_model=FinancialSummary,
    summary="Currency-aware counters: invoices, receivables, collections, subscriptions, MRR, quotes, credit notes, customers",
)
def financial_summary(
    range_: Optional[DashboardRange] = Query(None, alias="range", description="Shortcut; ignored when date_from/date_to are given"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Range-based figures (invoices/quotes/credit notes by issue date, payments by paid date,
    new customers) honour the date range; receivables, subscriptions and MRR are as of now.
    With neither `range` nor dates, range-based figures are all-time."""
    if range_ and not (date_from or date_to):
        date_from, date_to, _, _ = dashboard_service.resolve_range(range_, timezones.org_today(ctx.organization))
    return dashboard_summary_service.financial_summary(db, ctx.organization, date_from=date_from, date_to=date_to)


@router.get("/dashboard/quotes-summary", response_model=QuotesSummary, summary="Quote counts and value by status (quotes list KPIs)")
def quotes_summary(
    search: Optional[str] = Query(None, max_length=200),
    customer_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return dashboard_summary_service.quotes_summary(
        db, ctx.organization, search=search, customer_id=customer_id, date_from=date_from, date_to=date_to
    )


@router.get("/dashboard/catalog-summary", response_model=CatalogSummary, summary="Offering and price book counts (catalog KPIs)")
def catalog_summary(
    search: Optional[str] = Query(None, max_length=200),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return dashboard_summary_service.catalog_summary(db, ctx.organization, search=search)


@router.get("/dashboard/deals-summary", response_model=DealsSummary, summary="CPQ deal counts and value by status (CPQ KPIs)")
def deals_summary(
    customer_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return dashboard_summary_service.deals_summary(
        db, ctx.organization, customer_id=customer_id, date_from=date_from, date_to=date_to
    )


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

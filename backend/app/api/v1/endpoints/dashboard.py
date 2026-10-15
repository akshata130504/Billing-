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
from backend.app.services import dashboard_service, dashboard_summary_service, org_access, timezones
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()

# Overview, Action center and Calendar are core pages, but some of their figures come from optional
# product modules (core/modules.json). Those figures are left out (zeroed / omitted) for an
# organization that is not entitled to the module; everything from base modules is unchanged.
_ACTION_MODULES = {"expiring_trial": "subscriptions", "pending_quote": "quotes"}
_EVENT_MODULES = {"subscription_renewal": "subscriptions", "trial_ending": "subscriptions", "quote_expiry": "quotes"}


def _without_subscriptions_summary(data: dict) -> dict:
    data["revenue"].update(mrr="0.00", arr="0.00", mrr_change_pct=None, mrr_other_currencies={})
    data["customer_health"] = {
        "active": 0, "trialing": 0, "past_due": 0, "paused": 0, "cancelled_this_period": 0,
        "churned_customers": 0, "customers_at_period_start": 0, "churn_rate": None,
    }
    return data


def _filter_financial(data: dict, modules) -> dict:
    if "subscriptions" not in modules:
        data["subscriptions"] = {"total_count": 0, "by_status": {}}
        data["mrr"] = {"currency": data["mrr"]["currency"], "mrr": "0.00", "arr": "0.00", "by_currency": {},
                       "subscription_count": 0}
    if "quotes" not in modules:
        data["quotes"] = {"total_count": 0, "by_status": {}, "value_by_currency": []}
    return data


def _filter_action_center(data: dict, modules) -> dict:
    items = [i for i in data["items"] if _ACTION_MODULES.get(i["category"]) in (None, *modules)]
    counts = {key: 0 for key in data["counts"]}
    for item in items:
        counts[item["category"]] += 1
    return {**data, "items": items, "counts": counts}


@router.get("/dashboard/summary", response_model=DashboardSummary, summary="Dashboard KPIs, trend, pipeline and recent activity")
def dashboard_summary(
    range_: DashboardRange = Query("30_days", alias="range"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    data = dashboard_service.dashboard_summary(db, ctx.organization, range_)
    if "subscriptions" not in org_access.entitled_modules(db, ctx.organization):
        data = _without_subscriptions_summary(data)
    return data


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
    data = dashboard_summary_service.financial_summary(db, ctx.organization, date_from=date_from, date_to=date_to)
    return _filter_financial(data, org_access.entitled_modules(db, ctx.organization))


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
    data = dashboard_service.action_center(db, ctx.organization_id)
    return _filter_action_center(data, org_access.entitled_modules(db, ctx.organization))


@router.get("/calendar", response_model=CalendarResponse, summary="Billing events for a month")
def calendar(
    month: Optional[str] = Query(None, description="YYYY-MM (defaults to the current month)"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    data = dashboard_service.calendar_events(db, ctx.organization_id, month)
    modules = org_access.entitled_modules(db, ctx.organization)
    data["events"] = [e for e in data["events"] if _EVENT_MODULES.get(e["type"]) in (None, *modules)]
    return data


@router.get("/activity", response_model=PaginatedResponse[ActivityItem], summary="Activity feed derived from the audit log")
def activity(
    category: str = Query("all", pattern="^(all|billing|customers|payments|system)$"),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = dashboard_service.list_activity(db, ctx.organization_id, params, category)
    return page.to_response(dashboard_service.activity_item)

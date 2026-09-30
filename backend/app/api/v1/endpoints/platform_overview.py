"""Platform dashboard, health and audit. Mounted at /platform.

    GET /dashboard   any platform role     counts by status, recent sign-ups, health, scheduler
    GET /health      any platform role     API, database, migrations, scheduler, platform settings
    GET /audit       Administrator         platform audit log (filters, pages; read-only)

Counts and states only: no tenant financial data, no credentials, hosts or connection strings.
The audit log is append-only in the database (migration 0028); there is no edit, delete or purge.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.api.platform_deps import (
    ADMINISTRATOR_ONLY,
    PlatformContext,
    require_platform_roles,
    require_platform_staff,
)
from backend.app.api.v1.endpoints.platform_organizations import audit_page_out
from backend.app.schemas.platform_console import AuditPageOut, DashboardOut, HealthOut
from backend.app.services import platform_org_service, platform_overview_service

router = APIRouter()


@router.get("/dashboard", response_model=DashboardOut, summary="Platform dashboard (counts only)")
def dashboard(ctx: PlatformContext = Depends(require_platform_staff), db: Session = Depends(get_db)):
    return DashboardOut(**platform_overview_service.dashboard(db))


@router.get("/health", response_model=HealthOut, summary="Platform and system health")
def health(ctx: PlatformContext = Depends(require_platform_staff), db: Session = Depends(get_db)):
    return HealthOut(**platform_overview_service.health(db))


@router.get("/audit", response_model=AuditPageOut, summary="Platform audit log")
def audit(
    action: Optional[str] = Query(default=None, max_length=64),
    result: Optional[str] = Query(default=None, pattern="^(success|failure|denied)$"),
    staff_id: Optional[str] = Query(default=None, max_length=36),
    organization_id: Optional[str] = Query(default=None, max_length=36),
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=50, ge=1, le=platform_org_service.MAX_PAGE_SIZE),
    ctx: PlatformContext = Depends(require_platform_roles(ADMINISTRATOR_ONLY)),
    db: Session = Depends(get_db),
):
    rows, total = platform_org_service.audit_page(
        db, organization_id=organization_id, staff_id=staff_id, action=action, result=result, since=since,
        until=until, page=page, page_size=page_size,
    )
    return audit_page_out(rows, total, page, page_size)

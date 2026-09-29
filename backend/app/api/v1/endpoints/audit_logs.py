"""Audit log API (contract section 10). Mounted at /audit-logs. Admin and above."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin
from backend.app.core.exceptions import ValidationAppError
from backend.app.schemas.audit_logs import AuditLogOut
from backend.app.schemas.common_refs import PaginatedResponse
from backend.app.services import audit_query_service as svc
from backend.app.services import timezones
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


def audit_filters(
    search: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    actor_user_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
) -> svc.AuditFilters:
    return svc.AuditFilters(
        search=search,
        action=action,
        entity_type=entity_type,
        actor_user_id=actor_user_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("", response_model=PaginatedResponse[AuditLogOut], summary="List audit log entries")
def list_audit_logs(
    filters: svc.AuditFilters = Depends(audit_filters),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    page = svc.list_logs(db, ctx, params, filters)
    return page.to_response(svc.serialize_log)


@router.get(
    "/export",
    response_class=StreamingResponse,
    summary="Export audit log entries as CSV or JSON (max 10,000 rows)",
    responses={200: {"content": {"text/csv": {}, "application/json": {}}}},
)
def export_audit_logs(
    format: str = Query("csv", pattern="^(csv|json)$"),
    filters: svc.AuditFilters = Depends(audit_filters),
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    fmt = format.lower()
    if fmt not in ("csv", "json"):
        raise ValidationAppError("format must be csv or json", {"fields": {"format": "csv|json"}})
    stamp = timezones.org_today(ctx.organization).isoformat()
    if fmt == "csv":
        generator = svc.export_csv(db, ctx.organization_id, filters, getattr(ctx.organization, 'timezone', None))
        media_type = "text/csv; charset=utf-8"
        filename = f"audit-log-{stamp}.csv"
    else:
        generator = svc.export_json(db, ctx.organization_id, filters, getattr(ctx.organization, 'timezone', None))
        media_type = "application/json"
        filename = f"audit-log-{stamp}.json"
    return StreamingResponse(
        generator,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

"""Read side of the audit log: filtered listing and CSV/JSON export."""
import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Dict, Iterator, Optional

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.models import AuditLog
from backend.app.schemas.common_refs import enum_value, iso_dt, user_ref
from backend.app.services.pagination import Page, PageParams, paginate
from backend.app.services import timezones
from types import SimpleNamespace

EXPORT_MAX_ROWS = 10_000
EXPORT_BATCH = 500

CSV_COLUMNS = (
    "id",
    "created_at",
    "actor",
    "actor_label",
    "action",
    "entity_type",
    "entity_id",
    "entity_label",
    "status",
    "before_state",
    "after_state",
    "ip_address",
)


@dataclass
class AuditFilters:
    search: Optional[str] = None
    action: Optional[str] = None
    entity_type: Optional[str] = None
    actor_user_id: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None


def build_query(organization_id: str, filters: AuditFilters, tz_name: Optional[str] = None) -> Select:
    stmt = (
        select(AuditLog)
        .where(AuditLog.organization_id == organization_id)
        .options(selectinload(AuditLog.actor))
    )
    if filters.search:
        like = f"%{filters.search.strip()}%"
        stmt = stmt.where(
            or_(
                AuditLog.entity_label.ilike(like),
                AuditLog.actor_label.ilike(like),
                AuditLog.action.ilike(like),
                AuditLog.entity_id.ilike(like),
            )
        )
    if filters.action:
        stmt = stmt.where(AuditLog.action == filters.action.strip().upper())
    if filters.entity_type:
        stmt = stmt.where(AuditLog.entity_type == filters.entity_type.strip().lower())
    if filters.actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == filters.actor_user_id)
    # Date filters are calendar dates in the organization's timezone, resolved to
    # UTC instants here. Comparing them against UTC midnight would drop everything
    # logged between 00:00 and 05:30 IST from a "today" filter.
    tz = timezones.tz_for(SimpleNamespace(timezone=tz_name))
    start, end = timezones.range_bounds_utc(filters.date_from, filters.date_to, tz)
    if start is not None:
        stmt = stmt.where(AuditLog.created_at >= start)
    if end is not None:
        stmt = stmt.where(AuditLog.created_at < end)
    return stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


def list_logs(db: Session, ctx: CurrentContext, params: PageParams, filters: AuditFilters) -> Page:
    return paginate(db, build_query(ctx.organization_id, filters, getattr(ctx.organization, 'timezone', None)), params)


def serialize_log(log: AuditLog) -> Dict[str, Any]:
    return {
        "id": log.id,
        "created_at": iso_dt(log.created_at),
        "actor": user_ref(log.actor),
        "actor_label": log.actor_label,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "entity_label": log.entity_label,
        "status": enum_value(log.status),
        "before_state": log.before_state,
        "after_state": log.after_state,
        "ip_address": log.ip_address,
    }


def _iter_rows(db: Session, organization_id: str, filters: AuditFilters, tz_name: Optional[str] = None) -> Iterator[AuditLog]:
    stmt = build_query(organization_id, filters, tz_name)
    emitted = 0
    offset = 0
    while emitted < EXPORT_MAX_ROWS:
        batch = list(db.scalars(stmt.offset(offset).limit(min(EXPORT_BATCH, EXPORT_MAX_ROWS - emitted))).all())
        if not batch:
            break
        for row in batch:
            yield row
            emitted += 1
        offset += len(batch)
        if len(batch) < EXPORT_BATCH:
            break


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return iso_dt(value).isoformat().replace("+00:00", "Z")
    return str(value)


def _dt_text(value: Optional[datetime]) -> str:
    normalised = iso_dt(value)
    return normalised.isoformat().replace("+00:00", "Z") if normalised else ""


def export_csv(db: Session, organization_id: str, filters: AuditFilters, tz_name: Optional[str] = None) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    for log in _iter_rows(db, organization_id, filters, tz_name):
        actor = log.actor
        writer.writerow(
            [
                log.id,
                _dt_text(log.created_at),
                f"{actor.full_name} <{actor.email}>" if actor else "",
                log.actor_label,
                log.action,
                log.entity_type,
                log.entity_id or "",
                log.entity_label or "",
                enum_value(log.status),
                json.dumps(log.before_state, default=_json_default) if log.before_state is not None else "",
                json.dumps(log.after_state, default=_json_default) if log.after_state is not None else "",
                log.ip_address or "",
            ]
        )
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def export_json(db: Session, organization_id: str, filters: AuditFilters, tz_name: Optional[str] = None) -> Iterator[str]:
    yield "["
    first = True
    for log in _iter_rows(db, organization_id, filters, tz_name):
        chunk = json.dumps(serialize_log(log), default=_json_default)
        yield chunk if first else "," + chunk
        first = False
    yield "]"

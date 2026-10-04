"""Append-only audit trail.

Every state-changing service call records what happened. Rows are only ever
inserted; nothing in the application updates or deletes them.
"""
from decimal import Decimal
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.models import AuditLog, AuditStatus

SYSTEM_ACTOR = "System scheduler"
WEBHOOK_ACTOR = "Razorpay webhook"
CUSTOMER_ACTOR = "Customer (hosted page)"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def snapshot(obj: Any, fields: tuple[str, ...]) -> Dict[str, Any]:
    """Pick a JSON-safe subset of an ORM object's columns for before/after states."""
    return {f: _jsonable(getattr(obj, f, None)) for f in fields}


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    entity_label: Optional[str] = None,
    organization_id: Optional[str] = None,
    ctx: Optional[CurrentContext] = None,
    actor_label: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    status: AuditStatus = AuditStatus.SUCCESS,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """Add an audit row to the current transaction (caller commits).

    ``ip_address``/``user_agent`` attribute unauthenticated actors (e.g. a customer on a hosted page);
    when omitted they come from ``ctx``.
    """
    entry = AuditLog(
        organization_id=organization_id or (ctx.organization_id if ctx else None),
        actor_user_id=ctx.user.id if ctx else None,
        actor_label=actor_label or (ctx.user.full_name if ctx else SYSTEM_ACTOR),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        status=status,
        before_state=_jsonable(before) if before is not None else None,
        after_state=_jsonable(after) if after is not None else None,
        ip_address=ip_address or (ctx.ip_address if ctx else None),
        user_agent=user_agent or (ctx.user_agent if ctx else None),
    )
    db.add(entry)
    return entry

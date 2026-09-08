"""Transactional Outbox Processor.

Consumes pending OutboxEvents in order, transitions them through PROCESSING -> PUBLISHED/FAILED,
and safely uses SELECT FOR UPDATE SKIP LOCKED on PostgreSQL to allow concurrent workers.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.events import OutboxEvent, OutboxStatus

_EVENT_HANDLERS: Dict[str, List[Callable[[Session, OutboxEvent], None]]] = {}


def register_outbox_handler(event_type: str, handler: Callable[[Session, OutboxEvent], None]) -> None:
    """Registers a handler function to be invoked when an outbox event of event_type is processed."""
    if event_type not in _EVENT_HANDLERS:
        _EVENT_HANDLERS[event_type] = []
    _EVENT_HANDLERS[event_type].append(handler)


def clear_outbox_handlers() -> None:
    """Clear all registered handlers (mainly for tests)."""
    _EVENT_HANDLERS.clear()


def claim_and_publish_outbox_events(
    db: Session,
    organization_id: Optional[str] = None,
    limit: int = 50,
    max_retries: int = 5,
) -> int:
    """Claims pending outbox events and publishes/dispatches them.

    Returns:
        Number of events successfully published.
    """
    stmt = select(OutboxEvent).where(OutboxEvent.status == OutboxStatus.PENDING)
    if organization_id is not None:
        stmt = stmt.where(OutboxEvent.organization_id == organization_id)
    stmt = stmt.order_by(OutboxEvent.created_at.asc()).limit(limit)

    bind = db.get_bind() if hasattr(db, "get_bind") else getattr(db, "bind", None)
    if bind is not None and getattr(bind.dialect, "name", "") == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    events = list(db.scalars(stmt).all())
    published_count = 0

    for event in events:
        event.status = OutboxStatus.PROCESSING
        db.flush()

        try:
            # Execute registered handlers if any
            handlers = _EVENT_HANDLERS.get(event.event_type, [])
            for handler in handlers:
                handler(db, event)

            event.status = OutboxStatus.PUBLISHED
            event.published_at = utcnow()
            event.last_error = None
            published_count += 1
        except Exception as exc:
            logger.exception("Failed to publish outbox event %s", event.id)
            event.retry_count += 1
            event.last_error = str(exc)[:2000]
            if event.retry_count >= max_retries:
                event.status = OutboxStatus.FAILED
            else:
                event.status = OutboxStatus.PENDING

        db.flush()

    return published_count

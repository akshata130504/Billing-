"""Unit of Work pattern and transactional boundary coordination.

Ensures that multi-step operations (e.g. invoice issuing + credit application + outbox event)
occur in a single atomic database transaction without intermediate rogue commits.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional
from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal
from backend.app.core.logging import logger
from backend.app.models.events import DomainEventType, OutboxEvent, OutboxStatus, utcnow


class UnitOfWork:
    """Manages transactional boundaries and event publishing for application services."""

    def __init__(self, db: Session):
        self.db = db
        self._outbox_events: List[OutboxEvent] = []

    def register_event(
        self,
        organization_id: str,
        event_type: DomainEventType | str,
        aggregate_type: str,
        aggregate_id: str,
        payload: Dict[str, Any],
    ) -> OutboxEvent:
        """Register a domain event to be saved in the outbox atomically with the transaction."""
        event_str = event_type.value if isinstance(event_type, DomainEventType) else str(event_type)
        event = OutboxEvent(
            organization_id=organization_id,
            event_type=event_str,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            status=OutboxStatus.PENDING,
            created_at=utcnow(),
        )
        self._outbox_events.append(event)
        self.db.add(event)
        return event

    @property
    def pending_events(self) -> List[OutboxEvent]:
        return list(self._outbox_events)

    def commit(self) -> None:
        """Commit all mutations and registered events in one transaction."""
        self.db.commit()
        self._outbox_events.clear()

    def rollback(self) -> None:
        """Rollback the transaction on failure."""
        self.db.rollback()
        self._outbox_events.clear()

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()


@contextmanager
def unit_of_work(db: Optional[Session] = None) -> Iterator[UnitOfWork]:
    """Context manager providing a UnitOfWork. Uses existing session or creates a new one."""
    owns_session = False
    if db is None:
        db = SessionLocal()
        owns_session = True

    uow = UnitOfWork(db)
    try:
        yield uow
        uow.commit()
    except Exception:
        uow.rollback()
        logger.exception("UnitOfWork transaction rolled back due to an unhandled error")
        raise
    finally:
        if owns_session:
            db.close()

"""Transactional Outbox Processor.

Consumes pending OutboxEvents in order, transitions them through PROCESSING -> PUBLISHED/FAILED,
and uses SELECT ... FOR UPDATE SKIP LOCKED on PostgreSQL so concurrent workers never claim the
same row.

Built-in routing (always active, independent of the pluggable handler registry):
- ``email.send``       -> durable email delivery (see ``email.enqueue_email``)
- ``webhook.deliver``  -> one outbound webhook delivery attempt (signed, SSRF-guarded)
- any domain event     -> automation rules (``customization_service.process_outbox_event_automation``)
                          + fan-out to subscribed outbound webhook endpoints

Failures are retried with exponential backoff (``next_attempt_at``) up to ``max_attempts``;
rows stuck in PROCESSING longer than the lease (crashed worker) are reclaimed.

Entry points used by the scheduler: ``process_pending_outbox(db)`` and ``process_due_jobs(db)``.
Domain services publish events with ``emit_event(db, organization_id, event_type, payload)`` in
the same transaction as their business mutation.
"""
from __future__ import annotations

import os
import socket
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.events import DomainEventType, OutboxEvent, OutboxStatus

EMAIL_SEND_EVENT = "email.send"
WEBHOOK_DELIVER_EVENT = "webhook.deliver"
INTERNAL_EVENT_TYPES = frozenset({EMAIL_SEND_EVENT, WEBHOOK_DELIVER_EVENT})

DEFAULT_MAX_ATTEMPTS = 8
PROCESSING_LEASE_MINUTES = 10
BASE_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 6 * 60 * 60

_EVENT_HANDLERS: Dict[str, List[Callable[[Session, OutboxEvent], None]]] = {}
_JOB_HANDLERS: Dict[str, Callable[[Session, Any], None]] = {}


class OutboxRetry(Exception):
    """Raised by a handler to request a retry while KEEPING the changes it made (e.g. a recorded
    failed delivery attempt). Any other exception rolls the handler's changes back before retrying."""


def register_outbox_handler(event_type: str, handler: Callable[[Session, OutboxEvent], None]) -> None:
    """Registers a handler function to be invoked when an outbox event of event_type is processed.

    Use ``"*"`` to receive every event. Built-in routing (email, webhooks, automation) does not
    depend on this registry.
    """
    _EVENT_HANDLERS.setdefault(event_type, []).append(handler)


def clear_outbox_handlers() -> None:
    """Clear all registered (custom) handlers (mainly for tests). Built-in routing is unaffected."""
    _EVENT_HANDLERS.clear()


def register_job_handler(job_type: str, handler: Callable[[Session, Any], None]) -> None:
    """Registers a durable-job handler; ``process_due_jobs`` only claims job types with a handler."""
    _JOB_HANDLERS[job_type] = handler


def clear_job_handlers() -> None:
    _JOB_HANDLERS.clear()


def _event_type_str(event_type: Any) -> str:
    return str(getattr(event_type, "value", event_type) or "")


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------

def emit_event(
    db: Session,
    organization_id: str,
    event_type: DomainEventType | str,
    payload: Optional[Dict[str, Any]] = None,
    aggregate_type: Optional[str] = None,
    aggregate_id: Optional[str] = None,
) -> OutboxEvent:
    """Writes a PENDING domain event to the outbox in the caller's transaction (no commit).

    ``aggregate_type`` defaults to the event prefix (``invoice.paid`` -> ``invoice``) and
    ``aggregate_id`` to ``payload['<aggregate_type>_id']`` or ``payload['id']``.
    """
    event_str = _event_type_str(event_type)
    data = dict(payload or {})
    agg_type = aggregate_type or event_str.split(".", 1)[0] or "event"
    agg_id = aggregate_id or data.get(f"{agg_type}_id") or data.get("id") or "-"
    event = OutboxEvent(
        organization_id=organization_id,
        event_type=event_str,
        aggregate_type=agg_type,
        aggregate_id=str(agg_id)[:36],
        payload=data,
        status=OutboxStatus.PENDING,
        created_at=utcnow(),
    )
    db.add(event)
    db.flush()
    return event


def enqueue_webhook_delivery(db: Session, organization_id: str, delivery_id: str, delay_seconds: int = 0) -> OutboxEvent:
    """Queues a (re)delivery attempt for an OutboundWebhookDelivery row."""
    event = OutboxEvent(
        organization_id=organization_id,
        event_type=WEBHOOK_DELIVER_EVENT,
        aggregate_type="webhook_delivery",
        aggregate_id=delivery_id,
        payload={"delivery_id": delivery_id},
        status=OutboxStatus.PENDING,
        created_at=utcnow(),
        next_attempt_at=(utcnow() + timedelta(seconds=delay_seconds)) if delay_seconds else None,
    )
    db.add(event)
    db.flush()
    return event


# ---------------------------------------------------------------------------
# Built-in handlers
# ---------------------------------------------------------------------------

def _handle_email_send(db: Session, event: OutboxEvent) -> None:
    from backend.app.models.notifications import NotificationDelivery, NotificationDeliveryStatus
    from backend.app.services.email import resolve_smtp_config, send_email

    payload = event.payload or {}
    delivery = None
    delivery_id = payload.get("notification_delivery_id")
    if delivery_id:
        delivery = db.get(NotificationDelivery, delivery_id)
        if delivery is not None and delivery.status in (NotificationDeliveryStatus.SENT, NotificationDeliveryStatus.DELIVERED):
            return  # already sent (idempotent re-run)

    attempt_no = (event.retry_count or 0) + 1
    smtp_cfg = resolve_smtp_config(db, event.organization_id)
    try:
        sent = send_email(
            to=payload.get("to") or [],
            subject=payload.get("subject") or "Billing Notification",
            text_body=payload.get("text_body") or "",
            html_body=payload.get("html_body"),
            reply_to=payload.get("reply_to"),
            smtp_config=smtp_cfg,
        )
    except Exception as exc:  # noqa: BLE001 - SMTP / network errors are retryable
        if delivery is not None:
            delivery.attempts = attempt_no
            delivery.error = str(exc)[:2000]
        db.flush()
        raise OutboxRetry(f"SMTP delivery failed: {exc}") from exc

    if delivery is not None:
        delivery.attempts = attempt_no
        if sent:
            delivery.status = NotificationDeliveryStatus.SENT
            delivery.sent_at = utcnow()
            delivery.error = None
        else:
            # Nothing to retry until an administrator configures SMTP.
            delivery.status = NotificationDeliveryStatus.FAILED
            delivery.error = "smtp_not_configured"
    db.flush()


def _handle_webhook_delivery(db: Session, event: OutboxEvent) -> None:
    from backend.app.models.customization import OutboundWebhookDelivery
    from backend.app.services import customization_service

    delivery_id = (event.payload or {}).get("delivery_id") or event.aggregate_id
    delivery = db.get(OutboundWebhookDelivery, delivery_id)
    if delivery is None or delivery.status == "delivered":
        return
    customization_service.deliver_webhook(db, delivery)
    if delivery.status == "delivered":
        _sync_webhook_notification(db, delivery, sent=True)
    db.flush()
    if delivery.status != "delivered":
        raise OutboxRetry(delivery.error_message or "Webhook delivery failed")


def _sync_webhook_notification(db: Session, delivery: Any, sent: bool) -> None:
    """Mirrors a webhook delivery outcome onto the NotificationDelivery that queued it (if any)."""
    notification_id = (delivery.payload or {}).get("notification_delivery_id") if isinstance(delivery.payload, dict) else None
    if not notification_id:
        return
    from backend.app.models.notifications import NotificationDelivery, NotificationDeliveryStatus

    notification = db.get(NotificationDelivery, notification_id)
    if notification is None:
        return
    notification.attempts = delivery.attempt_count or notification.attempts
    if sent:
        notification.status = NotificationDeliveryStatus.SENT
        notification.sent_at = utcnow()
        notification.error = None
    else:
        notification.status = NotificationDeliveryStatus.FAILED
        notification.error = (delivery.error_message or "Webhook delivery failed")[:2000]


def _handle_domain_event(db: Session, event: OutboxEvent) -> None:
    from backend.app.services import customization_service

    event_type = _event_type_str(event.event_type)
    payload = dict(event.payload or {})
    customization_service.process_outbox_event_automation(
        db,
        event.organization_id,
        event_type,
        payload,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
    )
    customization_service.enqueue_subscribed_webhooks(
        db,
        event.organization_id,
        event_type,
        payload,
        event_id=event.id,
    )


def _dispatch(db: Session, event: OutboxEvent) -> None:
    event_type = _event_type_str(event.event_type)
    if event_type == EMAIL_SEND_EVENT:
        _handle_email_send(db, event)
    elif event_type == WEBHOOK_DELIVER_EVENT:
        _handle_webhook_delivery(db, event)
    else:
        _handle_domain_event(db, event)

    for handler in list(_EVENT_HANDLERS.get(event_type, [])) + list(_EVENT_HANDLERS.get("*", [])):
        handler(db, event)


def _on_permanent_failure(db: Session, event: OutboxEvent) -> None:
    """Final bookkeeping once an event exhausts its attempts."""
    if _event_type_str(event.event_type) == WEBHOOK_DELIVER_EVENT:
        from backend.app.models.customization import OutboundWebhookDelivery

        delivery_id = (event.payload or {}).get("delivery_id") or event.aggregate_id
        delivery = db.get(OutboundWebhookDelivery, delivery_id)
        if delivery is not None and delivery.status != "delivered":
            delivery.status = "failed"
            _sync_webhook_notification(db, delivery, sent=False)
    elif _event_type_str(event.event_type) == EMAIL_SEND_EVENT:
        from backend.app.models.notifications import NotificationDelivery, NotificationDeliveryStatus

        delivery_id = (event.payload or {}).get("notification_delivery_id")
        delivery = db.get(NotificationDelivery, delivery_id) if delivery_id else None
        if delivery is not None and delivery.status == NotificationDeliveryStatus.PENDING:
            delivery.status = NotificationDeliveryStatus.FAILED
            delivery.error = (event.last_error or "Delivery failed")[:2000]


# ---------------------------------------------------------------------------
# Claiming & processing
# ---------------------------------------------------------------------------

def _is_postgres(db: Session) -> bool:
    bind = db.get_bind() if hasattr(db, "get_bind") else getattr(db, "bind", None)
    return bind is not None and getattr(bind.dialect, "name", "") == "postgresql"


def _backoff_seconds(retry_count: int) -> int:
    return int(min(BASE_BACKOFF_SECONDS * (2 ** max(0, retry_count - 1)), MAX_BACKOFF_SECONDS))


def reclaim_stale_processing(db: Session, lease_minutes: int = PROCESSING_LEASE_MINUTES) -> int:
    """Returns rows stuck in PROCESSING (worker crashed mid-flight) to PENDING."""
    cutoff = utcnow() - timedelta(minutes=lease_minutes)
    result = db.execute(
        update(OutboxEvent)
        .where(
            OutboxEvent.status == OutboxStatus.PROCESSING,
            or_(
                OutboxEvent.locked_at < cutoff,
                and_(OutboxEvent.locked_at.is_(None), OutboxEvent.created_at < cutoff),
            ),
        )
        .values(status=OutboxStatus.PENDING, locked_at=None)
        .execution_options(synchronize_session=False)
    )
    reclaimed = int(result.rowcount or 0)
    if reclaimed:
        logger.warning("Outbox: reclaimed %d event(s) stuck in PROCESSING", reclaimed)
    db.commit()
    return reclaimed


def _claim_batch(db: Session, organization_id: Optional[str], limit: int) -> List[OutboxEvent]:
    now = utcnow()
    stmt = select(OutboxEvent).where(
        OutboxEvent.status == OutboxStatus.PENDING,
        or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
    )
    if organization_id is not None:
        stmt = stmt.where(OutboxEvent.organization_id == organization_id)
    stmt = stmt.order_by(OutboxEvent.created_at.asc()).limit(limit)
    if _is_postgres(db):
        stmt = stmt.with_for_update(skip_locked=True)

    events = list(db.scalars(stmt).all())
    for event in events:
        event.status = OutboxStatus.PROCESSING
        event.locked_at = now
    # Commit releases the row locks; the PROCESSING status keeps other workers away.
    db.commit()
    return events


def _process_one(db: Session, event: OutboxEvent, max_attempts: int) -> bool:
    event_id = event.id
    error: Optional[str] = None
    keep_changes = False
    try:
        _dispatch(db, event)
    except OutboxRetry as exc:
        error = str(exc) or "retry requested"
        keep_changes = True
    except Exception as exc:  # noqa: BLE001 - one bad event must not stop the batch
        logger.exception("Failed to publish outbox event %s", event_id)
        error = f"{type(exc).__name__}: {exc}"

    if error is None:
        event.status = OutboxStatus.PUBLISHED
        event.published_at = utcnow()
        event.last_error = None
        event.locked_at = None
        event.next_attempt_at = None
        db.commit()
        return True

    if not keep_changes:
        db.rollback()
        event = db.get(OutboxEvent, event_id)
        if event is None:  # pragma: no cover - deleted concurrently
            return False

    event.retry_count = (event.retry_count or 0) + 1
    event.last_error = error[:2000]
    event.locked_at = None
    if event.retry_count >= max_attempts:
        event.status = OutboxStatus.FAILED
        event.next_attempt_at = None
        _on_permanent_failure(db, event)
    else:
        event.status = OutboxStatus.PENDING
        event.next_attempt_at = utcnow() + timedelta(seconds=_backoff_seconds(event.retry_count))
    db.commit()
    return False


def process_pending_outbox(
    db: Session,
    organization_id: Optional[str] = None,
    limit: int = 100,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_batches: int = 5,
    lease_minutes: int = PROCESSING_LEASE_MINUTES,
) -> int:
    """Claims due PENDING outbox events, dispatches them and records the outcome.

    Commits after the claim and after every event, so call it with a dedicated session
    (scheduler tick). Events emitted by handlers (e.g. webhook fan-out) are picked up by the
    next batch within the same call. Returns the number of events successfully published.
    """
    reclaim_stale_processing(db, lease_minutes=lease_minutes)
    published = 0
    for _ in range(max(1, max_batches)):
        events = _claim_batch(db, organization_id, limit)
        if not events:
            break
        for event in events:
            if _process_one(db, event, max_attempts):
                published += 1
    return published


def claim_and_publish_outbox_events(
    db: Session,
    organization_id: Optional[str] = None,
    limit: int = 50,
    max_retries: int = 5,
) -> int:
    """Backwards-compatible single-batch variant of ``process_pending_outbox``.

    Returns:
        Number of events successfully published.
    """
    published = 0
    for event in _claim_batch(db, organization_id, limit):
        if _process_one(db, event, max_retries):
            published += 1
    return published


# ---------------------------------------------------------------------------
# Durable jobs
# ---------------------------------------------------------------------------

def process_due_jobs(db: Session, worker_id: Optional[str] = None, limit: int = 20) -> int:
    """Claims due durable jobs that have a registered handler and runs them.

    Returns the number of jobs completed. When no job handlers are registered nothing is
    claimed (so unknown job types are never burned through their attempts).
    """
    from backend.app.services.durable_job_service import claim_due_jobs, complete_job, fail_job

    if not _JOB_HANDLERS:
        return 0
    worker = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    jobs = claim_due_jobs(db, worker_id=worker, limit=limit, job_types=list(_JOB_HANDLERS.keys()))
    db.commit()

    completed = 0
    for job in jobs:
        job_id = job.id
        try:
            _JOB_HANDLERS[job.job_type](db, job)
            complete_job(db, job_id, worker_id=worker)
            db.commit()
            completed += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Durable job %s (%s) failed", job_id, job.job_type)
            db.rollback()
            fail_job(db, job_id, f"{type(exc).__name__}: {exc}", worker_id=worker)
            db.commit()
    return completed

"""Idempotency service to deduplicate requests and return cached responses."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import ConflictAppError
from backend.app.models.events import IdempotencyRecord, utcnow


def check_idempotency(
    db: Session,
    organization_id: str,
    key: str,
    request_path: str,
    request_method: str,
    params_hash: Optional[Any] = None,
    ttl_hours: int = 24,
) -> Tuple[Optional[IdempotencyRecord], bool]:
    """Check if an idempotency key was previously processed.

    Returns:
        (record, is_cached) where is_cached is True if a completed response is cached.
    """
    if isinstance(params_hash, dict):
        import hashlib
        import json
        params_hash = hashlib.sha256(json.dumps(params_hash, sort_keys=True).encode()).hexdigest()
    elif params_hash is not None and not isinstance(params_hash, str):
        params_hash = str(params_hash)

    now = utcnow()
    record = db.scalars(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == organization_id,
            IdempotencyRecord.idempotency_key == key,
        )
    ).first()

    if record is not None:
        expires = record.expires_at.replace(tzinfo=timezone.utc) if record.expires_at.tzinfo is None else record.expires_at
        current = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
        if expires <= current:
            db.delete(record)
            db.commit()
            record = None
        else:
            if (record.params_hash or params_hash) and record.params_hash != params_hash:
                raise ConflictAppError(
                    "Idempotency key reused with mismatched request parameters."
                )
            if record.status == "completed":
                return record, True
            elif record.status == "processing":
                raise ConflictAppError(
                    "A concurrent request with the same idempotency key is currently being processed."
                )

    new_record = IdempotencyRecord(
        organization_id=organization_id,
        idempotency_key=key,
        request_path=request_path,
        request_method=request_method,
        params_hash=params_hash,
        status="processing",
        expires_at=now + timedelta(hours=ttl_hours),
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record, False


def complete_idempotency(
    db: Session,
    record_id: Optional[str] = None,
    status_code: int = 200,
    response_body: Optional[Dict[str, Any]] = None,
    organization_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> None:
    """Store the completed response for the idempotency record."""
    if record_id:
        record = db.scalars(
            select(IdempotencyRecord).where(IdempotencyRecord.id == record_id)
        ).first()
    elif organization_id and idempotency_key:
        record = db.scalars(
            select(IdempotencyRecord).where(
                IdempotencyRecord.organization_id == organization_id,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        ).first()
    else:
        record = None

    if record is not None:
        record.status = "completed"
        record.status_code = status_code
        record.response_body = response_body or {}
        db.commit()


def run_idempotent(
    db: Session,
    *,
    organization_id: str,
    key: Optional[str],
    request_path: str,
    request_method: str,
    params: Optional[Any],
    handler: Callable[[], Dict[str, Any]],
    status_code: int = 200,
) -> Tuple[int, Dict[str, Any]]:
    """Run `handler` at most once per (organization, Idempotency-Key).

    Without a key the handler simply runs. With a key, a completed earlier request
    with the same parameters returns its stored response instead of re-executing
    (so a retried "record payment" never books the money twice); a key reused with
    different parameters, or while the first request is still running, is a 409.
    If the handler raises, the reservation is released so the client can retry.
    `handler` must return a JSON-serialisable dict.
    """
    if not key:
        return status_code, handler()
    key = key.strip()[:128]
    record, cached = check_idempotency(db, organization_id, key, request_path, request_method, params_hash=params)
    if cached:
        return int(record.status_code or status_code), dict(record.response_body or {})
    record_id = record.id
    try:
        body = handler()
    except Exception:
        db.rollback()
        stale = db.get(IdempotencyRecord, record_id)
        if stale is not None and stale.status != "completed":
            db.delete(stale)
            db.commit()
        raise
    complete_idempotency(db, record_id=record_id, status_code=status_code, response_body=body)
    return status_code, body

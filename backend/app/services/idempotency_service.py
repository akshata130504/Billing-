"""Idempotency service to deduplicate requests and return cached responses.

Concurrency: the (organization_id, idempotency_key) unique constraint is the
arbiter. Two simultaneous requests with the same key both try to INSERT the
"processing" reservation; the loser's INSERT raises a unique violation inside
a SAVEPOINT (so its transaction stays usable), after which it re-reads the
winner's record and either replays the stored response (same status + body)
or - if the winner is still running after a short wait - answers 409. The
handler therefore runs at most once and exactly one financial record is
written; the loser never surfaces an IntegrityError as a 500.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import timedelta, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.exceptions import ConflictAppError
from backend.app.models.events import IdempotencyRecord, utcnow

# How long a duplicate request waits for the in-flight original to finish
# before answering 409, and how often it re-reads the record meanwhile.
IDEMPOTENCY_WAIT_SECONDS = 3.0
IDEMPOTENCY_POLL_SECONDS = 0.1
_MAX_RESERVE_ATTEMPTS = 20

STILL_PROCESSING_MESSAGE = "A request with this Idempotency-Key is still processing; retry shortly."
MISMATCH_MESSAGE = "Idempotency key reused with mismatched request parameters."


def _normalize_params_hash(params_hash: Optional[Any]) -> Optional[str]:
    if isinstance(params_hash, dict):
        return hashlib.sha256(json.dumps(params_hash, sort_keys=True, default=str).encode()).hexdigest()
    if params_hash is not None and not isinstance(params_hash, str):
        return str(params_hash)
    return params_hash


def _load(db: Session, organization_id: str, key: str) -> Optional[IdempotencyRecord]:
    # populate_existing: a record already in the identity map (e.g. seen as
    # "processing" on a previous poll) must be refreshed from the database.
    return db.scalars(
        select(IdempotencyRecord)
        .where(
            IdempotencyRecord.organization_id == organization_id,
            IdempotencyRecord.idempotency_key == key,
        )
        .execution_options(populate_existing=True)
    ).first()


def _is_expired(record: IdempotencyRecord, now) -> bool:
    expires = record.expires_at.replace(tzinfo=timezone.utc) if record.expires_at.tzinfo is None else record.expires_at
    current = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
    return expires <= current


def check_idempotency(
    db: Session,
    organization_id: str,
    key: str,
    request_path: str,
    request_method: str,
    params_hash: Optional[Any] = None,
    ttl_hours: int = 24,
    wait_seconds: float = 0.0,
) -> Tuple[Optional[IdempotencyRecord], bool]:
    """Check if an idempotency key was previously processed, else reserve it.

    Returns:
        (record, is_cached) where is_cached is True if a completed response is cached.

    Raises ConflictAppError (409) when the key was used with different
    parameters, or when the original request is still processing after
    ``wait_seconds``.
    """
    params_hash = _normalize_params_hash(params_hash)
    deadline = time.monotonic() + max(0.0, wait_seconds)

    for _attempt in range(_MAX_RESERVE_ATTEMPTS):
        now = utcnow()
        record = _load(db, organization_id, key)

        if record is not None and _is_expired(record, now):
            # Bulk delete: two requests racing on the same expired key must not
            # trip over each other's ORM-level delete.
            db.execute(
                delete(IdempotencyRecord)
                .where(
                    IdempotencyRecord.id == record.id,
                    IdempotencyRecord.expires_at <= now,
                )
                .execution_options(synchronize_session=False)
            )
            db.expunge(record)
            db.commit()
            record = None

        if record is not None:
            if (record.params_hash or params_hash) and record.params_hash != params_hash:
                raise ConflictAppError(MISMATCH_MESSAGE)
            if record.status == "completed":
                return record, True
            # Still processing (another request owns the key).
            if time.monotonic() < deadline:
                db.commit()  # end our read so the next poll takes a fresh snapshot
                time.sleep(IDEMPOTENCY_POLL_SECONDS)
                continue
            raise ConflictAppError(STILL_PROCESSING_MESSAGE)

        new_record = IdempotencyRecord(
            organization_id=organization_id,
            idempotency_key=key,
            request_path=request_path,
            request_method=request_method,
            params_hash=params_hash,
            status="processing",
            expires_at=now + timedelta(hours=ttl_hours),
        )
        try:
            with db.begin_nested():
                db.add(new_record)
                db.flush()
        except IntegrityError:
            # Lost the race for this key: loop and read the winner's record.
            continue
        db.commit()
        db.refresh(new_record)
        return new_record, False

    raise ConflictAppError(STILL_PROCESSING_MESSAGE)


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
    wait_seconds: Optional[float] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Run `handler` at most once per (organization, Idempotency-Key).

    Without a key the handler simply runs. With a key, a completed earlier request
    with the same parameters returns its stored response instead of re-executing
    (so a retried "record payment" never books the money twice). A concurrent
    duplicate waits briefly for the original and replays its response (same
    status code and body); if the original is still running it gets a 409. A key
    reused with different parameters is a 409. If the handler raises, the
    reservation is released so the client can retry.
    `handler` must return a JSON-serialisable dict.
    """
    if not key:
        return status_code, handler()
    key = key.strip()[:128]
    record, cached = check_idempotency(
        db,
        organization_id,
        key,
        request_path,
        request_method,
        params_hash=params,
        wait_seconds=IDEMPOTENCY_WAIT_SECONDS if wait_seconds is None else wait_seconds,
    )
    if cached:
        return int(record.status_code or status_code), dict(record.response_body or {})
    record_id = record.id
    try:
        body = handler()
    except Exception:
        db.rollback()
        db.execute(
            delete(IdempotencyRecord)
            .where(
                IdempotencyRecord.id == record_id,
                IdempotencyRecord.status != "completed",
            )
            .execution_options(synchronize_session=False)
        )
        if record in db:
            db.expunge(record)
        db.commit()
        raise
    complete_idempotency(db, record_id=record_id, status_code=status_code, response_body=body)
    return status_code, body

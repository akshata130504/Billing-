"""Durable PostgreSQL/SQLite backed job queue service with lease-based locking and retry logic."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from backend.app.core.exceptions import NotFoundAppError
from backend.app.models.base import utcnow
from backend.app.models.events import Job, JobStatus


def enqueue_job(
    db: Session,
    organization_id: str,
    job_type: str,
    payload: Optional[Dict[str, Any]] = None,
    run_at: Optional[datetime] = None,
    max_attempts: int = 5,
) -> Job:
    """Enqueues a durable background job to be picked up by worker processes."""
    if run_at is None:
        run_at = utcnow()

    job = Job(
        organization_id=organization_id,
        job_type=job_type,
        payload=payload or {},
        status=JobStatus.PENDING,
        run_at=run_at,
        max_attempts=max_attempts,
        attempts=0,
    )
    db.add(job)
    db.flush()
    return job


def claim_due_jobs(
    db: Session,
    worker_id: str,
    limit: int = 10,
    lease_seconds: int = 300,
    job_types: Optional[List[str]] = None,
) -> List[Job]:
    """Claims up to `limit` runnable jobs using lease locking.

    A job is claimable if:
    1. status == PENDING and run_at <= now
    2. status == RUNNING and locked_at < (now - lease_seconds) [crashed worker takeover]

    When ``job_types`` is given only those job types are claimed.
    """
    now = utcnow()
    lease_cutoff = now - timedelta(seconds=lease_seconds)

    # Note: For SQLite compatibility in tests and PostgreSQL in prod, we do a filtered select then lock
    query = (
        db.query(Job)
        .filter(
            or_(
                and_(Job.status == JobStatus.PENDING, Job.run_at <= now),
                and_(Job.status == JobStatus.RUNNING, Job.locked_at < lease_cutoff),
            )
        )
    )
    if job_types is not None:
        query = query.filter(Job.job_type.in_(job_types))
    query = query.order_by(Job.run_at.asc()).limit(limit)
    bind = db.get_bind() if hasattr(db, "get_bind") else getattr(db, "bind", None)
    if bind is not None and getattr(bind.dialect, "name", "") == "postgresql":
        query = query.with_for_update(skip_locked=True)
    claimable_jobs = query.all()

    claimed: List[Job] = []
    for job in claimable_jobs:
        job.status = JobStatus.RUNNING
        job.locked_at = now
        job.locked_by = worker_id
        job.attempts += 1
        claimed.append(job)

    if claimed:
        db.flush()

    return claimed


def complete_job(
    db: Session,
    job_id: str,
    worker_id: Optional[str] = None,
) -> Job:
    """Marks a claimed job as COMPLETED."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise NotFoundAppError(f"Job {job_id} not found.")

    job.status = JobStatus.COMPLETED
    job.locked_at = None
    job.locked_by = None
    db.flush()
    return job


def fail_job(
    db: Session,
    job_id: str,
    error_message: str,
    worker_id: Optional[str] = None,
    retry_delay_seconds: int = 60,
) -> Job:
    """Records a job execution failure. Re-queues or transitions to DEAD if max attempts exceeded."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise NotFoundAppError(f"Job {job_id} not found.")

    job.last_error = error_message[:2000]
    job.locked_at = None
    job.locked_by = None

    if job.attempts >= job.max_attempts:
        job.status = JobStatus.DEAD
    else:
        job.status = JobStatus.PENDING
        # Exponential or fixed backoff
        backoff_delay = retry_delay_seconds * (2 ** max(0, job.attempts - 1))
        job.run_at = utcnow() + timedelta(seconds=backoff_delay)

    db.flush()
    return job


def get_job(db: Session, job_id: str) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise NotFoundAppError(f"Job {job_id} not found.")
    return job

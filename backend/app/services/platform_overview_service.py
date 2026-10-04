"""Platform dashboard and health (docs/platform-administration-design.md section 9).

Counts and operational status only. Health never includes connection strings, hosts, credentials,
environment variables or raw error text - just states, revision ids, timestamps and counts.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app import __version__
from backend.app.core.config import settings
from backend.app.core.database import check_db_health
from backend.app.core.migrations import migration_status
from backend.app.models import Organization, OrganizationStatus
from backend.app.models.base import utcnow
from backend.app.models.events import InboxEvent, Job, JobStatus, OutboxEvent, OutboxStatus
from backend.app.models.platform import PlatformAuditLog, PlatformRole, PlatformStaff
from backend.app.services.scheduler import get_scheduler_heartbeat

RECENT_DAYS = 7
# Scheduler step counts that are safe to show (all integers; no ids, no amounts).
SCHEDULER_COUNT_KEYS = (
    "renewals", "trials_converted", "marked_overdue", "reminders_sent", "scheduled_changes_applied",
    "dunning_recovered", "recurring_expenses_processed", "skipped_org_inactive",
)


def organization_counts(db: Session) -> Dict[str, int]:
    rows = dict(db.execute(select(Organization.status, func.count(Organization.id)).group_by(Organization.status)).all())
    counts = {status.value: int(rows.get(status, 0)) for status in OrganizationStatus}
    counts["total"] = sum(counts.values())
    counts["jobs_paused"] = int(db.scalar(select(func.count(Organization.id)).where(Organization.jobs_paused.is_(True))) or 0)
    return counts


def scheduler_status(db: Session) -> Dict[str, Any]:
    interval = max(1, int(settings.SCHEDULER_INTERVAL_MINUTES or 5))
    stale_after = max(900, interval * 60 * 3)
    beat = get_scheduler_heartbeat(db)
    if beat is None:
        return {"enabled": bool(settings.SCHEDULER_ENABLED), "status": "missing", "interval_minutes": interval,
                "last_finished_at": None, "seconds_since_last_run": None, "last_error_count": None,
                "total_runs": 0, "last_counts": {}}
    age = beat.get("seconds_since_last_run")
    counts = beat.get("last_counts") or {}
    return {
        "enabled": bool(settings.SCHEDULER_ENABLED),
        "status": "ok" if age is not None and age <= stale_after else "stale",
        "interval_minutes": interval,
        "last_finished_at": beat.get("last_finished_at"),
        "seconds_since_last_run": age,
        "last_error_count": beat.get("last_error_count"),
        "total_runs": beat.get("total_runs"),
        "last_counts": {k: int(counts[k]) for k in SCHEDULER_COUNT_KEYS if isinstance(counts.get(k), int)},
    }


def health(db: Session) -> Dict[str, Any]:
    database = check_db_health()
    db_ok = database.get("status") == "connected"
    migrations = migration_status() if db_ok else {"status": "unknown", "current": None, "head": None}
    return {
        "api": {"status": "ok", "version": __version__, "environment": settings.ENVIRONMENT},
        "database": {"status": "connected" if db_ok else "unavailable"},
        "migrations": {
            "status": migrations.get("status", "unknown"),
            "current": migrations.get("current"),
            "head": migrations.get("head"),
        },
        "scheduler": scheduler_status(db) if db_ok else {"enabled": bool(settings.SCHEDULER_ENABLED), "status": "unknown"},
        "platform": {
            "auth_enabled": settings.platform_auth_enabled,
            "step_up_minutes": settings.PLATFORM_STEP_UP_MINUTES,
            "session_idle_minutes": settings.PLATFORM_SESSION_IDLE_MINUTES,
            "session_max_hours": settings.PLATFORM_SESSION_MAX_HOURS,
            "deletion_waiting_days": settings.PLATFORM_DELETION_WAITING_DAYS,
        },
        "integrations": {
            "email_configured": bool(settings.email_enabled),
            "payments_configured": bool(settings.razorpay_enabled),
        },
    }


def recent_activity(db: Session, role: PlatformRole, limit: int = 8):
    """Latest platform audit rows for the dashboard. The full audit is Administrator-only, so other
    roles see organization lifecycle events only."""
    from backend.app.services.platform_org_service import LIFECYCLE_EVENTS

    stmt = select(PlatformAuditLog)
    if role != PlatformRole.PLATFORM_ADMINISTRATOR:
        stmt = stmt.where(PlatformAuditLog.action.in_(LIFECYCLE_EVENTS))
    return db.scalars(stmt.order_by(PlatformAuditLog.occurred_at.desc(), PlatformAuditLog.id.desc()).limit(limit)).all()


def _counts_by_status(db: Session, model, enum) -> Dict[str, int]:
    rows = dict(db.execute(select(model.status, func.count(model.id)).group_by(model.status)).all())
    return {member.value: int(rows.get(member, 0)) for member in enum}


def jobs(db: Session) -> Dict[str, Any]:
    """Background work across the platform - counts only (no payloads, ids or amounts).
    Observation only: nothing here can run, retry or cancel a job."""
    day_ago = utcnow() - timedelta(hours=24)
    return {
        "scheduler": scheduler_status(db),
        "durable_jobs": _counts_by_status(db, Job, JobStatus),
        "durable_jobs_failed_24h": int(db.scalar(
            select(func.count(Job.id)).where(Job.status.in_((JobStatus.FAILED, JobStatus.DEAD)), Job.updated_at >= day_ago)
        ) or 0),
        "outbox": _counts_by_status(db, OutboxEvent, OutboxStatus),
        "webhooks_received_24h": int(db.scalar(
            select(func.count(InboxEvent.id)).where(InboxEvent.created_at >= day_ago)
        ) or 0),
        "organizations_not_running": int(db.scalar(select(func.count(Organization.id)).where(
            (Organization.status != OrganizationStatus.ACTIVE) | Organization.jobs_paused.is_(True)
        )) or 0),
    }


def dashboard(db: Session, role: PlatformRole = PlatformRole.PLATFORM_ADMINISTRATOR) -> Dict[str, Any]:
    since = utcnow() - timedelta(days=RECENT_DAYS)
    recent = db.scalars(select(Organization).order_by(Organization.created_at.desc(), Organization.id).limit(5)).all()
    snapshot = health(db)
    return {
        "organizations": organization_counts(db),
        "created_last_7_days": int(db.scalar(select(func.count(Organization.id)).where(Organization.created_at >= since)) or 0),
        "recent_organizations": [
            {"id": o.id, "name": o.name, "slug": o.slug, "status": (o.status or OrganizationStatus.ACTIVE).value,
             "created_at": o.created_at}
            for o in recent
        ],
        "staff": {
            "total": int(db.scalar(select(func.count(PlatformStaff.id))) or 0),
            "active": int(db.scalar(select(func.count(PlatformStaff.id)).where(PlatformStaff.is_active.is_(True))) or 0),
        },
        "health": {
            "api": snapshot["api"]["status"],
            "database": snapshot["database"]["status"],
            "migrations": snapshot["migrations"]["status"],
            "scheduler": snapshot["scheduler"].get("status"),
        },
        "scheduler": snapshot["scheduler"],
        "recent_activity": recent_activity(db, role),
    }

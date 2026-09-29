from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Response, status

from backend.app import __version__
from backend.app.core.alerts import send_alert
from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, check_db_health
from backend.app.core.logging import logger
from backend.app.core.migrations import migration_status
from backend.app.schemas.common import HealthResponse, ReadinessResponse

router = APIRouter()


def _as_aware(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def scheduler_heartbeat_status() -> Dict[str, Any]:
    """Staleness of the dedicated scheduler's heartbeat (informational, never fails readiness).

    ``get_scheduler_heartbeat(db)`` lives in backend/app/services/scheduler.py. It may return a
    datetime, an ISO string, a dict with a ``last_heartbeat``/``last_run_at`` key, or None. Older
    builds without the function report ``status="unavailable"``.
    """
    interval_min = max(1, int(getattr(settings, "SCHEDULER_INTERVAL_MINUTES", 5) or 5))
    # Stale after three missed intervals (minimum 15 minutes).
    stale_after = int(getattr(settings, "SCHEDULER_HEARTBEAT_STALE_SECONDS", 0) or max(900, interval_min * 60 * 3))
    try:
        from backend.app.services.scheduler import get_scheduler_heartbeat  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        return {"status": "unavailable", "detail": "heartbeat not implemented in this build"}

    try:
        db = SessionLocal()
        try:
            raw = get_scheduler_heartbeat(db)
        finally:
            db.close()
    except Exception as exc:  # never let the probe itself crash
        logger.warning("Scheduler heartbeat lookup failed: %s", exc)
        return {"status": "unknown", "detail": "heartbeat lookup failed"}

    extra: Dict[str, Any] = {}
    if isinstance(raw, dict):
        if "last_error_count" in raw:
            extra["last_error_count"] = raw.get("last_error_count")
        raw = (
            raw.get("last_finished_at")
            or raw.get("last_heartbeat")
            or raw.get("last_run_at")
            or raw.get("timestamp")
        )
    last = _as_aware(raw)
    if last is None:
        return {"status": "missing", "last_heartbeat": None, "stale_after_seconds": stale_after}
    age = int((datetime.now(timezone.utc) - last).total_seconds())
    return {
        "status": "ok" if age <= stale_after else "stale",
        "last_heartbeat": last.isoformat(),
        "age_seconds": age,
        "stale_after_seconds": stale_after,
        **extra,
    }


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Health & Status Check",
    description="Returns current service status (healthy, or degraded when the database is unreachable), API version, environment details, and database connectivity state.",
)
def health_check() -> HealthResponse:
    db_health = check_db_health()
    overall_status = "healthy" if db_health.get("status") == "connected" else "degraded"
    return HealthResponse(
        status=overall_status,
        project_name=settings.PROJECT_NAME,
        version=__version__,
        environment=settings.ENVIRONMENT,
        database=db_health,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    responses={503: {"model": ReadinessResponse, "description": "Not ready: database down or migrations behind"}},
    summary="Readiness probe (deep)",
    description=(
        "Deep readiness check for load balancers and deploy gates. Hard checks: the database "
        "must be reachable and the schema must be at the Alembic head revision. Returns 503 when "
        "either fails. Also reports (informationally only) whether the background scheduler, "
        "Razorpay and SMTP are configured. Use /health for a shallow liveness probe."
    ),
)
def readiness_check(response: Response) -> ReadinessResponse:
    db_health = check_db_health()
    db_ok = db_health.get("status") == "connected"

    migrations = migration_status() if db_ok else {"status": "unknown", "current": None, "head": None}
    migrations_ok = migrations.get("status") == "at_head"

    failures = []
    if not db_ok:
        failures.append("database")
        # Deduplicated (ALERT_DEDUP_SECONDS) and non-blocking; the probe runs every few seconds.
        send_alert(
            "database.unreachable",
            "Readiness probe cannot reach the database",
            {"dialect": db_health.get("dialect"), "error": db_health.get("error")},
            severity="critical",
        )
    if not migrations_ok:
        failures.append("migrations")

    ready = not failures
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        ready=ready,
        project_name=settings.PROJECT_NAME,
        version=__version__,
        environment=settings.ENVIRONMENT,
        checks={"database": db_health, "migrations": migrations},
        features={
            # Informational: these never fail the probe, but they are the settings that
            # most often silently differ between environments.
            "scheduler_enabled": settings.SCHEDULER_ENABLED,
            "razorpay_configured": settings.razorpay_enabled,
            "smtp_configured": settings.email_enabled,
            "sentry_enabled": settings.sentry_enabled,
            # Heartbeat of the separate scheduler container. Reported only: the API is ready
            # to serve even when the scheduler is down, so this never adds to `failures`.
            "scheduler_heartbeat": scheduler_heartbeat_status() if db_ok else {"status": "unknown"},
        },
        failures=failures,
    )

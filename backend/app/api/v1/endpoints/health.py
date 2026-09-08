from fastapi import APIRouter, Response, status

from backend.app import __version__
from backend.app.core.config import settings
from backend.app.core.database import check_db_health
from backend.app.core.migrations import migration_status
from backend.app.schemas.common import HealthResponse, ReadinessResponse

router = APIRouter()


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
        },
        failures=failures,
    )

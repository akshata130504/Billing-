from fastapi import APIRouter, status
from backend.app import __version__
from backend.app.core.config import settings
from backend.app.core.database import check_db_health
from backend.app.schemas.common import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Health & Status Check",
    description="Returns current service status, API version, environment details, and database connectivity state.",
)
def health_check() -> HealthResponse:
    db_health = check_db_health()
    return HealthResponse(
        status="healthy",
        project_name=settings.PROJECT_NAME,
        version=__version__,
        environment=settings.ENVIRONMENT,
        database=db_health,
    )

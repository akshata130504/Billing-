from datetime import datetime, timezone
from typing import Generic, List, Optional, TypeVar, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    status: str = Field(default="healthy", description="Application service status")
    project_name: str = Field(..., description="Project brand name")
    version: str = Field(..., description="Application version")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    environment: str = Field(..., description="Active runtime environment")
    database: Dict[str, Any] = Field(..., description="Database connection health")

    model_config = ConfigDict(from_attributes=True)


class ReadinessResponse(BaseModel):
    """Deep readiness probe. `ready` is false whenever the process must not take traffic."""

    ready: bool = Field(..., description="True only when every hard check passed")
    project_name: str = Field(..., description="Project brand name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Active runtime environment")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    checks: Dict[str, Any] = Field(..., description="Hard checks: database and migrations")
    features: Dict[str, Any] = Field(..., description="Informational: scheduler, razorpay, smtp, sentry")
    failures: List[str] = Field(default_factory=list, description="Names of the hard checks that failed")

    model_config = ConfigDict(from_attributes=True)


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String

from backend.app.core.database import Base  # noqa: F401  (re-exported for convenience)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    """Abstract mixin adding created_at and updated_at timestamps."""

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class TenantMixin:
    """Abstract mixin adding multi-tenant organization scoping.

    Every business table carries organization_id and every query in the
    repositories/services layer MUST filter on it.
    """

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Abstract mixin for UUID-based primary keys."""

    id = Column(String(36), primary_key=True, default=new_uuid)

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, String
from backend.app.core.database import Base


class TimestampMixin:
    """Abstract mixin adding created_at and updated_at timestamps."""
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TenantMixin:
    """Abstract mixin adding multi-tenant organization scoping."""
    organization_id = Column(
        String(36),
        index=True,
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Abstract mixin for UUID-based primary keys."""
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )

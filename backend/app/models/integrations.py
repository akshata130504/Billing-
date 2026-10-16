"""Organization integration configurations model."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OrganizationIntegration(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Stores tenant-level integration credentials and settings (encrypted at rest)."""

    __tablename__ = "organization_integrations"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider", name="uq_org_integration_provider"),
        # Named as in migration 0011 (d1e2f3a4b5c6); index=True would auto-name them
        # ix_organization_integrations_* and create a second, duplicate index per column.
        Index("ix_org_integrations_org_id", "organization_id"),
        Index("ix_org_integrations_provider", "provider"),
    )

    # Overrides TenantMixin.organization_id only to drop its index=True (see __table_args__).
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    provider = Column(String(50), nullable=False)  # razorpay, smtp, webhook, storage, crm, accounting
    is_connected = Column(Boolean, nullable=False, default=False)
    encrypted_config = Column(Text, nullable=True)  # Fernet AES-encrypted JSON string of credentials
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    status_message = Column(String(255), nullable=True)

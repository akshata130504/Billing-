"""Organization integration configurations model."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class OrganizationIntegration(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Stores tenant-level integration credentials and settings (encrypted at rest)."""

    __tablename__ = "organization_integrations"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider", name="uq_org_integration_provider"),
    )

    provider = Column(String(50), nullable=False, index=True)  # razorpay, smtp, webhook, storage, crm, accounting
    is_connected = Column(Boolean, nullable=False, default=False)
    encrypted_config = Column(Text, nullable=True)  # Fernet AES-encrypted JSON string of credentials
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    status_message = Column(String(255), nullable=True)

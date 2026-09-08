"""Client platform device registration: desktop/mobile device trust and push-token state."""
import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, UniqueConstraint

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DevicePlatform(str, enum.Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    ANDROID = "android"
    IOS = "ios"


class DeviceTrustStatus(str, enum.Enum):
    PENDING = "pending"
    TRUSTED = "trusted"
    REVOKED = "revoked"


class Device(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "device_identifier", name="uq_device_identifier_per_user"),
    )

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_identifier = Column(String(255), nullable=False)
    device_name = Column(String(150), nullable=True)
    platform = Column(Enum(DevicePlatform, name="device_platform"), nullable=False)
    os_version = Column(String(50), nullable=True)
    app_version = Column(String(50), nullable=True)
    push_token = Column(String(500), nullable=True)
    trust_status = Column(
        Enum(DeviceTrustStatus, name="device_trust_status"),
        nullable=False,
        default=DeviceTrustStatus.PENDING,
        index=True,
    )
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    trusted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_reason = Column(String(255), nullable=True)

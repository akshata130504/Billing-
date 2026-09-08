"""Pydantic schemas for client-platform device registration, native auth exchange, and mobile bootstrap."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.devices import DevicePlatform, DeviceTrustStatus
from backend.app.schemas.auth import AuthTokens, MembershipOut, OrganizationSummary, UserOut
from backend.app.schemas.organization import EmailAddress, OrganizationOut, UTCDateTime


class DeviceRegisterIn(BaseModel):
    device_identifier: str = Field(..., min_length=1, max_length=255)
    platform: DevicePlatform
    device_name: Optional[str] = Field(None, max_length=150)
    os_version: Optional[str] = Field(None, max_length=50)
    app_version: Optional[str] = Field(None, max_length=50)
    push_token: Optional[str] = Field(None, max_length=500)


class DeviceOut(BaseModel):
    id: str
    user_id: str
    device_identifier: str
    device_name: Optional[str] = None
    platform: DevicePlatform
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    trust_status: DeviceTrustStatus
    last_seen_at: Optional[UTCDateTime] = None
    trusted_at: Optional[UTCDateTime] = None
    revoked_at: Optional[UTCDateTime] = None
    created_at: UTCDateTime
    updated_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True)


class NativeExchangeRequest(BaseModel):
    email: EmailAddress
    password: str = Field(..., min_length=1, max_length=256)
    device: DeviceRegisterIn


class NativeExchangeResponse(AuthTokens):
    device: DeviceOut


class MobileBootstrapOut(BaseModel):
    user: UserOut
    organization: OrganizationOut
    membership: MembershipOut
    organizations: List[OrganizationSummary] = Field(description="Every organization the user is an active member of")
    server_time: UTCDateTime

"""Platform (Rooman staff) authentication request/response models.

Responses never include password hashes, TOTP data, or any token value: the session
travels in HttpOnly cookies set by the endpoints.
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.organization import EmailAddress, UTCDateTime


class PlatformLoginRequest(BaseModel):
    email: EmailAddress
    password: str = Field(min_length=1, max_length=256)


class PlatformStaffOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    last_login_at: Optional[UTCDateTime] = None


class PlatformMeOut(BaseModel):
    staff: PlatformStaffOut
    session_id: str
    session_expires_at: UTCDateTime
    access_expires_in: int


class PlatformSessionOut(BaseModel):
    id: str
    created_at: UTCDateTime
    last_used_at: UTCDateTime
    expires_at: UTCDateTime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    current: bool = False


class PlatformSessionsOut(BaseModel):
    sessions: List[PlatformSessionOut]


class PlatformLogoutAllOut(BaseModel):
    sessions_revoked: int


class PlatformStepUpRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class PlatformStepUpOut(BaseModel):
    """When the step-up on this session lapses. Deliberately no token: step-up is server-side state."""

    step_up_expires_at: UTCDateTime
    expires_in: int

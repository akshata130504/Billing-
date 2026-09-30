"""Platform (Rooman staff) authentication request/response models.

Responses never include password hashes, TOTP secrets or state, or any token value: the session
travels in HttpOnly cookies set by the endpoints.
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.organization import EmailAddress, UTCDateTime


class PlatformLoginRequest(BaseModel):
    email: EmailAddress
    password: str = Field(min_length=1, max_length=256)


class PlatformLoginChallengeOut(BaseModel):
    two_factor_required: bool = True
    challenge_token: str
    expires_in: int


class PlatformTwoFactorRequest(BaseModel):
    challenge_token: str = Field(min_length=1, max_length=512)
    code: str = Field(min_length=6, max_length=10)


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

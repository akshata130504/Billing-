"""Authentication request/response models (contract §2)."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models import MemberRole, MembershipStatus
from backend.app.schemas.organization import EmailAddress, OrganizationOut, UTCDateTime


# --- requests ------------------------------------------------------------------------


class SignupRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailAddress
    password: str = Field(min_length=1, max_length=256)


class LoginRequest(BaseModel):
    email: EmailAddress
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class SwitchOrganizationRequest(BaseModel):
    organization_id: str = Field(min_length=1, max_length=36)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
    # Optional extension: the caller's own refresh token. When given it survives while every
    # other session of the user is revoked; otherwise all refresh tokens are revoked.
    refresh_token: Optional[str] = Field(default=None, max_length=512)


class ForgotPasswordRequest(BaseModel):
    email: EmailAddress


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1, max_length=256)


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    full_name: Optional[str] = Field(default=None, max_length=200)
    password: Optional[str] = Field(default=None, max_length=256)


# --- responses -----------------------------------------------------------------------


class AuthTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    last_login_at: Optional[UTCDateTime] = None
    created_at: UTCDateTime


class MembershipOut(BaseModel):
    id: str
    role: MemberRole
    status: MembershipStatus
    joined_at: Optional[UTCDateTime] = None


class OrganizationSummary(BaseModel):
    id: str
    name: str
    slug: str
    role: MemberRole


class MeResponse(BaseModel):
    user: UserOut
    organization: OrganizationOut
    membership: MembershipOut
    organizations: List[OrganizationSummary] = Field(description="Every organization the user is an active member of")


class SignupResponse(AuthTokens):
    me: MeResponse


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_url: Optional[str] = Field(default=None, description="Only present when SMTP is not configured.")


class InvitationOut(BaseModel):
    email: str
    organization_name: str
    role: MemberRole
    invited_by: str
    expires_at: UTCDateTime
    user_exists: bool

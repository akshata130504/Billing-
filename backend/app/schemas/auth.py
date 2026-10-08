"""Authentication request/response models (contract §2)."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from backend.app.models import MemberRole, MembershipStatus
from backend.app.schemas.organization import EmailAddress, OrganizationOut, UTCDateTime
from backend.app.schemas.subscription_access import OrganizationAccess
from backend.app.schemas.validators import validate_phone_number, validate_sensible_name


# --- requests ------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailAddress
    password: str = Field(min_length=1, max_length=256)


class MfaLoginRequest(BaseModel):
    mfa_token: str = Field(min_length=1, max_length=2048)
    code: str = Field(min_length=6, max_length=8)


class TotpEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TotpDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=8)


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
    # New accounts: the password to set. Existing accounts: their current password (required).
    password: Optional[str] = Field(default=None, max_length=256)
    # Existing accounts with two-factor authentication on.
    totp_code: Optional[str] = Field(default=None, max_length=8)


# --- responses -----------------------------------------------------------------------


class AuthTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class LoginResponse(BaseModel):
    """Either a token pair, or (two-factor accounts) an MFA challenge for POST /auth/login/mfa."""

    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: Optional[str] = None
    expires_in: Optional[int] = Field(default=None, description="Access token (or MFA token) lifetime in seconds")
    mfa_required: bool = False
    mfa_token: Optional[str] = None


class TotpSetupResponse(BaseModel):
    secret: str = Field(description="Base32 seed to type into an authenticator app")
    otpauth_uri: str = Field(description="otpauth:// URI (render as a QR code)")


class SessionOut(BaseModel):
    id: str
    organization_id: Optional[str] = None
    created_at: UTCDateTime
    last_active_at: UTCDateTime
    expires_at: UTCDateTime
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    current: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    last_login_at: Optional[UTCDateTime] = None
    created_at: UTCDateTime
    totp_enabled_at: Optional[UTCDateTime] = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def two_factor_enabled(self) -> bool:
        return self.totp_enabled_at is not None


class UserProfileUpdate(BaseModel):
    """Fields a user may change on their own profile.

    Email is deliberately excluded: changing it is an identity change that has to
    go through verification, not a profile edit.
    """

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=40)

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, v):
        if v is None:
            return v
        return validate_sensible_name(v, "Full name")

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return validate_phone_number(v)


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
    access: Optional[OrganizationAccess] = Field(default=None, description="Trial state, modules and seats (API-enforced)")


class SignupResponse(AuthTokens):
    me: MeResponse


class ForgotPasswordResponse(BaseModel):
    message: str


class InvitationOut(BaseModel):
    email: str
    organization_name: str
    role: MemberRole
    invited_by: str
    expires_at: UTCDateTime
    user_exists: bool


class SignupVerificationRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailAddress
    # Optional: the sign-up page asks for the password only after the email is verified. When
    # present (older clients) the pending signup is bound to it, as before.
    password: Optional[str] = Field(default=None, min_length=1, max_length=256)


class SignupConfirmEmailRequest(BaseModel):
    email: EmailAddress
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class SignupConfirmEmailResponse(BaseModel):
    """Proof that the mailbox was verified; redeemed by /signup/complete together with a password."""

    verification_token: str
    expires_in_seconds: int


class SignupCompleteRequest(BaseModel):
    email: EmailAddress
    verification_token: str = Field(min_length=1, max_length=2048)
    organization_name: str = Field(min_length=1, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class SignupVerifyOtpRequest(BaseModel):
    email: EmailAddress
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    # Must match the password submitted with request-verification.
    password: str = Field(min_length=1, max_length=256)


class ResendOtpRequest(BaseModel):
    email: EmailAddress


class SignupVerificationResponse(BaseModel):
    message: str
    email: str
    expires_in_seconds: int = 600
    resend_cooldown_seconds: int = 60


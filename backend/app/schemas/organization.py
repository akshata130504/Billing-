"""Organization and team request/response models (contract §3)."""
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from backend.app.models import MemberRole, MembershipStatus
from backend.app.schemas.common_refs import UserRef, money_str
from backend.app.schemas.validators import (
    validate_gstin_format,
    validate_pan_format,
    validate_phone_number,
    validate_website_url,
)


# --- shared scalar types -----------------------------------------------------------


def ensure_utc(value):
    """SQLite hands back naive datetimes for DateTime(timezone=True); label them UTC."""
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


UTCDateTime = Annotated[datetime, BeforeValidator(ensure_utc)]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    """Trim + lower-case. Deliberately permissive about TLDs (accepts .test/.local used in-house)."""
    value = (value or "").strip().lower()
    if not _EMAIL_RE.match(value) or len(value) > 255:
        raise ValueError("value is not a valid email address")
    return value


EmailAddress = Annotated[str, AfterValidator(normalize_email)]


# --- Organization ------------------------------------------------------------------


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    legal_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: str
    gstin: Optional[str] = None
    pan: Optional[str] = None
    default_currency: str
    timezone: str
    invoice_prefix: str
    invoice_next_number: int
    quote_prefix: str
    quote_next_number: int
    payment_prefix: str
    payment_next_number: int
    subscription_prefix: str
    subscription_next_number: int
    customer_prefix: str
    customer_next_number: int
    default_payment_terms_days: int
    default_tax_rate_pct: str
    discount_approval_threshold_pct: str
    invoice_notes: Optional[str] = None
    invoice_terms: Optional[str] = None
    logo_url: Optional[str] = None
    created_at: UTCDateTime
    updated_at: UTCDateTime

    @field_validator("default_tax_rate_pct", "discount_approval_threshold_pct", mode="before")
    @classmethod
    def _decimals_as_strings(cls, value):
        return money_str(value) if value is not None else value


class OrganizationUpdate(BaseModel):
    """Partial update. Semantic checks (ISO codes, ranges, sequences) live in the service."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=200)
    legal_name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=40)
    website: Optional[str] = Field(default=None, max_length=255)
    address_line1: Optional[str] = Field(default=None, max_length=255)
    address_line2: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=120)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, max_length=10)
    gstin: Optional[str] = Field(default=None, max_length=20)
    pan: Optional[str] = Field(default=None, max_length=20)
    default_currency: Optional[str] = Field(default=None, max_length=10)
    timezone: Optional[str] = Field(default=None, max_length=64)
    invoice_prefix: Optional[str] = Field(default=None, max_length=12)
    invoice_next_number: Optional[int] = None
    quote_prefix: Optional[str] = Field(default=None, max_length=12)
    quote_next_number: Optional[int] = None
    payment_prefix: Optional[str] = Field(default=None, max_length=12)
    payment_next_number: Optional[int] = None
    subscription_prefix: Optional[str] = Field(default=None, max_length=12)
    subscription_next_number: Optional[int] = None
    customer_prefix: Optional[str] = Field(default=None, max_length=12)
    customer_next_number: Optional[int] = None
    default_payment_terms_days: Optional[int] = None
    default_tax_rate_pct: Optional[Decimal] = None
    discount_approval_threshold_pct: Optional[Decimal] = None
    invoice_notes: Optional[str] = Field(default=None, max_length=5000)
    invoice_terms: Optional[str] = Field(default=None, max_length=5000)
    logo_url: Optional[str] = Field(default=None, max_length=500)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return validate_phone_number(v)

    @field_validator("website")
    @classmethod
    def _website(cls, v):
        return validate_website_url(v)

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v):
        return validate_gstin_format(v)

    @field_validator("pan")
    @classmethod
    def _pan(cls, v):
        return validate_pan_format(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        if v is None or v == "":
            return v
        return normalize_email(v)


# --- Team --------------------------------------------------------------------------


class TeamMember(BaseModel):
    id: str = Field(description="Membership id")
    user: UserRef
    role: MemberRole
    status: MembershipStatus
    invited_by: Optional[UserRef] = None
    invite_expires_at: Optional[UTCDateTime] = None
    accepted_at: Optional[UTCDateTime] = None
    created_at: UTCDateTime


class TeamMemberInvited(TeamMember):
    invite_url: Optional[str] = Field(default=None, description="Development only: present when the email could not be sent and the invitee is a brand-new (password-less) user.")
    email_delivered: Optional[bool] = Field(default=None, description="True if invitation email was delivered via SMTP.")


class TeamInviteRequest(BaseModel):
    email: EmailAddress
    role: MemberRole
    full_name: Optional[str] = Field(default=None, max_length=200)


class TeamRoleUpdate(BaseModel):
    role: MemberRole


TeamList = List[TeamMember]

__all__ = [
    "UTCDateTime",
    "EmailAddress",
    "ensure_utc",
    "normalize_email",
    "OrganizationOut",
    "OrganizationUpdate",
    "UserRef",
    "TeamMember",
    "TeamMemberInvited",
    "TeamInviteRequest",
    "TeamRoleUpdate",
    "TeamList",
]

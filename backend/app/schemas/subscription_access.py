"""Trial, subscription request and entitlement API models (strict: unknown fields are refused)."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.organization import UTCDateTime

BillingCycleIn = Literal["monthly", "quarterly", "annual"]
MAX_SEATS = 10000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrganizationAccess(BaseModel):
    """What the organization may use (the API enforces it; the SPA only mirrors it)."""

    status: str
    trial_started_at: Optional[UTCDateTime] = None
    trial_ends_at: Optional[UTCDateTime] = None
    module_access: Literal["unrestricted", "trial", "entitled"]
    modules: List[str]
    nav_items: List[str]
    seat_limit: Optional[int] = None
    seats_used: int


class ModuleOut(BaseModel):
    key: str
    label: str
    description: str
    base: bool
    requires: List[str]


def _clean_modules(value: List[str]) -> List[str]:
    from backend.app.core.entitlements import registry

    reg = registry()
    out: List[str] = []
    for key in value:
        if key not in reg.by_key:
            raise ValueError(f"Unknown module '{key}'.")
        if key not in out and not reg.by_key[key].base:
            out.append(key)
    return out


def _clean_text(value: Optional[str]) -> Optional[str]:
    text = " ".join((value or "").split())
    return text or None


class SubscriptionRequestCreate(_Strict):
    modules: List[str] = Field(default_factory=list, max_length=50)
    seats: int = Field(ge=1, le=MAX_SEATS)
    billing_cycle: BillingCycleIn
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("modules")
    @classmethod
    def _modules(cls, v):
        return _clean_modules(v)

    @field_validator("notes")
    @classmethod
    def _notes(cls, v):
        return _clean_text(v)


class SubscriptionRequestOut(BaseModel):
    id: str
    organization_id: str
    status: str
    modules: List[str]
    seats: int
    billing_cycle: str
    notes: Optional[str] = None
    created_at: UTCDateTime
    reviewed_at: Optional[UTCDateTime] = None
    decision_reason: Optional[str] = None
    approved_modules: Optional[List[str]] = None
    approved_seats: Optional[int] = None
    approved_billing_cycle: Optional[str] = None


class TenantSubscriptionState(BaseModel):
    access: OrganizationAccess
    modules: List[ModuleOut]
    current_request: Optional[SubscriptionRequestOut] = None
    history: List[SubscriptionRequestOut]


# --- platform console -------------------------------------------------------------------------


class PlatformSubscriptionRequestOut(SubscriptionRequestOut):
    organization_name: str
    organization_slug: str
    organization_status: str
    trial_ends_at: Optional[UTCDateTime] = None
    requested_by_email: Optional[str] = None
    requested_by_name: Optional[str] = None
    seats_used: int = 0


class PlatformSubscriptionRequestPage(BaseModel):
    items: List[PlatformSubscriptionRequestOut]
    total: int
    page: int
    page_size: int


class ApproveSubscriptionRequest(_Strict):
    """Approve as requested, or modify modules / seats / billing cycle before approving."""

    modules: Optional[List[str]] = Field(default=None, max_length=50)
    seats: Optional[int] = Field(default=None, ge=1, le=MAX_SEATS)
    billing_cycle: Optional[BillingCycleIn] = None
    reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("modules")
    @classmethod
    def _modules(cls, v):
        return None if v is None else _clean_modules(v)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        return _clean_text(v)


class RejectSubscriptionRequest(_Strict):
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        text = _clean_text(v) or ""
        if len(text) < 10:
            raise ValueError("A reason of at least 10 characters is required.")
        return text


class UpdateEntitlements(_Strict):
    """Platform Administrator edit of an ACTIVE organization's modules and seat limit."""

    modules: List[str] = Field(max_length=50)
    seat_limit: Optional[int] = Field(default=None, ge=1, le=MAX_SEATS)
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("modules")
    @classmethod
    def _modules(cls, v):
        return _clean_modules(v)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        text = _clean_text(v) or ""
        if len(text) < 10:
            raise ValueError("A reason of at least 10 characters is required.")
        return text


class OrganizationEntitlementsOut(BaseModel):
    organization_id: str
    module_access: str
    modules: List[str]
    seat_limit: Optional[int] = None
    seats_used: int
    trial_ends_at: Optional[UTCDateTime] = None

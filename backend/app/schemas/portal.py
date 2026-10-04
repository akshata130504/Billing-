"""Pydantic schemas for Customer Portal settings, authentication, and self-service views."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from backend.app.schemas.validators import validate_slug_format


class CustomerPortalSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    portal_name: str
    portal_url_slug: Optional[str] = None
    banner_message: Optional[str] = None
    auto_invite_enabled: bool
    mfa_enabled: bool
    prevent_duplicate_payments: bool
    allow_self_signup: bool
    allow_document_upload: bool
    allow_document_forwarding: bool
    allow_save_payment_methods: bool
    save_payment_method_default: bool
    prevent_deselecting_save_payment: bool
    enable_identity_verification_public_links: bool
    trials_allow_customer_extension: bool
    trials_max_extensions: int
    trials_activate_immediately: bool
    created_at: datetime
    updated_at: datetime


class CustomerPortalSettingsUpdate(BaseModel):
    portal_name: Optional[str] = Field(None, max_length=100)
    portal_url_slug: Optional[str] = Field(None, max_length=64)

    @field_validator("portal_url_slug")
    @classmethod
    def _slug(cls, v):
        return validate_slug_format(v, "Portal URL slug")
    banner_message: Optional[str] = None
    auto_invite_enabled: Optional[bool] = None
    prevent_duplicate_payments: Optional[bool] = None
    allow_self_signup: Optional[bool] = None
    allow_document_upload: Optional[bool] = None
    allow_document_forwarding: Optional[bool] = None
    allow_save_payment_methods: Optional[bool] = None
    save_payment_method_default: Optional[bool] = None
    prevent_deselecting_save_payment: Optional[bool] = None
    enable_identity_verification_public_links: Optional[bool] = None
    trials_allow_customer_extension: Optional[bool] = None
    trials_max_extensions: Optional[int] = Field(None, ge=0, le=10)
    trials_activate_immediately: Optional[bool] = None


class PortalSignupIn(BaseModel):
    organization_id: str
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str = Field(..., max_length=200)
    customer_id: Optional[str] = None


class PortalLoginIn(BaseModel):
    organization_id: Optional[str] = None
    email: EmailStr
    password: str
    mfa_code: Optional[str] = None


class PortalInvitationValidateOut(BaseModel):
    valid: bool
    email: str
    customer_id: str
    customer_name: str
    organization_id: str
    organization_name: str
    portal_name: str
    expires_at: datetime


class PortalActivateIn(BaseModel):
    token: str
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = Field(None, max_length=200)


class CustomerPortalInviteIn(BaseModel):
    email: Optional[EmailStr] = None


class CustomerPortalInvitationOut(BaseModel):
    id: str
    customer_id: str
    email: str
    expires_at: datetime
    created_at: datetime
    invited_by_name: Optional[str] = None
    invite_url: Optional[str] = None
    status: str


class CustomerPortalAccessStatusOut(BaseModel):
    status: str  # not_invited | invitation_pending | active | revoked
    user: Optional[PortalUserOut] = None
    invitation: Optional[CustomerPortalInvitationOut] = None
    portal_url: Optional[str] = None


class PortalUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    customer_id: str
    email: str
    display_name: str
    is_active: bool
    mfa_enabled: bool
    last_login_at: Optional[datetime] = None


class PortalAuthOut(BaseModel):
    token: str
    expires_at: datetime
    user: PortalUserOut
    customer_display_name: str


class PortalDashboardOut(BaseModel):
    portal_name: str
    banner_message: Optional[str] = None
    customer_name: str
    customer_email: Optional[str] = None
    active_subscriptions_count: int
    open_invoices_count: int
    total_outstanding_amount: Decimal
    recent_invoices: List[Dict[str, Any]] = Field(default_factory=list)
    subscriptions: List[Dict[str, Any]] = Field(default_factory=list)
    saved_payment_methods: List[Dict[str, Any]] = Field(default_factory=list)
    # Set when the merchant is suspended: the portal is read-only (no payments, card or plan changes).
    read_only_reason: Optional[str] = None


class PortalProfileUpdateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    website: Optional[str] = Field(default=None, max_length=255)
    billing_address_line1: Optional[str] = Field(default=None, max_length=255)
    billing_address_line2: Optional[str] = Field(default=None, max_length=255)
    billing_city: Optional[str] = Field(default=None, max_length=100)
    billing_state: Optional[str] = Field(default=None, max_length=100)
    billing_postal_code: Optional[str] = Field(default=None, max_length=20)
    billing_country: Optional[str] = Field(default=None, max_length=100)
    shipping_address_line1: Optional[str] = Field(default=None, max_length=255)
    shipping_address_line2: Optional[str] = Field(default=None, max_length=255)
    shipping_city: Optional[str] = Field(default=None, max_length=100)
    shipping_state: Optional[str] = Field(default=None, max_length=100)
    shipping_postal_code: Optional[str] = Field(default=None, max_length=20)
    shipping_country: Optional[str] = Field(default=None, max_length=100)
    user_display_name: Optional[str] = Field(default=None, min_length=1, max_length=120)

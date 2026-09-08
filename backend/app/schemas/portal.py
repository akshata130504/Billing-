"""Pydantic schemas for Customer Portal settings, authentication, and self-service views."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
    banner_message: Optional[str] = None
    auto_invite_enabled: Optional[bool] = None
    mfa_enabled: Optional[bool] = None
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
    organization_id: str
    email: EmailStr
    password: str
    mfa_code: Optional[str] = None


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

"""Pydantic schemas for Hosted Payment Pages and Checkout Sessions."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.validators import validate_image_url, validate_redirect_url


class CheckoutTemplateCreate(BaseModel):
    name: str = Field(..., max_length=100)
    template_type: str = Field("single_page", description="single_page or multi_page")
    primary_color: str = Field("#2563eb", max_length=20)
    accent_color: str = Field("#1e40af", max_length=20)
    logo_url: Optional[str] = Field(None, max_length=500)
    button_text: str = Field("Pay Now", max_length=50)
    allow_quantity_edit: bool = False
    show_order_summary: bool = True
    redirect_url: Optional[str] = Field(None, max_length=500)
    thank_you_message: Optional[str] = None
    error_message_template: Optional[str] = Field(None, max_length=255)
    custom_fields: Optional[Dict[str, Any]] = None
    is_default: bool = False

    @field_validator("redirect_url")
    @classmethod
    def _redirect_url(cls, v: Optional[str]) -> Optional[str]:
        return validate_redirect_url(v)

    @field_validator("logo_url")
    @classmethod
    def _logo_url(cls, v: Optional[str]) -> Optional[str]:
        return validate_image_url(v)


class CheckoutTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    template_type: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    logo_url: Optional[str] = None
    button_text: Optional[str] = None
    allow_quantity_edit: Optional[bool] = None
    show_order_summary: Optional[bool] = None
    redirect_url: Optional[str] = None
    thank_you_message: Optional[str] = None
    error_message_template: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None

    @field_validator("redirect_url")
    @classmethod
    def _redirect_url(cls, v: Optional[str]) -> Optional[str]:
        return validate_redirect_url(v)

    @field_validator("logo_url")
    @classmethod
    def _logo_url(cls, v: Optional[str]) -> Optional[str]:
        return validate_image_url(v)


class CheckoutTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    template_type: str
    primary_color: str
    accent_color: str
    logo_url: Optional[str] = None
    button_text: str
    allow_quantity_edit: bool
    show_order_summary: bool
    redirect_url: Optional[str] = None
    thank_you_message: Optional[str] = None
    error_message_template: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CheckoutSessionCreate(BaseModel):
    purpose: str = Field(
        "invoice_payment",
        description="invoice_payment, new_subscription, update_subscription, update_card, one_time_addon, add_payment_method",
    )
    template_id: Optional[str] = None
    customer_id: Optional[str] = None
    invoice_id: Optional[str] = None
    subscription_id: Optional[str] = None
    plan_id: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = "INR"
    expires_in_hours: int = Field(1, ge=1, le=168, description="Session validity duration in hours")
    save_payment_method: bool = False
    metadata_snapshot: Optional[Dict[str, Any]] = None


class CheckoutSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    # The raw bearer token (and a usable checkout_url) is only returned when the
    # session is created. Listings return a non-secret display reference and no URL.
    token: str
    checkout_url: Optional[str] = None
    purpose: str
    status: str
    amount: Decimal
    currency: str
    expires_at: datetime
    customer_id: Optional[str] = None
    invoice_id: Optional[str] = None
    subscription_id: Optional[str] = None
    plan_id: Optional[str] = None
    payment_attempt_id: Optional[str] = None
    payment_id: Optional[str] = None
    save_payment_method: bool
    completed_at: Optional[datetime] = None
    created_at: datetime


class PublicCheckoutView(BaseModel):
    token: str
    purpose: str
    status: str
    amount: Decimal
    currency: str
    expires_at: datetime
    is_expired: bool
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    item_description: str
    organization_name: str
    branding: Dict[str, Any]
    save_payment_method_default: bool
    allow_save_payment_methods: bool
    prevent_deselecting_save_payment: bool
    gateway: str = "razorpay"
    gateway_order_id: Optional[str] = None
    gateway_key_id: Optional[str] = None
    # Razorpay customer (cust_...) - pass to Checkout with save=1 to let the customer save the card.
    gateway_customer_id: Optional[str] = None
    gateway_available: bool = False
    gateway_message: Optional[str] = None


class CheckoutConfirmIn(BaseModel):
    payment_method_type: str = Field("card", description="card, upi, netbanking")
    gateway: Optional[str] = Field("razorpay", description="Only 'razorpay' is accepted on the public confirm endpoint.")
    razorpay_payment_id: Optional[str] = Field(None, description="Cryptographic payment ID from Razorpay")
    razorpay_order_id: Optional[str] = Field(None, description="Order ID from Razorpay")
    razorpay_signature: Optional[str] = Field(None, description="HMAC-SHA256 signature from Razorpay")
    gateway_token: Optional[str] = Field(None, description="Not accepted on the public endpoint (rejected with 400).")
    # Ignored: saved-card details always come from the gateway, never the browser.
    card_last4: Optional[str] = None
    card_brand: Optional[str] = None
    save_payment_method: bool = False


class CheckoutConfirmOut(BaseModel):
    status: str
    message: str
    payment_id: Optional[str] = None
    invoice_id: Optional[str] = None
    subscription_id: Optional[str] = None
    redirect_url: Optional[str] = None

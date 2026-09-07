"""Catalog schemas: products and plans (contract section 5)."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models import BillingInterval, PricingModel, ProductType


class PlanCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    product_id: str
    name: str = Field(..., min_length=1, max_length=200)
    code: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    billing_interval: BillingInterval
    interval_count: int = Field(1, ge=1, le=120)
    pricing_model: PricingModel
    unit_amount: Decimal = Field(..., ge=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    setup_fee: Decimal = Field(Decimal("0"), ge=0)
    trial_days: int = Field(0, ge=0, le=3650)
    is_active: bool = True

    @field_validator("currency")
    @classmethod
    def _upper(cls, v):
        return v.upper() if isinstance(v, str) else v


class PlanUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    code: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = None
    billing_interval: Optional[BillingInterval] = None
    interval_count: Optional[int] = Field(None, ge=1, le=120)
    pricing_model: Optional[PricingModel] = None
    unit_amount: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    setup_fee: Optional[Decimal] = Field(None, ge=0)
    trial_days: Optional[int] = Field(None, ge=0, le=3650)
    is_active: Optional[bool] = None

    @field_validator("currency")
    @classmethod
    def _upper(cls, v):
        return v.upper() if isinstance(v, str) else v


class PlanOut(BaseModel):
    id: str
    product_id: str
    name: str
    code: str
    description: Optional[str] = None
    billing_interval: str
    interval_count: int
    pricing_model: str
    unit_amount: str
    currency: str
    setup_fee: str
    trial_days: int
    is_active: bool
    active_subscriptions: int
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    # Optional on input: a SKU is generated when omitted (the column is NOT NULL).
    sku: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = None
    type: ProductType = ProductType.SERVICE
    unit: str = Field("unit", min_length=1, max_length=32)
    hsn_sac_code: Optional[str] = Field(None, max_length=16)
    # Defaults to the organization's default_tax_rate_pct when omitted.
    tax_rate_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    is_active: bool = True


class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    sku: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = None
    type: Optional[ProductType] = None
    unit: Optional[str] = Field(None, min_length=1, max_length=32)
    hsn_sac_code: Optional[str] = Field(None, max_length=16)
    tax_rate_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None


class ProductOut(BaseModel):
    id: str
    name: str
    sku: str
    description: Optional[str] = None
    type: str
    unit: str
    hsn_sac_code: Optional[str] = None
    tax_rate_pct: str
    is_active: bool
    plans: List[PlanOut]
    created_at: datetime
    updated_at: datetime

"""Catalog and CPQ schemas."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.catalog_cpq import (
    OfferingPricingModel,
    OfferingType,
    PriceBookStatus,
    RuleType,
)
from backend.app.schemas.validators import validate_hsn_sac, validate_sku_format


# --- Pricing Tiers ---

# Numeric(14,2) columns hold at most 12 integer digits.
MAX_MONEY = Decimal("999999999999.99")
MAX_QTY = Decimal("1000000000")  # sane upper bound for tier quantities


class PricingTierSchema(BaseModel):
    min_qty: Optional[Decimal] = Field(None, ge=0, le=MAX_QTY)
    max_qty: Optional[Decimal] = Field(None, ge=0, le=MAX_QTY)
    unit_price: Optional[Decimal] = Field(None, ge=0, le=MAX_MONEY, max_digits=14, decimal_places=2)
    package_qty: Optional[Decimal] = Field(None, ge=0, le=MAX_QTY)
    package_price: Optional[Decimal] = Field(None, ge=0, le=MAX_MONEY, max_digits=14, decimal_places=2)


# --- Offerings (Catalog) ---

class BundleComponentIn(BaseModel):
    component_offering_id: str
    is_required: bool = True
    default_quantity: Decimal = Field(Decimal("1"), gt=0)
    min_quantity: Decimal = Field(Decimal("1"), ge=0)
    max_quantity: Optional[Decimal] = Field(None, gt=0)
    discount_pct: Decimal = Field(Decimal("0"), ge=0, le=100)


class BundleComponentOut(BaseModel):
    id: str
    component_offering_id: str
    component_name: str
    component_sku: str
    component_base_price: str
    is_required: bool
    default_quantity: str
    min_quantity: str
    max_quantity: Optional[str] = None
    discount_pct: str


class OfferingCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    sku: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = None
    type: OfferingType = OfferingType.PRODUCT
    category: Optional[str] = Field(None, max_length=100)
    unit: str = Field("unit", min_length=1, max_length=32)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    pricing_model: OfferingPricingModel = OfferingPricingModel.PER_UNIT
    base_price: Decimal = Field(..., ge=0, le=MAX_MONEY, max_digits=14, decimal_places=2)
    tax_rate_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    hsn_sac_code: Optional[str] = Field(None, max_length=16)
    billing_frequency: str = Field("one_time", max_length=32)
    is_active: bool = True
    pricing_tiers: Optional[List[PricingTierSchema]] = None
    bundle_components: Optional[List[BundleComponentIn]] = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v):
        return v.upper() if isinstance(v, str) else v

    @field_validator("sku")
    @classmethod
    def _sku(cls, v):
        return validate_sku_format(v)

    @field_validator("hsn_sac_code")
    @classmethod
    def _hsn_sac(cls, v):
        return validate_hsn_sac(v)

    @field_validator("pricing_tiers")
    @classmethod
    def _validate_tier_brackets(cls, v):
        # Reject overlapping / inverted / negative brackets and a non-final open-ended bracket
        # at save time (same bracket semantics the pricing engine uses when billing).
        from backend.app.services.pricing_engine import validate_pricing_tiers

        validate_pricing_tiers(v)
        return v


class OfferingUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    sku: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = None
    type: Optional[OfferingType] = None
    category: Optional[str] = Field(None, max_length=100)
    unit: Optional[str] = Field(None, min_length=1, max_length=32)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    pricing_model: Optional[OfferingPricingModel] = None
    base_price: Optional[Decimal] = Field(None, ge=0, le=MAX_MONEY, max_digits=14, decimal_places=2)
    tax_rate_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    hsn_sac_code: Optional[str] = Field(None, max_length=16)
    billing_frequency: Optional[str] = Field(None, max_length=32)
    is_active: Optional[bool] = None
    pricing_tiers: Optional[List[PricingTierSchema]] = None
    bundle_components: Optional[List[BundleComponentIn]] = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v):
        return v.upper() if isinstance(v, str) else v

    @field_validator("sku")
    @classmethod
    def _sku(cls, v):
        return validate_sku_format(v)

    @field_validator("hsn_sac_code")
    @classmethod
    def _hsn_sac(cls, v):
        return validate_hsn_sac(v)

    @field_validator("pricing_tiers")
    @classmethod
    def _validate_tier_brackets(cls, v):
        # Reject overlapping / inverted / negative brackets and a non-final open-ended bracket
        # at save time (same bracket semantics the pricing engine uses when billing).
        from backend.app.services.pricing_engine import validate_pricing_tiers

        validate_pricing_tiers(v)
        return v


class OfferingOut(BaseModel):
    id: str
    name: str
    sku: str
    description: Optional[str] = None
    type: str
    category: Optional[str] = None
    unit: str
    currency: str
    pricing_model: str
    base_price: str
    tax_rate_pct: str
    hsn_sac_code: Optional[str] = None
    billing_frequency: str
    is_active: bool
    pricing_tiers: Optional[List[Dict[str, Any]]] = None
    bundle_components: List[BundleComponentOut] = []
    created_at: datetime
    updated_at: datetime


# --- Price Books ---

class PriceBookEntryIn(BaseModel):
    offering_id: str
    custom_price: Optional[Decimal] = Field(None, ge=0)
    discount_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    is_active: bool = True


class PriceBookEntryOut(BaseModel):
    id: str
    offering_id: str
    offering_name: str
    offering_sku: str
    catalog_base_price: str
    custom_price: Optional[str] = None
    discount_pct: Optional[str] = None
    is_active: bool


class PriceBookCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    currency: Optional[str] = Field("INR", min_length=3, max_length=3)
    customer_segment: Optional[str] = Field(None, max_length=100)
    is_default: bool = False
    status: PriceBookStatus = PriceBookStatus.ACTIVE
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None
    entries: Optional[List[PriceBookEntryIn]] = None


class PriceBookUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    customer_segment: Optional[str] = Field(None, max_length=100)
    is_default: Optional[bool] = None
    status: Optional[PriceBookStatus] = None
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None
    entries: Optional[List[PriceBookEntryIn]] = None


class PriceBookOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    currency: str
    customer_segment: Optional[str] = None
    is_default: bool
    status: str
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None
    entries_count: int = 0
    entries: List[PriceBookEntryOut] = []
    created_at: datetime
    updated_at: datetime


# --- CPQ Rules ---

class CPQRuleCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    rule_type: RuleType
    is_active: bool = True
    priority: int = 100
    conditions: Dict[str, Any] = Field(default_factory=dict)
    actions: Dict[str, Any] = Field(default_factory=dict)


class CPQRuleOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    rule_type: str
    is_active: bool
    priority: int
    conditions: Dict[str, Any]
    actions: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


# --- Pricing Simulation & "Why This Price?" ---

class PriceSimulationItemIn(BaseModel):
    offering_id: str
    quantity: Decimal = Field(Decimal("1"), gt=0, le=1_000_000)
    custom_discount_pct: Optional[Decimal] = Field(Decimal("0"), ge=0, le=100)


class PriceSimulationRequest(BaseModel):
    customer_id: Optional[str] = None
    price_book_id: Optional[str] = None
    items: List[PriceSimulationItemIn] = Field(..., min_length=1)
    deal_discount_pct: Decimal = Field(Decimal("0"), ge=0, le=100)


class PriceLineBreakdown(BaseModel):
    offering_id: str
    offering_name: str
    sku: str
    quantity: str
    pricing_model: str
    catalog_base_price: str
    price_book_name: Optional[str] = None
    price_book_adjusted_unit_price: str
    volume_tier_applied: Optional[str] = None
    effective_unit_price: str
    line_subtotal: str
    discount_pct: str
    discount_amount: str
    line_net_amount: str
    tax_rate_pct: str
    tax_amount: str
    line_total: str
    rule_messages: List[str] = []


class PriceSimulationResponse(BaseModel):
    currency: str
    price_book_applied: Optional[str] = None
    items: List[PriceLineBreakdown]
    subtotal: str
    discount_pct: str
    discount_amount: str
    tax_amount: str
    total: str
    approval_required: bool = False
    approval_reasons: List[str] = []
    recommendations: List[Dict[str, Any]] = []
    rule_warnings: List[str] = []


# --- CPQ Deal Builder ---

class CPQDealItemIn(BaseModel):
    offering_id: str
    # Same ceiling as the pricing simulator (/cpq/simulate, /pricing/*); a larger value used to
    # fail inside the service's simulation request and return 500.
    quantity: Decimal = Field(Decimal("1"), gt=0, le=1_000_000)
    discount_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    description: Optional[str] = None


class CPQDealCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=255)
    customer_id: str
    price_book_id: Optional[str] = None
    # None: the deal takes the customer's currency, else the organization's (BUG-24).
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    discount_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    notes: Optional[str] = None
    terms: Optional[str] = None
    items: List[CPQDealItemIn] = Field(..., min_length=1)


class CPQDealUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    customer_id: Optional[str] = None
    price_book_id: Optional[str] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    discount_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    notes: Optional[str] = None
    terms: Optional[str] = None
    items: Optional[List[CPQDealItemIn]] = None


class CPQDealItemOut(BaseModel):
    id: str
    offering_id: str
    offering_name: str
    offering_sku: str
    description: str
    quantity: str
    catalog_base_price: str
    unit_price: str
    discount_pct: str
    discount_amount: str
    tax_rate_pct: str
    tax_amount: str
    total_amount: str
    is_bundle_parent: bool
    parent_item_id: Optional[str] = None
    item_explanation: Optional[Dict[str, Any]] = None
    position: int


class CPQDealOut(BaseModel):
    id: str
    deal_number: str
    title: str
    customer_id: str
    customer_name: str
    customer_number: str
    price_book_id: Optional[str] = None
    price_book_name: Optional[str] = None
    status: str
    currency: str
    subtotal: str
    discount_pct: str
    discount_amount: str
    tax_amount: str
    total: str
    pricing_explanation: Optional[Dict[str, Any]] = None
    approval_required: bool
    approval_reason: Optional[str] = None
    approval_status: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    converted_quote_id: Optional[str] = None
    created_by_id: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    items: List[CPQDealItemOut] = []
    created_at: datetime
    updated_at: datetime

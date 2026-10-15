"""Rooman Billing plan catalog API models (read-only; core/plan_catalog.py is the source of truth)."""
from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class CatalogModuleOut(BaseModel):
    key: str
    label: str
    base: bool


class CatalogBundleOut(BaseModel):
    key: str
    label: str
    description: str


class CatalogPriceOut(BaseModel):
    amount_minor: int  # smallest currency unit (paise)
    currency: str
    interval: str
    interval_count: int


class PublicPlanOut(BaseModel):
    code: str
    name: str
    description: str
    bundles: List[CatalogBundleOut]
    modules: List[CatalogModuleOut]
    price: CatalogPriceOut
    tax_treatment: Optional[str] = None  # always set for published plans; null for sandbox test plans
    seat_limit: int
    # A sandbox TEST plan (Razorpay Test Mode only), never a commercial offer.
    sandbox: bool = False
    # True only when checkout can run right now (keys, allowed mode, webhook configured). The checkout
    # endpoint re-checks everything; this is never authorization.
    purchasable: bool = False


class PublicCatalogOut(BaseModel):
    catalog_version: int
    plans: List[PublicPlanOut]


class PlatformPlanOut(BaseModel):
    code: str
    name: str
    description: str
    status: str
    bundles: List[CatalogBundleOut]
    modules: List[CatalogModuleOut]
    price: CatalogPriceOut
    tax_treatment: Optional[str] = None
    seat_limit: int
    sandbox: bool = False
    approved_by: Optional[str] = None
    approved_on: Optional[date] = None
    created_on: date
    updated_on: date


class NotOfferedModuleOut(BaseModel):
    key: str
    label: str
    reason: str


class PlatformCatalogOut(BaseModel):
    catalog_version: int
    updated_on: date
    bundles: List[CatalogBundleOut]
    plans: List[PlatformPlanOut]
    not_offered: List[NotOfferedModuleOut]

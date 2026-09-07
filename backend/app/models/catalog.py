"""Products and their recurring/one-time pricing plans."""
import enum

from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ProductType(str, enum.Enum):
    SERVICE = "service"
    GOODS = "goods"
    SUBSCRIPTION = "subscription"


class BillingInterval(str, enum.Enum):
    ONE_TIME = "one_time"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    YEARLY = "yearly"


INTERVAL_MONTHS = {
    BillingInterval.MONTHLY: 1,
    BillingInterval.QUARTERLY: 3,
    BillingInterval.SEMIANNUAL: 6,
    BillingInterval.YEARLY: 12,
}


class PricingModel(str, enum.Enum):
    FLAT = "flat"  # unit_amount charged once per period regardless of quantity
    PER_UNIT = "per_unit"  # unit_amount * quantity


class Product(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("organization_id", "sku", name="uq_product_sku_per_org"),)

    name = Column(String(200), nullable=False, index=True)
    sku = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(Enum(ProductType, name="product_type"), nullable=False, default=ProductType.SERVICE)
    unit = Column(String(32), nullable=False, default="unit")
    hsn_sac_code = Column(String(16), nullable=True)
    tax_rate_pct = Column(Numeric(5, 2), nullable=False, default=18)
    is_active = Column(Boolean, nullable=False, default=True)

    plans = relationship("Plan", back_populates="product", cascade="all, delete-orphan")


class Plan(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_plan_code_per_org"),)

    product_id = Column(String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    billing_interval = Column(Enum(BillingInterval, name="billing_interval"), nullable=False, default=BillingInterval.MONTHLY)
    interval_count = Column(Integer, nullable=False, default=1)
    pricing_model = Column(Enum(PricingModel, name="pricing_model"), nullable=False, default=PricingModel.FLAT)
    unit_amount = Column(Numeric(14, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="INR")
    setup_fee = Column(Numeric(14, 2), nullable=False, default=0)
    trial_days = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    product = relationship("Product", back_populates="plans")

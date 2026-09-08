"""Catalog and CPQ models: Offerings, Price Books, Bundles, Rules, and CPQ Deals."""
import enum
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OfferingType(str, enum.Enum):
    PRODUCT = "product"  # Tangible/physical goods or equipment
    SERVICE = "service"  # Professional, consulting or managed services
    PLAN = "plan"  # Recurring software/subscription plan
    BUNDLE = "bundle"  # Curated package/composite offering


class OfferingPricingModel(str, enum.Enum):
    FLAT = "flat"  # Fixed flat amount
    PER_UNIT = "per_unit"  # unit_price * quantity
    VOLUME = "volume"  # All units priced at applicable bracket tier
    TIERED = "tiered"  # Graduated brackets across cumulative units
    PACKAGE = "package"  # Fixed block / package pricing (e.g. 10 for ₹5k, 25 for ₹10k, 50 for ₹18k)


class PriceBookStatus(str, enum.Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


class CPQDealStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIGURED = "configured"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONVERTED = "converted"  # Converted to quote/invoice


class RuleType(str, enum.Enum):
    REQUIRES = "requires"  # Offering A requires Offering B
    EXCLUDES = "excludes"  # Offering A cannot be paired with Offering C
    RECOMMENDS = "recommends"  # Offering A suggests Add-on D
    TIER_DISCOUNT = "tier_discount"  # Discount rule based on volume/amount


class Offering(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Master Commercial Catalog Offering."""
    __tablename__ = "offerings"
    __table_args__ = (
        UniqueConstraint("organization_id", "sku", name="uq_offering_sku_per_org"),
        Index("ix_offerings_org_type_active", "organization_id", "type", "is_active"),
    )

    name = Column(String(200), nullable=False, index=True)
    sku = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(Enum(OfferingType, name="offering_type"), nullable=False, default=OfferingType.PRODUCT)
    category = Column(String(100), nullable=True, index=True)
    unit = Column(String(32), nullable=False, default="unit")
    currency = Column(String(3), nullable=False, default="INR")
    pricing_model = Column(Enum(OfferingPricingModel, name="offering_pricing_model"), nullable=False, default=OfferingPricingModel.PER_UNIT)
    base_price = Column(Numeric(14, 2), nullable=False, default=0)
    tax_rate_pct = Column(Numeric(5, 2), nullable=False, default=18)
    hsn_sac_code = Column(String(16), nullable=True)
    billing_frequency = Column(String(32), nullable=False, default="one_time")  # one_time, monthly, quarterly, yearly
    is_active = Column(Boolean, nullable=False, default=True)

    # For volume/tiered pricing: list of { "min_qty": 0, "max_qty": 100, "unit_price": 500 }
    pricing_tiers = Column(JSON, nullable=True)

    # Relationships
    bundle_items = relationship(
        "BundleItem",
        back_populates="bundle",
        foreign_keys="[BundleItem.bundle_id]",
        cascade="all, delete-orphan",
    )
    price_book_entries = relationship(
        "PriceBookEntry",
        back_populates="offering",
        cascade="all, delete-orphan",
    )


class PriceBook(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Price Book / Price List for segmentation (Enterprise, Partner, Gov, etc.)."""
    __tablename__ = "price_books"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_price_book_name_per_org"),
        Index("ix_price_books_org_status", "organization_id", "status"),
    )

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    currency = Column(String(3), nullable=False, default="INR")
    customer_segment = Column(String(100), nullable=True)  # Standard, Enterprise, Partner, Government, Education
    is_default = Column(Boolean, nullable=False, default=False)
    status = Column(Enum(PriceBookStatus, name="price_book_status"), nullable=False, default=PriceBookStatus.ACTIVE)
    effective_from = Column(Date, nullable=True)
    effective_until = Column(Date, nullable=True)

    entries = relationship("PriceBookEntry", back_populates="price_book", cascade="all, delete-orphan")


class PriceBookEntry(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Price Book item pricing override or discount percentage."""
    __tablename__ = "price_book_entries"
    __table_args__ = (
        UniqueConstraint("price_book_id", "offering_id", name="uq_pbe_book_offering"),
    )

    price_book_id = Column(String(36), ForeignKey("price_books.id", ondelete="CASCADE"), nullable=False, index=True)
    offering_id = Column(String(36), ForeignKey("offerings.id", ondelete="CASCADE"), nullable=False, index=True)
    custom_price = Column(Numeric(14, 2), nullable=True)  # Direct price override
    discount_pct = Column(Numeric(5, 2), nullable=True)  # Or percentage discount off catalog base price
    is_active = Column(Boolean, nullable=False, default=True)

    price_book = relationship("PriceBook", back_populates="entries")
    offering = relationship("Offering", back_populates="price_book_entries")


class BundleItem(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Components belonging to a Bundle offering."""
    __tablename__ = "bundle_items"
    __table_args__ = (
        UniqueConstraint("bundle_id", "component_offering_id", name="uq_bundle_component"),
    )

    bundle_id = Column(String(36), ForeignKey("offerings.id", ondelete="CASCADE"), nullable=False, index=True)
    component_offering_id = Column(String(36), ForeignKey("offerings.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_required = Column(Boolean, nullable=False, default=True)
    default_quantity = Column(Numeric(12, 3), nullable=False, default=1)
    min_quantity = Column(Numeric(12, 3), nullable=False, default=1)
    max_quantity = Column(Numeric(12, 3), nullable=True)
    discount_pct = Column(Numeric(5, 2), nullable=False, default=0)
    position = Column(Integer, nullable=False, default=0)

    bundle = relationship("Offering", back_populates="bundle_items", foreign_keys=[bundle_id])
    component = relationship("Offering", foreign_keys=[component_offering_id])


class CPQRule(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Deterministic configuration and pricing rule."""
    __tablename__ = "cpq_rules"

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    rule_type = Column(Enum(RuleType, name="cpq_rule_type"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)
    # JSON schema defining conditions (e.g. { "offering_id": "...", "min_qty": 5, "segment": "..." })
    conditions = Column(JSON, nullable=False, default=dict)
    # JSON schema defining action (e.g. { "requires_offering_id": "...", "discount_pct": 10, "message": "..." })
    actions = Column(JSON, nullable=False, default=dict)


class CPQDeal(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """CPQ Deal / Configuration transaction."""
    __tablename__ = "cpq_deals"
    __table_args__ = (
        UniqueConstraint("organization_id", "deal_number", name="uq_deal_number_per_org"),
        Index("ix_cpq_deals_org_status", "organization_id", "status"),
    )

    deal_number = Column(String(32), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    price_book_id = Column(String(36), ForeignKey("price_books.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(Enum(CPQDealStatus, name="cpq_deal_status"), nullable=False, default=CPQDealStatus.DRAFT)
    title = Column(String(255), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")

    subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    discount_pct = Column(Numeric(5, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(14, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    total = Column(Numeric(14, 2), nullable=False, default=0)

    # Detailed "Why This Price?" calculation lineage tree stored as JSON
    pricing_explanation = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    terms = Column(Text, nullable=True)

    approval_required = Column(Boolean, nullable=False, default=False)
    approval_reason = Column(String(255), nullable=True)
    approval_status = Column(String(32), nullable=True)  # pending, approved, rejected
    approved_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    converted_quote_id = Column(String(36), ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    customer = relationship("Customer")
    price_book = relationship("PriceBook")
    items = relationship("CPQDealItem", back_populates="deal", cascade="all, delete-orphan", order_by="CPQDealItem.position")
    quote = relationship("Quote")


class CPQDealItem(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Line items inside a CPQ Deal."""
    __tablename__ = "cpq_deal_items"

    deal_id = Column(String(36), ForeignKey("cpq_deals.id", ondelete="CASCADE"), nullable=False, index=True)
    offering_id = Column(String(36), ForeignKey("offerings.id", ondelete="RESTRICT"), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False, default=1)
    catalog_base_price = Column(Numeric(14, 2), nullable=False, default=0)
    unit_price = Column(Numeric(14, 2), nullable=False, default=0)  # After price book and pricing model evaluation
    discount_pct = Column(Numeric(5, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(14, 2), nullable=False, default=0)
    tax_rate_pct = Column(Numeric(5, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    is_bundle_parent = Column(Boolean, nullable=False, default=False)
    parent_item_id = Column(String(36), nullable=True)
    item_explanation = Column(JSON, nullable=True)  # Line-level "Why this price?"
    position = Column(Integer, nullable=False, default=0)

    deal = relationship("CPQDeal", back_populates="items")
    offering = relationship("Offering")

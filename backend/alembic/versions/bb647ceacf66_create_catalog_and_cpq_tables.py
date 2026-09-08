"""create_catalog_and_cpq_tables

Revision ID: bb647ceacf66
Revises:
Create Date: 2026-09-08 12:55:30.450707

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bb647ceacf66'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. PostgreSQL Safe ENUM Types
    op.execute(
        sa.text("""
        DO $$ BEGIN
            CREATE TYPE offering_type AS ENUM ('PRODUCT', 'SERVICE', 'PLAN', 'BUNDLE', 'product', 'service', 'plan', 'bundle');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
        """)
    )
    op.execute(
        sa.text("""
        DO $$ BEGIN
            CREATE TYPE offering_pricing_model AS ENUM ('FLAT', 'PER_UNIT', 'VOLUME', 'TIERED', 'PACKAGE', 'flat', 'per_unit', 'volume', 'tiered', 'package');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
        """)
    )
    op.execute(
        sa.text("""
        DO $$ BEGIN
            CREATE TYPE price_book_status AS ENUM ('ACTIVE', 'DRAFT', 'ARCHIVED', 'active', 'draft', 'archived');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
        """)
    )
    op.execute(
        sa.text("""
        DO $$ BEGIN
            CREATE TYPE cpq_deal_status AS ENUM ('DRAFT', 'CONFIGURED', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'CONVERTED', 'draft', 'configured', 'pending_approval', 'approved', 'rejected', 'converted');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
        """)
    )
    op.execute(
        sa.text("""
        DO $$ BEGIN
            CREATE TYPE cpq_rule_type AS ENUM ('REQUIRES', 'EXCLUDES', 'RECOMMENDS', 'TIER_DISCOUNT', 'requires', 'excludes', 'recommends', 'tier_discount');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
        """)
    )

    # 1. offerings
    op.create_table(
        "offerings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, index=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", postgresql.ENUM('PRODUCT', 'SERVICE', 'PLAN', 'BUNDLE', 'product', 'service', 'plan', 'bundle', name='offering_type', create_type=False), nullable=False, server_default='product'),
        sa.Column("category", sa.String(length=100), nullable=True, index=True),
        sa.Column("unit", sa.String(length=32), nullable=False, server_default='unit'),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column("pricing_model", postgresql.ENUM('FLAT', 'PER_UNIT', 'VOLUME', 'TIERED', 'PACKAGE', 'flat', 'per_unit', 'volume', 'tiered', 'package', name='offering_pricing_model', create_type=False), nullable=False, server_default='per_unit'),
        sa.Column("base_price", sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column("tax_rate_pct", sa.Numeric(precision=5, scale=2), nullable=False, server_default='18'),
        sa.Column("hsn_sac_code", sa.String(length=16), nullable=True),
        sa.Column("billing_frequency", sa.String(length=32), nullable=False, server_default='one_time'),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("pricing_tiers", sa.JSON(), nullable=True),
        sa.UniqueConstraint("organization_id", "sku", name="uq_offering_sku_per_org"),
    )
    op.create_index("ix_offerings_org_type_active", "offerings", ["organization_id", "type", "is_active"])

    # 2. price_books
    op.create_table(
        "price_books",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column("customer_segment", sa.String(length=100), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", postgresql.ENUM('ACTIVE', 'DRAFT', 'ARCHIVED', 'active', 'draft', 'archived', name='price_book_status', create_type=False), nullable=False, server_default='active'),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.UniqueConstraint("organization_id", "name", name="uq_price_book_name_per_org"),
    )
    op.create_index("ix_price_books_org_status", "price_books", ["organization_id", "status"])

    # 3. price_book_entries
    op.create_table(
        "price_book_entries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("price_book_id", sa.String(length=36), sa.ForeignKey("price_books.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("offering_id", sa.String(length=36), sa.ForeignKey("offerings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("custom_price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("discount_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("price_book_id", "offering_id", name="uq_pbe_book_offering"),
    )

    # 4. bundle_items
    op.create_table(
        "bundle_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("bundle_id", sa.String(length=36), sa.ForeignKey("offerings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("component_offering_id", sa.String(length=36), sa.ForeignKey("offerings.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("default_quantity", sa.Numeric(precision=12, scale=3), nullable=False, server_default='1'),
        sa.Column("min_quantity", sa.Numeric(precision=12, scale=3), nullable=False, server_default='1'),
        sa.Column("max_quantity", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("discount_pct", sa.Numeric(precision=5, scale=2), nullable=False, server_default='0'),
        sa.Column("position", sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint("bundle_id", "component_offering_id", name="uq_bundle_component"),
    )

    # 5. cpq_rules
    op.create_table(
        "cpq_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rule_type", postgresql.ENUM('REQUIRES', 'EXCLUDES', 'RECOMMENDS', 'TIER_DISCOUNT', 'requires', 'excludes', 'recommends', 'tier_discount', name='cpq_rule_type', create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default='100'),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
    )

    # 6. cpq_deals
    op.create_table(
        "cpq_deals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deal_number", sa.String(length=32), nullable=False),
        sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("price_book_id", sa.String(length=36), sa.ForeignKey("price_books.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("status", postgresql.ENUM('DRAFT', 'CONFIGURED', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'CONVERTED', 'draft', 'configured', 'pending_approval', 'approved', 'rejected', 'converted', name='cpq_deal_status', create_type=False), nullable=False, server_default='draft'),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column("subtotal", sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column("discount_pct", sa.Numeric(precision=5, scale=2), nullable=False, server_default='0'),
        sa.Column("discount_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column("tax_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column("pricing_explanation", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approval_reason", sa.String(length=255), nullable=True),
        sa.Column("approval_status", sa.String(length=32), nullable=True),
        sa.Column("approved_by_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_quote_id", sa.String(length=36), sa.ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("organization_id", "deal_number", name="uq_deal_number_per_org"),
    )
    op.create_index("ix_cpq_deals_org_status", "cpq_deals", ["organization_id", "status"])

    # 7. cpq_deal_items
    op.create_table(
        "cpq_deal_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("deal_id", sa.String(length=36), sa.ForeignKey("cpq_deals.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("offering_id", sa.String(length=36), sa.ForeignKey("offerings.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False, server_default='1'),
        sa.Column("catalog_base_price", sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column("discount_pct", sa.Numeric(precision=5, scale=2), nullable=False, server_default='0'),
        sa.Column("discount_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column("tax_rate_pct", sa.Numeric(precision=5, scale=2), nullable=False, server_default='0'),
        sa.Column("tax_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column("is_bundle_parent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("parent_item_id", sa.String(length=36), nullable=True),
        sa.Column("item_explanation", sa.JSON(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_table("cpq_deal_items")
    op.drop_table("cpq_deals")
    op.drop_table("cpq_rules")
    op.drop_table("bundle_items")
    op.drop_table("price_book_entries")
    op.drop_table("price_books")
    op.drop_table("offerings")

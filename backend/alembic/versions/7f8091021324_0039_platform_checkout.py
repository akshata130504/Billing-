"""0039 platform checkout: Razorpay plans and checkout attempts for Rooman's own plans

Two new platform tables (not tenant tables, no row level security - like platform_subscriptions):

- platform_provider_plans: the Razorpay Plan created in Rooman's account for one catalog plan's
  billing terms (fingerprint) in one mode (test / live). Unique per (provider, mode, fingerprint);
  reconcile_ref is written into the Razorpay plan's notes so an ambiguous create can be looked up
  instead of repeated.
- platform_checkout_attempts: an Owner started buying a plan - the Razorpay Subscription created for
  it and a snapshot of the offer. Grants nothing. At most one open attempt per organization (partial
  unique index on status pending / created / unknown).

No existing table or row is changed. Downgrade drops both tables, and refuses while either holds
rows (they map to objects that already exist at Razorpay).

Early revisions build tables from the models (Base.metadata.create_all), so on a fresh database the
tables may already exist: each is created only when missing.

Revision ID: 7f8091021324
Revises: 6e7f80910213
Create Date: 2026-10-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "7f8091021324"
down_revision = "6e7f80910213"
branch_labels = None
depends_on = None

OPEN = "status IN ('pending', 'created', 'unknown')"


def _has(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has("platform_provider_plans"):
        op.create_table(
            "platform_provider_plans",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("provider", sa.String(length=16), nullable=False),
            sa.Column("mode", sa.String(length=8), nullable=False),
            sa.Column("plan_code", sa.String(length=32), nullable=False),
            sa.Column("fingerprint", sa.String(length=64), nullable=False),
            sa.Column("amount_minor", sa.BigInteger(), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("billing_interval", sa.String(length=10), nullable=False),
            sa.Column("billing_interval_count", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("reconcile_ref", sa.String(length=64), nullable=False),
            sa.Column("provider_plan_id", sa.String(length=64), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.String(length=300), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider", "mode", "fingerprint", name="uq_platform_provider_plan_terms"),
            sa.UniqueConstraint("reconcile_ref", name="uq_platform_provider_plans_reconcile_ref"),
            sa.UniqueConstraint("provider_plan_id", name="uq_platform_provider_plans_provider_plan_id"),
            sa.CheckConstraint("mode IN ('test', 'live')", name="ck_platform_provider_plan_mode"),
            sa.CheckConstraint("status IN ('pending', 'created', 'unknown', 'failed')", name="ck_platform_provider_plan_status"),
            sa.CheckConstraint("status <> 'created' OR provider_plan_id IS NOT NULL", name="ck_platform_provider_plan_created_id"),
        )
    if not _has("platform_checkout_attempts"):
        op.create_table(
            "platform_checkout_attempts",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("organization_id", sa.String(length=36), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("plan_code", sa.String(length=32), nullable=False),
            sa.Column("catalog_version", sa.Integer(), nullable=False),
            sa.Column("fingerprint", sa.String(length=64), nullable=False),
            sa.Column("amount_minor", sa.BigInteger(), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("billing_interval", sa.String(length=10), nullable=False),
            sa.Column("billing_interval_count", sa.Integer(), nullable=False),
            sa.Column("seat_limit", sa.Integer(), nullable=False),
            sa.Column("tax_treatment", sa.String(length=16), nullable=True),
            sa.Column("provider", sa.String(length=16), nullable=False),
            sa.Column("mode", sa.String(length=8), nullable=False),
            sa.Column("provider_plan_id", sa.String(length=64), nullable=True),
            sa.Column("provider_subscription_id", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_error", sa.String(length=300), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("provider_subscription_id", name="uq_platform_checkout_attempts_provider_subscription_id"),
            sa.CheckConstraint("mode IN ('test', 'live')", name="ck_platform_checkout_mode"),
            sa.CheckConstraint("status IN ('pending', 'created', 'unknown', 'failed', 'expired', 'completed')",
                               name="ck_platform_checkout_status"),
            sa.CheckConstraint("status <> 'created' OR provider_subscription_id IS NOT NULL",
                               name="ck_platform_checkout_created_id"),
        )
        op.create_index("ix_platform_checkout_attempts_organization_id", "platform_checkout_attempts", ["organization_id"])
        op.create_index("uq_platform_checkout_one_open", "platform_checkout_attempts", ["organization_id"], unique=True,
                        postgresql_where=sa.text(OPEN), sqlite_where=sa.text(OPEN))


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("platform_checkout_attempts", "platform_provider_plans"):
        if _has(table) and bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError(f"Refusing to downgrade 0039: {table} has rows that refer to objects at Razorpay.")
    for table in ("platform_checkout_attempts", "platform_provider_plans"):
        if _has(table):
            op.drop_table(table)

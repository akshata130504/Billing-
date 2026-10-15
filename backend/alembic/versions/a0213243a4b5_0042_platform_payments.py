"""0042 platform payments: verified Rooman plan payments and their payment receipts

- platform_payments: one row per VERIFIED, successful Razorpay payment for an organization's Rooman plan (initial
  payment or renewal), written by services/platform_receipt_service.py from the shared payment verification.
  Unique (provider, provider_payment_id): a payment can never produce a second receipt. Unique receipt_number.
  Amount, plan and the organization's billing identity are snapshots; the application never updates or deletes
  rows. Foreign keys are RESTRICT (a payment record outlives the checkout and the organization row).
- A payment RECEIPT, not a GST tax invoice (no tax columns: tax treatment and Rooman's legal / tax details are not
  decided; a future tax invoice would be its own table referencing these rows).
- Platform table: no row level security (tenant reads filter by organization_id in the API, like
  platform_subscriptions). Unrelated to the on-hold scheduled plan switch.

Additive only. Downgrade refuses while any payment is recorded.

Revision ID: a0213243a4b5
Revises: 910213243a4b
Create Date: 2026-10-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a0213243a4b5"
down_revision = "910213243a4b"
branch_labels = None
depends_on = None

TABLE = "platform_payments"


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("checkout_attempt_id", sa.String(length=36),
                  sa.ForeignKey("platform_checkout_attempts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=64), nullable=False),
        sa.Column("provider_subscription_id", sa.String(length=64), nullable=False),
        sa.Column("provider_invoice_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_code", sa.String(length=32), nullable=False),
        sa.Column("plan_name", sa.String(length=80), nullable=True),
        sa.Column("billing_interval", sa.String(length=10), nullable=False),
        sa.Column("billing_interval_count", sa.Integer(), nullable=False),
        sa.Column("sandbox", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("receipt_number", sa.String(length=32), nullable=False),
        sa.Column("billed_name", sa.String(length=200), nullable=False),
        sa.Column("billed_legal_name", sa.String(length=200), nullable=True),
        sa.Column("billed_email", sa.String(length=255), nullable=True),
        sa.Column("billed_address_line1", sa.String(length=255), nullable=True),
        sa.Column("billed_address_line2", sa.String(length=255), nullable=True),
        sa.Column("billed_city", sa.String(length=120), nullable=True),
        sa.Column("billed_state", sa.String(length=120), nullable=True),
        sa.Column("billed_postal_code", sa.String(length=20), nullable=True),
        sa.Column("billed_country", sa.String(length=10), nullable=True),
        sa.Column("billed_gstin", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_platform_payments_provider_payment"),
        sa.UniqueConstraint("receipt_number", name="uq_platform_payments_receipt_number"),
        sa.CheckConstraint("mode IN ('test', 'live')", name="ck_platform_payments_mode"),
        sa.CheckConstraint("kind IN ('initial', 'renewal')", name="ck_platform_payments_kind"),
        sa.CheckConstraint("status IN ('paid')", name="ck_platform_payments_status"),
        sa.CheckConstraint("amount_minor > 0", name="ck_platform_payments_amount_positive"),
    )
    op.create_index("ix_platform_payments_org_paid_at", TABLE, ["organization_id", "paid_at"])
    op.create_index("ix_platform_payments_checkout_attempt_id", TABLE, ["checkout_attempt_id"])
    op.create_index("ix_platform_payments_provider_subscription_id", TABLE, ["provider_subscription_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    if bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar():
        raise RuntimeError("Refusing to downgrade 0042: platform_payments holds payment records.")
    op.drop_table(TABLE)

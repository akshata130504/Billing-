"""0038_upi_autopay_gateway_subscriptions

UPI AutoPay / e-mandate through Razorpay Subscriptions (BUSINESS-217).

* plans.autopay_enabled: per-plan switch; subscriptions to a plan may only be collected by a
  Razorpay Subscription when it is on. Existing plans stay off (one-time payment unchanged).
* gateway_subscriptions: one row per Razorpay Subscription (mandate) of a local subscription,
  mirroring its state for webhook attribution, ordering and the customer authorisation page.
  It carries organization_id, so it gets the same forced tenant_isolation_policy as 0032/0037
  (backend/tests/test_rls_coverage.py requires every tenant table to be in an RLS migration).

Idempotent like 0035/0036: on a fresh database the 0002 baseline (Base.metadata.create_all with the
current models) has already created the column and the table, so each step checks first.

Revision ID: 6e7f80910213
Revises: 5d6e7f809102
Create Date: 2026-10-26 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6e7f80910213"
down_revision: Union[str, None] = "5d6e7f809102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = ("gateway_subscriptions",)

# Same predicate as 0032 / 0037 (textually identical so the policies are interchangeable).
_PREDICATE = (
    "current_setting('app.current_organization_id', true) = '__SYSTEM__' "
    "OR organization_id = current_setting('app.current_organization_id', true)"
)


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


INDEXES = (
    ("ix_gateway_subscriptions_organization_id", ["organization_id"]),
    ("ix_gateway_subscriptions_customer_id", ["customer_id"]),
    ("ix_gateway_subscriptions_status", ["status"]),
    ("ix_gateway_subscriptions_org_subscription", ["organization_id", "subscription_id"]),
)


def upgrade() -> None:
    if "autopay_enabled" not in _columns("plans"):
        op.add_column("plans", sa.Column("autopay_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not _has_table("gateway_subscriptions"):
        _create_table()
    existing = _indexes("gateway_subscriptions")
    for name, cols in INDEXES:
        if name not in existing:
            op.create_index(name, "gateway_subscriptions", cols)

    if op.get_bind().dialect.name == "postgresql":
        for table in RLS_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            op.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies
                        WHERE schemaname = current_schema() AND tablename = '{table}'
                          AND policyname = 'tenant_isolation_policy'
                    ) THEN
                        CREATE POLICY tenant_isolation_policy ON {table}
                            FOR ALL
                            USING ({_PREDICATE})
                            WITH CHECK ({_PREDICATE});
                    END IF;
                END $$;
            """)


def _create_table() -> None:
    op.create_table(
        "gateway_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("gateway", sa.String(length=20), nullable=False),
        sa.Column("gateway_key_id", sa.String(length=64), nullable=False),
        sa.Column("gateway_plan_id", sa.String(length=64), nullable=False),
        sa.Column("gateway_subscription_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("paid_count", sa.Integer(), nullable=False),
        sa.Column("short_url", sa.Text(), nullable=True),
        sa.Column("public_token_hash", sa.String(length=64), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("charge_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_notified_cycle", sa.String(length=32), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gateway_subscription_id"),
        sa.UniqueConstraint("public_token_hash"),
    )


def downgrade() -> None:
    if _has_table("gateway_subscriptions"):
        op.drop_table("gateway_subscriptions")  # drops its indexes and policy with it
    if "autopay_enabled" in _columns("plans"):
        with op.batch_alter_table("plans") as batch:  # SQLite needs batch mode to drop a column
            batch.drop_column("autopay_enabled")

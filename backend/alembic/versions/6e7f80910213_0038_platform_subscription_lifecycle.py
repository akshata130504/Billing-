"""0038 platform_subscriptions: paid plan lifecycle and billing periods

Adds what a paid Rooman plan needs to the existing one-row-per-organization table (the trial row
becomes the subscription row; no second subscription table):

- plan_code (a code from core/plan_catalog.json), billing_interval / billing_interval_count (copied
  from the catalog for the current period), current_period_start / current_period_end,
  cancel_at_period_end, cancelled_at, grace_period_end - all NULL / false for existing rows.
- trial_started_at / trial_ends_at become nullable (an organization may subscribe without a trial);
  a CHECK keeps them required for 'trialing' rows, so every existing trial row stays valid.
- CHECK constraints: the stored state is one of trialing / active / past_due / cancelled / expired,
  a paid row names its plan and a non-empty period, past_due has a grace end, cancelled a time.

No data is changed: every existing row is a 'trialing' row with both trial dates, which satisfies
every new constraint. Not a tenant table (no row level security), like 0037.

Downgrade drops the new columns and constraints and makes the trial dates NOT NULL again. It refuses
to run while any row is not 'trialing' (a paid subscription would lose its plan and period).

Early revisions build tables from the models (Base.metadata.create_all), so on a fresh database the
columns and constraints may already exist: everything is added only when missing.

Revision ID: 6e7f80910213
Revises: 5d6e7f809102
Create Date: 2026-10-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "6e7f80910213"
down_revision = "5d6e7f809102"
branch_labels = None
depends_on = None

TABLE = "platform_subscriptions"
NEW_COLUMNS = (
    ("plan_code", lambda: sa.Column("plan_code", sa.String(length=32), nullable=True)),
    ("billing_interval", lambda: sa.Column("billing_interval", sa.String(length=10), nullable=True)),
    ("billing_interval_count", lambda: sa.Column("billing_interval_count", sa.Integer(), nullable=True)),
    ("current_period_start", lambda: sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True)),
    ("current_period_end", lambda: sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True)),
    ("cancel_at_period_end", lambda: sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False,
                                               server_default=sa.false())),
    ("cancelled_at", lambda: sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)),
    ("grace_period_end", lambda: sa.Column("grace_period_end", sa.DateTime(timezone=True), nullable=True)),
)
CHECKS = (
    ("ck_platform_subscription_state",
     "state IN ('trialing', 'active', 'past_due', 'cancelled', 'expired')"),
    ("ck_platform_subscription_trial_window",
     "state <> 'trialing' OR (trial_started_at IS NOT NULL AND trial_ends_at IS NOT NULL)"),
    ("ck_platform_subscription_paid_period",
     "state NOT IN ('active', 'past_due', 'cancelled', 'expired') OR (plan_code IS NOT NULL "
     "AND billing_interval IS NOT NULL AND billing_interval_count IS NOT NULL AND current_period_start IS NOT NULL "
     "AND current_period_end IS NOT NULL AND current_period_end > current_period_start)"),
    ("ck_platform_subscription_grace", "state <> 'past_due' OR grace_period_end IS NOT NULL"),
    ("ck_platform_subscription_cancelled_at", "state <> 'cancelled' OR cancelled_at IS NOT NULL"),
    ("ck_platform_subscription_interval", "billing_interval IS NULL OR billing_interval IN ('month', 'year')"),
    ("ck_platform_subscription_interval_count",
     "billing_interval_count IS NULL OR (billing_interval_count >= 1 AND billing_interval_count <= 12)"),
)


def _columns() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _checks() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_check_constraints(TABLE)}


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table(TABLE):  # pragma: no cover - 0037 always creates it
        return
    existing, checks = _columns(), _checks()
    with op.batch_alter_table(TABLE) as batch:
        for name, column in NEW_COLUMNS:
            if name not in existing:
                batch.add_column(column())
        batch.alter_column("trial_started_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch.alter_column("trial_ends_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        for name, condition in CHECKS:
            if name not in checks:
                batch.create_check_constraint(name, condition)


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):  # pragma: no cover
        return
    paid = bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE state <> 'trialing'")).scalar()
    if paid:
        raise RuntimeError(
            f"Refusing to downgrade 0038: {paid} platform subscription(s) are past the trial and would lose "
            "their plan and billing period."
        )
    existing, checks = _columns(), _checks()
    with op.batch_alter_table(TABLE) as batch:
        for name, _ in reversed(CHECKS):
            if name in checks:
                batch.drop_constraint(name, type_="check")
        for name, _ in reversed(NEW_COLUMNS):
            if name in existing:
                batch.drop_column(name)
        batch.alter_column("trial_started_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column("trial_ends_at", existing_type=sa.DateTime(timezone=True), nullable=False)

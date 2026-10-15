"""0040 platform payment verification: authorized checkouts, provider links, webhook ledger

- platform_checkout_attempts: provider_payment_id, authorized_at, completed_at; status may also be
  'authorized' (Razorpay has the customer's authorization, the first charge is not confirmed yet), which
  counts as OPEN in the one-open-attempt-per-organization index.
- platform_subscriptions: provider_subscription_id (unique), provider_mode, provider_paid_count - the
  Razorpay Subscription paying for the current plan and how many of its paid cycles were applied.
- platform_webhook_events: one row per verified webhook event of Rooman's account (unique event_id),
  normalized fields only (no payload). Platform table, no row level security.

No existing row changes meaning: new columns are NULL, existing attempts keep their status (none is
'authorized'). Downgrade refuses while an attempt is 'authorized', a subscription has a provider link,
or the ledger has rows.

Revision ID: 80910213243a
Revises: 7f8091021324
Create Date: 2026-10-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "80910213243a"
down_revision = "7f8091021324"
branch_labels = None
depends_on = None

ATTEMPTS = "platform_checkout_attempts"
SUBS = "platform_subscriptions"
STATUS_CHECK = "ck_platform_checkout_status"
OPEN_INDEX = "uq_platform_checkout_one_open"
NEW_STATUSES = "status IN ('pending', 'created', 'unknown', 'authorized', 'failed', 'expired', 'completed')"
OLD_STATUSES = "status IN ('pending', 'created', 'unknown', 'failed', 'expired', 'completed')"
NEW_OPEN = "status IN ('pending', 'created', 'unknown', 'authorized')"
OLD_OPEN = "status IN ('pending', 'created', 'unknown')"
ATTEMPT_COLUMNS = (
    ("provider_payment_id", lambda: sa.Column("provider_payment_id", sa.String(length=64), nullable=True)),
    ("authorized_at", lambda: sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True)),
    ("completed_at", lambda: sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)),
)
SUB_COLUMNS = (
    ("provider_subscription_id", lambda: sa.Column("provider_subscription_id", sa.String(length=64), nullable=True)),
    ("provider_mode", lambda: sa.Column("provider_mode", sa.String(length=8), nullable=True)),
    ("provider_paid_count", lambda: sa.Column("provider_paid_count", sa.Integer(), nullable=True)),
)
SUB_UNIQUE = "uq_platform_subscription_provider_subscription_id"


def _insp():
    return sa.inspect(op.get_bind())


def _columns(table):
    return {c["name"] for c in _insp().get_columns(table)}


def _checks(table):
    return {c["name"]: c.get("sqltext") for c in _insp().get_check_constraints(table)}


def _uniques(table):
    return {u["name"] for u in _insp().get_unique_constraints(table)}


def _index_has(table, name, needle):
    for ix in _insp().get_indexes(table):
        if ix["name"] == name:
            options = ix.get("dialect_options") or {}
            # Reflected conditions may be SQL clause objects: compare their text, never their truth value.
            return any(needle in str(options[key]) for key in ("postgresql_where", "sqlite_where")
                       if options.get(key) is not None)
    return False


def _set_open_index(predicate: str) -> None:
    if any(ix["name"] == OPEN_INDEX for ix in _insp().get_indexes(ATTEMPTS)):
        op.drop_index(OPEN_INDEX, table_name=ATTEMPTS)
    op.create_index(OPEN_INDEX, ATTEMPTS, ["organization_id"], unique=True,
                    postgresql_where=sa.text(predicate), sqlite_where=sa.text(predicate))


def upgrade() -> None:
    existing = _columns(ATTEMPTS)
    checks = _checks(ATTEMPTS)
    with op.batch_alter_table(ATTEMPTS) as batch:
        for name, column in ATTEMPT_COLUMNS:
            if name not in existing:
                batch.add_column(column())
        if "authorized" not in str(checks.get(STATUS_CHECK) or ""):
            if STATUS_CHECK in checks:
                batch.drop_constraint(STATUS_CHECK, type_="check")
            batch.create_check_constraint(STATUS_CHECK, NEW_STATUSES)
    if not _index_has(ATTEMPTS, OPEN_INDEX, "authorized"):
        _set_open_index(NEW_OPEN)

    existing = _columns(SUBS)
    with op.batch_alter_table(SUBS) as batch:
        for name, column in SUB_COLUMNS:
            if name not in existing:
                batch.add_column(column())
        if SUB_UNIQUE not in _uniques(SUBS):
            batch.create_unique_constraint(SUB_UNIQUE, ["provider_subscription_id"])

    if not _insp().has_table("platform_webhook_events"):
        op.create_table(
            "platform_webhook_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("provider", sa.String(length=16), nullable=False),
            sa.Column("event_id", sa.String(length=128), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("mode", sa.String(length=8), nullable=True),
            sa.Column("provider_subscription_id", sa.String(length=64), nullable=True),
            sa.Column("provider_payment_id", sa.String(length=64), nullable=True),
            sa.Column("organization_id", sa.String(length=36), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("outcome", sa.String(length=40), nullable=False),
            sa.Column("event_created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("event_id", name="uq_platform_webhook_events_event_id"),
            sa.CheckConstraint("status IN ('processed', 'ignored', 'needs_review')", name="ck_platform_webhook_event_status"),
        )
        op.create_index("ix_platform_webhook_events_organization_id", "platform_webhook_events", ["organization_id"])


def downgrade() -> None:
    bind = op.get_bind()
    blockers = []
    if _insp().has_table("platform_webhook_events") and bind.execute(sa.text("SELECT COUNT(*) FROM platform_webhook_events")).scalar():
        blockers.append("platform_webhook_events has rows")
    if "provider_subscription_id" in _columns(SUBS) and bind.execute(sa.text(
            f"SELECT COUNT(*) FROM {SUBS} WHERE provider_subscription_id IS NOT NULL")).scalar():
        blockers.append("subscriptions are linked to Razorpay")
    if bind.execute(sa.text(f"SELECT COUNT(*) FROM {ATTEMPTS} WHERE status = 'authorized'")).scalar():
        blockers.append("checkout attempts are 'authorized'")
    if blockers:
        raise RuntimeError("Refusing to downgrade 0040: " + "; ".join(blockers) + ".")

    if _insp().has_table("platform_webhook_events"):
        op.drop_table("platform_webhook_events")
    existing = _columns(SUBS)
    with op.batch_alter_table(SUBS) as batch:
        if SUB_UNIQUE in _uniques(SUBS):
            batch.drop_constraint(SUB_UNIQUE, type_="unique")
        for name, _ in reversed(SUB_COLUMNS):
            if name in existing:
                batch.drop_column(name)
    existing = _columns(ATTEMPTS)
    with op.batch_alter_table(ATTEMPTS) as batch:
        if STATUS_CHECK in _checks(ATTEMPTS):
            batch.drop_constraint(STATUS_CHECK, type_="check")
        batch.create_check_constraint(STATUS_CHECK, OLD_STATUSES)
        for name, _ in reversed(ATTEMPT_COLUMNS):
            if name in existing:
                batch.drop_column(name)
    _set_open_index(OLD_OPEN)  # after the batch: SQLite batch mode rebuilds the table and its indexes

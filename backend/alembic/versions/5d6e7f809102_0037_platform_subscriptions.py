"""0037 platform_subscriptions: the organization's own free trial

One row per organization created from now on (the 15-minute test trial, later the production
trial). Commercial state is separate from organizations.status. Existing organizations get no row
and are never restricted: this migration changes no existing data.

Chain: this revision was first written as 0035 on top of 2f3a4b5c6d7e (id 3a4b5c6d7e8f) and was
never pushed. The remote history added 0035 app_ui_visual_editor (3b4c5d6e7f80) and 0036
trial_subscription_lifecycle (4c5d6e7f8091) on the same parent, so it is re-parented after them
under a new id: a database that had the old id stamped must be stamped back first (the old id no
longer exists, so Alembic fails loudly instead of silently skipping 0035/0036).

Revision ID: 5d6e7f809102
Revises: 4c5d6e7f8091
Create Date: 2026-10-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "5d6e7f809102"
down_revision = "4c5d6e7f8091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Early revisions bootstrap tables from the models (Base.metadata.create_all), so a fresh
    # database may already have it by the time this runs.
    if sa.inspect(op.get_bind()).has_table("platform_subscriptions"):
        return
    op.create_table(
        "platform_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reminders_sent", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_subscriptions_organization_id", "platform_subscriptions", ["organization_id"], unique=True)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("platform_subscriptions"):
        op.drop_table("platform_subscriptions")

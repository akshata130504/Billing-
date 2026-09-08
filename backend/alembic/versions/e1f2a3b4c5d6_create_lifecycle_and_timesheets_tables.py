"""create_lifecycle_and_timesheets_tables

Revision ID: e1f2a3b4c5d6
Revises: d9f1a2b3c4e5
Create Date: 2026-09-08 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd9f1a2b3c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)

    # 1. Create customer_lifecycles table if not exists
    if not insp.has_table("customer_lifecycles"):
        op.create_table(
            "customer_lifecycles",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column(
                "lifecycle_stage",
                sa.Enum("prospect", "onboarding", "active", "renewal_due", "expansion", "at_risk", "churned", name="customer_lifecycle_stage"),
                nullable=False,
                server_default="active",
            ),
            sa.Column("stage_entered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column(
                "health_status",
                sa.Enum("healthy", "neutral", "at_risk", "critical", name="health_status"),
                nullable=False,
                server_default="healthy",
            ),
            sa.Column("health_score", sa.Integer(), nullable=False, server_default="85"),
            sa.Column("next_action", sa.String(length=255), nullable=True),
            sa.Column("next_action_due", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.UniqueConstraint("organization_id", "customer_id", name="uq_lifecycle_customer_per_org"),
        )

    # 2. Create time_entries table if not exists
    if not insp.has_table("time_entries"):
        op.create_table(
            "time_entries",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True),
            sa.Column("customer_id", sa.String(length=36), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("project_id", sa.String(length=64), nullable=True, index=True),
            sa.Column("project_name", sa.String(length=200), nullable=True),
            sa.Column("date", sa.Date(), nullable=False, index=True),
            sa.Column("start_time", sa.String(length=10), nullable=True),
            sa.Column("end_time", sa.String(length=10), nullable=True),
            sa.Column("duration_hours", sa.Numeric(precision=8, scale=2), nullable=False, server_default="0"),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("billing_rate", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
            sa.Column("billable_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
            sa.Column(
                "status",
                sa.Enum("draft", "submitted", "approved", "rejected", "billed", name="time_entry_status"),
                nullable=False,
                server_default="draft",
            ),
            sa.Column("invoice_id", sa.String(length=36), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("approved_by_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)

    if insp.has_table("time_entries"):
        op.drop_table("time_entries")
    if insp.has_table("customer_lifecycles"):
        op.drop_table("customer_lifecycles")

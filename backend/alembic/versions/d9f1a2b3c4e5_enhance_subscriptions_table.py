"""enhance_subscriptions_table

Revision ID: d9f1a2b3c4e5
Revises: 89da3e5d27e3
Create Date: 2026-09-08 16:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = 'd9f1a2b3c4e5'
down_revision: Union[str, None] = '89da3e5d27e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)

    # 1. Update PostgreSQL subscription_status enum if running on Postgres
    if conn.dialect.name == "postgresql":
        new_enum_values = [
            "DRAFT",
            "PENDING_ACTIVATION",
            "EXPIRED",
            "draft",
            "pending_activation",
            "active",
            "trialing",
            "past_due",
            "paused",
            "cancelled",
            "expired",
        ]
        for val in new_enum_values:
            try:
                conn.execute(text(f"ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS '{val}'"))
            except Exception:
                pass

    # 2. Add columns if missing in subscriptions table
    existing_cols = {c["name"] for c in insp.get_columns("subscriptions")} if insp.has_table("subscriptions") else set()

    columns_to_add = [
        ("billing_frequency", sa.Column("billing_frequency", sa.String(length=32), nullable=False, server_default="monthly")),
        ("currency", sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR")),
        ("pricing_model", sa.Column("pricing_model", sa.String(length=32), nullable=False, server_default="flat")),
        ("unit_price", sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0")),
        ("subtotal", sa.Column("subtotal", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0")),
        ("discount_amount", sa.Column("discount_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0")),
        ("tax_amount", sa.Column("tax_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0")),
        ("total_amount", sa.Column("total_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0")),
        ("auto_renewal", sa.Column("auto_renewal", sa.Boolean(), nullable=False, server_default=sa.text("true"))),
        ("cancellation_reason", sa.Column("cancellation_reason", sa.Text(), nullable=True)),
        ("trial_start", sa.Column("trial_start", sa.Date(), nullable=True)),
        ("updated_by_id", sa.Column("updated_by_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)),
    ]

    for col_name, col_def in columns_to_add:
        if col_name not in existing_cols:
            op.add_column("subscriptions", col_def)

    # 3. Add indexes if missing
    try:
        op.create_index("ix_subscriptions_status", "subscriptions", ["status"], if_not_exists=True)
    except Exception:
        pass
    try:
        op.create_index("ix_subscriptions_next_billing_date", "subscriptions", ["next_billing_date"], if_not_exists=True)
    except Exception:
        pass
    try:
        op.create_index("ix_subscriptions_org_status", "subscriptions", ["organization_id", "status"], if_not_exists=True)
    except Exception:
        pass


def downgrade() -> None:
    pass

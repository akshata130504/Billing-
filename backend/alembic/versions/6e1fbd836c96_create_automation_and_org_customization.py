"""create_automation_and_org_customization

Revision ID: 6e1fbd836c96
Revises: d9f1a2b3c4e5
Create Date: 2026-09-08 16:42:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import backend.app.models  # noqa: F401
from backend.app.core.database import Base


# revision identifiers, used by Alembic.
revision: str = '6e1fbd836c96'
down_revision: Union[str, None] = 'd9f1a2b3c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # New tables (automation_rules, automation_executions): checkfirst=True only
    # creates tables that don't exist yet, matching this project's established
    # migration idiom. It does NOT alter existing tables, so the new Organization
    # columns below need explicit add_column calls.
    Base.metadata.create_all(bind=conn, checkfirst=True)

    with op.batch_alter_table("organizations") as batch_op:
        batch_op.add_column(sa.Column("brand_color", sa.String(length=7), nullable=True))
        batch_op.add_column(sa.Column("quote_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("quote_terms", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("date_format", sa.String(length=20), nullable=False, server_default="DD/MM/YYYY"))
        batch_op.add_column(sa.Column("decimal_display_precision", sa.Integer(), nullable=False, server_default="2"))
        batch_op.add_column(sa.Column("default_dashboard_range", sa.String(length=20), nullable=False, server_default="30_days"))
        batch_op.add_column(sa.Column("table_density", sa.String(length=12), nullable=False, server_default="comfortable"))


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_column("table_density")
        batch_op.drop_column("default_dashboard_range")
        batch_op.drop_column("decimal_display_precision")
        batch_op.drop_column("date_format")
        batch_op.drop_column("quote_terms")
        batch_op.drop_column("quote_notes")
        batch_op.drop_column("brand_color")
    op.drop_table("automation_executions")
    op.drop_table("automation_rules")

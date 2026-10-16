"""create_catalog_and_cpq_tables

Revision ID: bb647ceacf66
Revises:
Create Date: 2026-09-08 12:55:30.450707

"""
from typing import Sequence, Union

from alembic import op
import backend.app.models  # noqa: F401
from backend.app.core.database import Base


# revision identifiers, used by Alembic.
revision: str = 'bb647ceacf66'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    Base.metadata.create_all(bind=conn, checkfirst=True)


def downgrade() -> None:
    catalog_cpq_tables = [
        "cpq_deal_items",
        "cpq_deals",
        "cpq_rules",
        "bundle_items",
        "price_book_entries",
        "price_books",
        "offerings",
    ]
    for table_name in catalog_cpq_tables:
        op.drop_table(table_name)

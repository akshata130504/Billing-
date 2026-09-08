"""fix_invoice_and_quote_item_offering_columns

The Product Catalog & CPQ work added `offering_id` and `pricing_explanation`
to the InvoiceItem/QuoteItem models, but no migration ever added those
columns to an already-existing database (the very first migration predates
those model fields, and every migration since has used
`Base.metadata.create_all(checkfirst=True)`, which only creates whole new
tables — never alters an existing one). This was live schema drift: any
endpoint touching invoice or quote line items errored with
`UndefinedColumn: invoice_items.offering_id does not exist`.

Revision ID: 89da3e5d27e3
Revises: bb647ceacf66
Create Date: 2026-09-08 17:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '89da3e5d27e3'
down_revision: Union[str, None] = 'bb647ceacf66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("invoice_items", "quote_items")


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    for table in _TABLES:
        existing = {c["name"] for c in insp.get_columns(table)}
        with op.batch_alter_table(table) as batch_op:
            if "offering_id" not in existing:
                batch_op.add_column(sa.Column("offering_id", sa.String(length=36), sa.ForeignKey("offerings.id", ondelete="SET NULL"), nullable=True))
            if "pricing_explanation" not in existing:
                batch_op.add_column(sa.Column("pricing_explanation", sa.Text(), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("pricing_explanation")
            batch_op.drop_column("offering_id")

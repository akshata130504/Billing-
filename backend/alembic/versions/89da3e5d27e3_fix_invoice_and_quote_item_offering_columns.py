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
Revises: cbbe51c36b05
Create Date: 2026-09-08 17:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '89da3e5d27e3'
down_revision: Union[str, None] = 'cbbe51c36b05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("invoice_items", "quote_items")


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    for table in _TABLES:
        existing = {c["name"] for c in insp.get_columns(table)}
        missing = [c for c in ("offering_id", "pricing_explanation") if c not in existing]
        # Only enter batch mode when there is something to add. On SQLite
        # batch_alter_table rebuilds the table by reflecting it, which fails with
        # "Constraint must have a name" if the table carries an unnamed
        # constraint - so an unconditional no-op batch is not actually a no-op.
        if not missing:
            continue
        with op.batch_alter_table(table) as batch_op:
            if "offering_id" in missing:
                # The FK is named explicitly: SQLite batch mode cannot reflect
                # an unnamed constraint on any later migration touching this table.
                batch_op.add_column(
                    sa.Column(
                        "offering_id",
                        sa.String(length=36),
                        sa.ForeignKey(
                            "offerings.id",
                            ondelete="SET NULL",
                            name=f"fk_{table}_offering_id_offerings",
                        ),
                        nullable=True,
                    )
                )
            if "pricing_explanation" in missing:
                batch_op.add_column(sa.Column("pricing_explanation", sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    for table in _TABLES:
        existing = {c["name"] for c in insp.get_columns(table)}
        present = [c for c in ("pricing_explanation", "offering_id") if c in existing]
        if not present:
            continue
        with op.batch_alter_table(table) as batch_op:
            for column in present:
                batch_op.drop_column(column)

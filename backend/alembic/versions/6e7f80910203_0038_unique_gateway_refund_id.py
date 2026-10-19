"""0038_unique_gateway_refund_id

refunds.gateway_refund_id: a UNIQUE index (NULLs allowed, so manual refunds without a gateway id
are unaffected). One Razorpay refund can then never be booked twice, whatever the writer and
database; the refund and webhook paths already deduplicate in code under the payment row lock.

Defensive like 0018: when duplicates already exist the index is skipped with a warning instead
of failing startup (a failed migration keeps the API down); reconcile them, then re-run.

Revision ID: 5d6e7f809102
Revises: 4c5d6e7f8091
Create Date: 2026-10-16 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e7f80910203'
down_revision: Union[str, None] = '5d6e7f809102'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX = 'uq_refunds_gateway_refund_id'


def _has_index() -> bool:
    return any(ix.get('name') == INDEX for ix in sa.inspect(op.get_bind()).get_indexes('refunds'))


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table('refunds') or _has_index():
        return
    duplicates = op.get_bind().execute(
        sa.text(
            "SELECT gateway_refund_id FROM refunds WHERE gateway_refund_id IS NOT NULL "
            "GROUP BY gateway_refund_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if duplicates:
        print(
            "WARNING [0038]: skipped the unique index on refunds.gateway_refund_id - duplicate gateway "
            f"refund ids exist ({', '.join(str(r[0]) for r in duplicates[:10])}). Reconcile them (each "
            "Razorpay refund may be booked once), then create the index manually: "
            f"CREATE UNIQUE INDEX {INDEX} ON refunds (gateway_refund_id);"
        )
        return
    op.create_index(INDEX, 'refunds', ['gateway_refund_id'], unique=True)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('refunds') and _has_index():
        op.drop_index(INDEX, table_name='refunds')

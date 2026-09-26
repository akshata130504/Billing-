"""0019_meter_pricing_scheduler_heartbeat

Adds:
  * usage_meters.unit_price - per-meter flat usage rate (usage used to be rated at the
    plan's recurring price)
  * scheduler_heartbeats - last-run bookkeeping for the billing scheduler
  * uq_invoices_subscription_period - partial unique index on
    invoices(subscription_id, period_start) for non-void period invoices, the
    database-level backstop against double-invoicing a subscription period.
    Skipped (with a warning) when existing data already violates it.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERIOD_INDEX = 'uq_invoices_subscription_period'
# SQLAlchemy's Enum stores member NAMES, so a void invoice's status is 'VOID'.
PERIOD_INDEX_WHERE = "status <> 'VOID' AND subscription_id IS NOT NULL AND period_start IS NOT NULL"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table_name, column_name):
    insp = _inspector()
    if not insp.has_table(table_name):
        return False
    return column_name in {c["name"] for c in insp.get_columns(table_name)}


def _has_index(table_name, index_name):
    insp = _inspector()
    if not insp.has_table(table_name):
        return False
    return index_name in {ix["name"] for ix in insp.get_indexes(table_name)}


def _create_table(table_name, *args, **kwargs):
    if not _inspector().has_table(table_name):
        op.create_table(table_name, *args, **kwargs)


def _drop_table(table_name):
    if _inspector().has_table(table_name):
        op.drop_table(table_name)


def _period_duplicates_exist() -> bool:
    row = op.get_bind().execute(
        sa.text(
            "SELECT subscription_id, period_start FROM invoices "
            f"WHERE {PERIOD_INDEX_WHERE} "
            "GROUP BY subscription_id, period_start HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    return row is not None


def upgrade() -> None:
    if _inspector().has_table('usage_meters') and not _has_column('usage_meters', 'unit_price'):
        with op.batch_alter_table('usage_meters') as batch_op:
            batch_op.add_column(sa.Column('unit_price', sa.Numeric(precision=18, scale=4), nullable=True))

    _create_table(
        'scheduler_heartbeats',
        sa.Column('job_name', sa.String(length=64), nullable=False),
        sa.Column('last_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_counts', sa.JSON(), nullable=True),
        sa.Column('total_runs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('job_name'),
    )

    if _inspector().has_table('invoices') and not _has_index('invoices', PERIOD_INDEX):
        if _period_duplicates_exist():
            # Do not fail the deploy on legacy duplicates: they need a human decision
            # (void one of each pair) before the constraint can be enforced.
            print(
                f"WARNING: {PERIOD_INDEX} not created - invoices already contain duplicate "
                "non-void (subscription_id, period_start) rows. Void the duplicates and re-run."
            )
        else:
            op.create_index(
                PERIOD_INDEX,
                'invoices',
                ['subscription_id', 'period_start'],
                unique=True,
                postgresql_where=sa.text(PERIOD_INDEX_WHERE),
                sqlite_where=sa.text(PERIOD_INDEX_WHERE),
            )


def downgrade() -> None:
    if _has_index('invoices', PERIOD_INDEX):
        op.drop_index(PERIOD_INDEX, table_name='invoices')
    _drop_table('scheduler_heartbeats')
    if _has_column('usage_meters', 'unit_price'):
        with op.batch_alter_table('usage_meters') as batch_op:
            batch_op.drop_column('unit_price')

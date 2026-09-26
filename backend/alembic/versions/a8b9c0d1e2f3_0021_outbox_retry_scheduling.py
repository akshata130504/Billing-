"""0021_outbox_retry_scheduling

Adds retry scheduling / lease columns to outbox_events so the outbox processor
can back off failed events (next_attempt_at) and reclaim rows stuck in
PROCESSING after a worker crash (locked_at).

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table_name, column_name):
    insp = _inspector()
    if not insp.has_table(table_name):
        return False
    return column_name in {c["name"] for c in insp.get_columns(table_name)}


def _add_column(table_name, column):
    if _inspector().has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _drop_column(table_name, column_name):
    if _has_column(table_name, column_name):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column(column_name)


def _create_index(index_name, table_name, *args, **kwargs):
    insp = _inspector()
    if not insp.has_table(table_name):
        return
    if index_name in {ix["name"] for ix in insp.get_indexes(table_name)}:
        return
    op.create_index(index_name, table_name, *args, **kwargs)


def _drop_index(index_name, table_name=None, **kwargs):
    insp = _inspector()
    if table_name is None or not insp.has_table(table_name):
        return
    if index_name not in {ix["name"] for ix in insp.get_indexes(table_name)}:
        return
    op.drop_index(index_name, table_name, **kwargs)


def upgrade() -> None:
    _add_column('outbox_events', sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True))
    _add_column('outbox_events', sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True))
    _create_index('ix_outbox_events_next_attempt_at', 'outbox_events', ['next_attempt_at'], unique=False)


def downgrade() -> None:
    _drop_index('ix_outbox_events_next_attempt_at', 'outbox_events')
    _drop_column('outbox_events', 'locked_at')
    _drop_column('outbox_events', 'next_attempt_at')

"""0020_totp_and_login_throttles

Two-factor authentication (TOTP) columns on users and the per-(account, IP)
login throttle table that replaces the hard account lockout.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-09-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e6f7a8b9c0d1'
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
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(column)


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


def _drop_index(index_name, table_name):
    insp = _inspector()
    if not insp.has_table(table_name):
        return
    if index_name not in {ix["name"] for ix in insp.get_indexes(table_name)}:
        return
    op.drop_index(index_name, table_name)


def upgrade() -> None:
    _add_column('users', sa.Column('totp_secret', sa.String(length=255), nullable=True))
    _add_column('users', sa.Column('totp_enabled_at', sa.DateTime(timezone=True), nullable=True))
    _add_column('users', sa.Column('totp_last_used_step', sa.Integer(), nullable=True))

    if not _inspector().has_table('login_throttles'):
        op.create_table(
            'login_throttles',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('scope', sa.String(length=16), nullable=False),
            sa.Column('subject', sa.String(length=255), nullable=False),
            sa.Column('ip_address', sa.String(length=64), nullable=False, server_default=''),
            sa.Column('failures', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('scope', 'subject', 'ip_address', name='uq_login_throttle_key'),
        )
    _create_index('ix_login_throttles_subject', 'login_throttles', ['subject'])


def downgrade() -> None:
    _drop_index('ix_login_throttles_subject', 'login_throttles')
    if _inspector().has_table('login_throttles'):
        op.drop_table('login_throttles')
    _drop_column('users', 'totp_last_used_step')
    _drop_column('users', 'totp_enabled_at')
    _drop_column('users', 'totp_secret')

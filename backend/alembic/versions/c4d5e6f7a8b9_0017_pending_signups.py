"""0017_pending_signups

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _create_table(table_name, *args, **kwargs):
    if not _inspector().has_table(table_name):
        op.create_table(table_name, *args, **kwargs)


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


def _drop_table(table_name):
    if _inspector().has_table(table_name):
        op.drop_table(table_name)


def upgrade() -> None:
    _create_table(
        'pending_signups',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('organization_name', sa.String(length=200), nullable=False),
        sa.Column('full_name', sa.String(length=200), nullable=False),
        sa.Column('hashed_password', sa.String(length=128), nullable=False),
        sa.Column('otp_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index('ix_pending_signups_email', 'pending_signups', ['email'], unique=True)


def downgrade() -> None:
    _drop_index('ix_pending_signups_email', 'pending_signups')
    _drop_table('pending_signups')

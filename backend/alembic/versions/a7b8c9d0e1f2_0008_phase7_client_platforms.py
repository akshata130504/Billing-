"""0008_phase7_client_platforms

Revision ID: a7b8c9d0e1f2
Revises: e5f6a7b8c9d0
Create Date: 2026-09-08 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- idempotent DDL helpers ---------------------------------------------------
# The baseline migration (bb647ceacf66) builds the schema with
# Base.metadata.create_all(), so by the time this revision runs the tables it
# declares may already exist. Mirrors the guard style used by the lifecycle /
# timesheet migrations.


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
        'devices',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('device_identifier', sa.String(length=255), nullable=False),
        sa.Column('device_name', sa.String(length=150), nullable=True),
        sa.Column('platform', sa.Enum('windows', 'macos', 'android', 'ios', name='device_platform'), nullable=False),
        sa.Column('os_version', sa.String(length=50), nullable=True),
        sa.Column('app_version', sa.String(length=50), nullable=True),
        sa.Column('push_token', sa.String(length=500), nullable=True),
        sa.Column(
            'trust_status',
            sa.Enum('pending', 'trusted', 'revoked', name='device_trust_status'),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trusted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_reason', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'user_id', 'device_identifier', name='uq_device_identifier_per_user'),
    )
    _create_index(op.f('ix_devices_organization_id'), 'devices', ['organization_id'], unique=False)
    _create_index(op.f('ix_devices_user_id'), 'devices', ['user_id'], unique=False)
    _create_index(op.f('ix_devices_trust_status'), 'devices', ['trust_status'], unique=False)


def downgrade() -> None:
    _drop_table('devices')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute('DROP TYPE IF EXISTS device_trust_status;')
        op.execute('DROP TYPE IF EXISTS device_platform;')

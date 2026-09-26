"""0025_notification_preferences_and_read_state

Server-side, tenant- and user-scoped persistence for what used to live in the browser's
localStorage:

- user_notification_preferences: one row per (organization, user) holding the validated
  in-app notification preference map.
- notification_read_states: read / dismissed markers for header (action-center)
  notifications, unique per (organization, user, notification_key).

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2026-09-26 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c4d5e6f7a8b'
down_revision: Union[str, None] = '2b3c4d5e6f7a'
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
        'user_notification_preferences',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('preferences', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'user_id', name='uq_user_notif_prefs_org_user'),
    )
    _create_index('ix_user_notification_preferences_organization_id', 'user_notification_preferences', ['organization_id'])
    _create_index('ix_user_notification_preferences_user_id', 'user_notification_preferences', ['user_id'])

    _create_table(
        'notification_read_states',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('notification_key', sa.String(length=160), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'organization_id', 'user_id', 'notification_key', name='uq_notif_read_state_org_user_key'
        ),
    )
    _create_index('ix_notification_read_states_organization_id', 'notification_read_states', ['organization_id'])
    _create_index(
        'ix_notif_read_states_user_org_updated',
        'notification_read_states',
        ['user_id', 'organization_id', 'updated_at'],
    )


def downgrade() -> None:
    _drop_index('ix_notif_read_states_user_org_updated', 'notification_read_states')
    _drop_index('ix_notification_read_states_organization_id', 'notification_read_states')
    _drop_table('notification_read_states')
    _drop_index('ix_user_notification_preferences_user_id', 'user_notification_preferences')
    _drop_index('ix_user_notification_preferences_organization_id', 'user_notification_preferences')
    _drop_table('user_notification_preferences')

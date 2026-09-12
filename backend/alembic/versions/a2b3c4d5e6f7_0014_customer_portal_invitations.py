"""0014_customer_portal_invitations

Revision ID: a2b3c4d5e6f7
Revises: f3a4b5c6d7e8
Create Date: 2026-09-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f3a4b5c6d7e8'
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
        'customer_portal_invitations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('customer_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('invited_by_id', sa.String(length=36), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_customer_portal_invitations_organization_id'), 'customer_portal_invitations', ['organization_id'], unique=False)
    _create_index(op.f('ix_customer_portal_invitations_customer_id'), 'customer_portal_invitations', ['customer_id'], unique=False)
    _create_index(op.f('ix_customer_portal_invitations_email'), 'customer_portal_invitations', ['email'], unique=False)
    _create_index(op.f('ix_customer_portal_invitations_token_hash'), 'customer_portal_invitations', ['token_hash'], unique=True)
    _create_index(op.f('ix_customer_portal_invitations_expires_at'), 'customer_portal_invitations', ['expires_at'], unique=False)


def downgrade() -> None:
    _drop_index(op.f('ix_customer_portal_invitations_expires_at'), table_name='customer_portal_invitations')
    _drop_index(op.f('ix_customer_portal_invitations_token_hash'), table_name='customer_portal_invitations')
    _drop_index(op.f('ix_customer_portal_invitations_email'), table_name='customer_portal_invitations')
    _drop_index(op.f('ix_customer_portal_invitations_customer_id'), table_name='customer_portal_invitations')
    _drop_index(op.f('ix_customer_portal_invitations_organization_id'), table_name='customer_portal_invitations')
    _drop_table('customer_portal_invitations')

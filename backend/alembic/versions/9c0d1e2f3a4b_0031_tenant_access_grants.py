"""0031_tenant_access_grants

Platform-administration phase 4 (docs/platform-administration-design.md sections 6, 7, 12, 15):
tenant_access_grants - scoped, time-limited, approved access for platform staff to ONE tenant,
including break-glass emergency grants approved by a second Platform Administrator.

Database constraints: approver differs from requester; expiry after approval; an emergency grant
is never approved by a tenant user; duration 5-240 minutes; at most one open grant per staff
member per organization (partial unique index). All foreign keys RESTRICT (grants are never
deleted), except the tenant approver/denier (SET NULL if that user is removed).

New table only; no existing table or row is touched.

Revision ID: 9c0d1e2f3a4b
Revises: 8b9c0d1e2f3a
Create Date: 2026-10-01 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c0d1e2f3a4b'
down_revision: Union[str, None] = '8b9c0d1e2f3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OPEN = "status IN ('pending', 'approved', 'active')"


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('tenant_access_grants'):
        return
    op.create_table(
        'tenant_access_grants',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('requested_by_staff_id', sa.String(length=36), nullable=False),
        sa.Column('approved_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('approved_by_staff_id', sa.String(length=36), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('ticket_ref', sa.String(length=100), nullable=False),
        sa.Column('requested_duration_minutes', sa.Integer(), nullable=False),
        sa.Column('is_emergency', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_entered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_by_kind', sa.String(length=16), nullable=True),
        sa.Column('revoked_by_id', sa.String(length=36), nullable=True),
        sa.Column('revoke_reason', sa.String(length=300), nullable=True),
        sa.Column('denied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('denied_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('denied_reason', sa.String(length=300), nullable=True),
        sa.Column('current_token_jti', sa.String(length=64), nullable=True),
        sa.Column('request_count', sa.Integer(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by_staff_id', sa.String(length=36), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.CheckConstraint("approved_by_staff_id IS NULL OR approved_by_staff_id <> requested_by_staff_id",
                           name='ck_grant_approver_not_requester'),
        sa.CheckConstraint("expires_at IS NULL OR approved_at IS NULL OR expires_at > approved_at",
                           name='ck_grant_expiry_after_approval'),
        sa.CheckConstraint("NOT is_emergency OR approved_by_user_id IS NULL", name='ck_grant_emergency_staff_approval'),
        sa.CheckConstraint("requested_duration_minutes BETWEEN 5 AND 240", name='ck_grant_duration'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['requested_by_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['denied_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reviewed_by_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tenant_access_grants_status', 'tenant_access_grants', ['status'])
    op.create_index('ix_tenant_access_grants_expires_at', 'tenant_access_grants', ['expires_at'])
    op.create_index('ix_tenant_access_grants_org_status', 'tenant_access_grants', ['organization_id', 'status'])
    op.create_index('ix_tenant_access_grants_staff_status', 'tenant_access_grants', ['requested_by_staff_id', 'status'])
    op.create_index('uq_tenant_access_grants_one_open', 'tenant_access_grants', ['requested_by_staff_id', 'organization_id'],
                    unique=True, postgresql_where=sa.text(OPEN), sqlite_where=sa.text(OPEN))


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('tenant_access_grants'):
        op.drop_table('tenant_access_grants')

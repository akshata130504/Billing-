"""0027_platform_identity

Platform-administration phase 2 (docs/platform-administration-design.md): a separate identity for
Rooman platform staff, independent of tenant users and memberships.

- platform_staff: the principal (email, bcrypt password hash, role, mandatory encrypted TOTP).
- platform_sessions: one row per signed-in device; only a hash of the refresh secret is stored.
- platform_login_challenges: single-use, short-lived second step of sign-in (password -> TOTP).
- platform_audit_logs: append-only security events; no reference to any organization.

role is a VARCHAR (non-native Enum in the model), constrained on PostgreSQL. Foreign keys are
ON DELETE RESTRICT: staff are deactivated, never deleted, so their history is never lost. The
migration only creates new tables; no existing table is altered.

Revision ID: 5e6f7a8b9c0d
Revises: 4d5e6f7a8b9c
Create Date: 2026-09-30 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e6f7a8b9c0d'
down_revision: Union[str, None] = '4d5e6f7a8b9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_CHECK = 'ck_platform_staff_role'
ROLE_VALUES = ('platform_administrator', 'platform_operations', 'platform_support')


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _create_index(index_name, table_name, columns, unique=False):
    if index_name in {ix['name'] for ix in _inspector().get_indexes(table_name)}:
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not _has_table('platform_staff'):
        op.create_table(
            'platform_staff',
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('full_name', sa.String(length=200), nullable=False),
            sa.Column('hashed_password', sa.String(length=255), nullable=False),
            sa.Column('role', sa.String(length=32), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('totp_secret', sa.String(length=255), nullable=True),
            sa.Column('totp_enabled_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('totp_last_used_step', sa.Integer(), nullable=True),
            sa.Column('tokens_valid_after', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
    _create_index('ix_platform_staff_email', 'platform_staff', ['email'], unique=True)
    if op.get_bind().dialect.name == 'postgresql':
        existing = {c['name'] for c in _inspector().get_check_constraints('platform_staff')}
        if ROLE_CHECK not in existing:
            allowed = ", ".join(f"'{v}'" for v in ROLE_VALUES)
            op.create_check_constraint(ROLE_CHECK, 'platform_staff', f"role IN ({allowed})")

    if not _has_table('platform_audit_logs'):
        op.create_table(
            'platform_audit_logs',
            sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('platform_staff_id', sa.String(length=36), nullable=True),
            sa.Column('staff_email_snapshot', sa.String(length=255), nullable=True),
            sa.Column('action', sa.String(length=64), nullable=False),
            sa.Column('result', sa.String(length=16), nullable=False),
            sa.Column('session_id', sa.String(length=36), nullable=True),
            sa.Column('ip_address', sa.String(length=64), nullable=True),
            sa.Column('user_agent', sa.String(length=400), nullable=True),
            sa.Column('details', sa.JSON(), nullable=True),
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.ForeignKeyConstraint(['platform_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
        )
    _create_index('ix_platform_audit_logs_action', 'platform_audit_logs', ['action'])
    _create_index('ix_platform_audit_logs_occurred_at', 'platform_audit_logs', ['occurred_at'])
    _create_index('ix_platform_audit_logs_platform_staff_id', 'platform_audit_logs', ['platform_staff_id'])
    _create_index('ix_platform_audit_logs_session_id', 'platform_audit_logs', ['session_id'])

    if not _has_table('platform_login_challenges'):
        op.create_table(
            'platform_login_challenges',
            sa.Column('staff_id', sa.String(length=36), nullable=False),
            sa.Column('token_hash', sa.String(length=64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('failed_attempts', sa.Integer(), nullable=False),
            sa.Column('ip_address', sa.String(length=64), nullable=True),
            sa.Column('user_agent', sa.String(length=400), nullable=True),
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.ForeignKeyConstraint(['staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
        )
    _create_index('ix_platform_login_challenges_staff_id', 'platform_login_challenges', ['staff_id'])
    _create_index('ix_platform_login_challenges_token_hash', 'platform_login_challenges', ['token_hash'], unique=True)

    if not _has_table('platform_sessions'):
        op.create_table(
            'platform_sessions',
            sa.Column('staff_id', sa.String(length=36), nullable=False),
            sa.Column('refresh_token_hash', sa.String(length=64), nullable=False),
            sa.Column('previous_refresh_token_hash', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('idle_expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('mfa_verified_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('revoke_reason', sa.String(length=64), nullable=True),
            sa.Column('ip_address', sa.String(length=64), nullable=True),
            sa.Column('user_agent', sa.String(length=400), nullable=True),
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.ForeignKeyConstraint(['staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
        )
    _create_index('ix_platform_sessions_previous_refresh_token_hash', 'platform_sessions', ['previous_refresh_token_hash'])
    _create_index('ix_platform_sessions_refresh_token_hash', 'platform_sessions', ['refresh_token_hash'], unique=True)
    _create_index('ix_platform_sessions_staff_id', 'platform_sessions', ['staff_id'])


def downgrade() -> None:
    # Children first (they reference platform_staff).
    for table in ('platform_sessions', 'platform_login_challenges', 'platform_audit_logs', 'platform_staff'):
        if _has_table(table):
            op.drop_table(table)

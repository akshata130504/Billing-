"""0036_trial_subscription_lifecycle

Self-service organizations still need a Platform Administrator's approval (PENDING_APPROVAL ->
ACTIVE). Approval starts a free trial; access after the trial comes from a subscription request
approved by a Platform Administrator:

- organizations.status: 'trial' and 'trial_expired' are added to ck_organizations_status (PostgreSQL)
  so rows written by the effective-status logic of earlier builds stay valid; new code keeps
  approved organizations ACTIVE and computes the trial from the columns below.
- organizations: trial_started_at, trial_ends_at, seat_limit (NULL = unlimited) and module_access
  ('unrestricted' for every existing organization via the server default, so nobody loses access;
  self-service signups are created with 'trial' by the application).
- organization_entitlements and subscription_requests: new tenant tables with row level security
  (the 0032 tenant_isolation_policy).
- No data is changed: organizations waiting for approval keep waiting. The migration touches no
  financial data.

Downgrade: 'trial' / 'trial_expired' organizations go back to 'pending_approval' (never to
'active' - that would grant access nobody approved); the new tables and columns are dropped.

Revision ID: 4c5d6e7f8091
Revises: 3b4c5d6e7f80
Create Date: 2026-10-06 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c5d6e7f8091'
down_revision: Union[str, None] = '3b4c5d6e7f80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_CHECK = 'ck_organizations_status'
NEW_STATUS_VALUES = ('trial', 'trial_expired', 'pending_approval', 'active', 'rejected', 'suspended',
                     'pending_deletion', 'deleted')
OLD_STATUS_VALUES = ('pending_approval', 'active', 'rejected', 'suspended', 'pending_deletion', 'deleted')
ORG_COLUMNS = ('trial_started_at', 'trial_ends_at', 'seat_limit', 'module_access')
RLS_TABLES = ('subscription_requests', 'organization_entitlements')


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _check_constraints(table: str) -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_check_constraints(table)}


def _set_status_check(values) -> None:
    if not _is_postgres():
        return
    if STATUS_CHECK in _check_constraints('organizations'):
        op.drop_constraint(STATUS_CHECK, 'organizations', type_='check')
    allowed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(STATUS_CHECK, 'organizations', f"status IN ({allowed})")


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies WHERE tablename = '{table}' AND policyname = 'tenant_isolation_policy'
            ) THEN
                CREATE POLICY tenant_isolation_policy ON {table}
                    FOR ALL
                    USING (
                        current_setting('app.current_organization_id', true) = '__SYSTEM__'
                        OR organization_id = current_setting('app.current_organization_id', true)
                    )
                    WITH CHECK (
                        current_setting('app.current_organization_id', true) = '__SYSTEM__'
                        OR organization_id = current_setting('app.current_organization_id', true)
                    );
            END IF;
        END $$;
    """)


def upgrade() -> None:
    _set_status_check(NEW_STATUS_VALUES)

    existing = _columns('organizations')
    with op.batch_alter_table('organizations') as batch:
        if 'trial_started_at' not in existing:
            batch.add_column(sa.Column('trial_started_at', sa.DateTime(timezone=True), nullable=True))
        if 'trial_ends_at' not in existing:
            batch.add_column(sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True))
        if 'seat_limit' not in existing:
            batch.add_column(sa.Column('seat_limit', sa.Integer(), nullable=True))
        if 'module_access' not in existing:
            batch.add_column(sa.Column('module_access', sa.String(length=20), nullable=False,
                                       server_default='unrestricted'))

    if not _has_table('subscription_requests'):
        op.create_table(
            'subscription_requests',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('organization_id', sa.String(length=36), nullable=False),
            sa.Column('status', sa.String(length=16), nullable=False),
            sa.Column('modules', sa.JSON(), nullable=False),
            sa.Column('seats', sa.Integer(), nullable=False),
            sa.Column('billing_cycle', sa.String(length=16), nullable=False),
            sa.Column('notes', sa.String(length=1000), nullable=True),
            sa.Column('requested_by_user_id', sa.String(length=36), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('reviewed_by_staff_id', sa.String(length=36), nullable=True),
            sa.Column('decision_reason', sa.String(length=500), nullable=True),
            sa.Column('approved_modules', sa.JSON(), nullable=True),
            sa.Column('approved_seats', sa.Integer(), nullable=True),
            sa.Column('approved_billing_cycle', sa.String(length=16), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['reviewed_by_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
            sa.CheckConstraint("status IN ('submitted', 'approved', 'rejected', 'withdrawn')",
                               name='ck_subscription_request_status'),
            sa.CheckConstraint("billing_cycle IN ('monthly', 'quarterly', 'annual')",
                               name='ck_subscription_request_cycle'),
            sa.CheckConstraint('seats >= 1 AND seats <= 10000', name='ck_subscription_request_seats'),
            sa.CheckConstraint('approved_seats IS NULL OR (approved_seats >= 1 AND approved_seats <= 10000)',
                               name='ck_subscription_request_approved_seats'),
        )
        op.create_index('ix_subscription_requests_organization_id', 'subscription_requests', ['organization_id'])
        op.create_index(
            'uq_subscription_request_one_open', 'subscription_requests', ['organization_id'], unique=True,
            postgresql_where=sa.text("status = 'submitted'"), sqlite_where=sa.text("status = 'submitted'"),
        )

    if not _has_table('organization_entitlements'):
        op.create_table(
            'organization_entitlements',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('organization_id', sa.String(length=36), nullable=False),
            sa.Column('module_key', sa.String(length=40), nullable=False),
            sa.Column('source', sa.String(length=30), nullable=False),
            sa.Column('request_id', sa.String(length=36), nullable=True),
            sa.Column('granted_by_staff_id', sa.String(length=36), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['request_id'], ['subscription_requests.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['granted_by_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('organization_id', 'module_key', name='uq_org_entitlement_module'),
        )
        op.create_index('ix_organization_entitlements_organization_id', 'organization_entitlements',
                        ['organization_id'])

    if _is_postgres():
        for table in RLS_TABLES:
            _enable_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    # Never 'active': these organizations were never approved under the old lifecycle.
    bind.execute(sa.text("UPDATE organizations SET status = 'pending_approval' "
                         "WHERE status IN ('trial', 'trial_expired')"))
    for table in reversed(RLS_TABLES):  # entitlements reference requests
        if _has_table(table):
            if _is_postgres():
                op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
            op.drop_table(table)
    existing = _columns('organizations')
    with op.batch_alter_table('organizations') as batch:
        for column in reversed(ORG_COLUMNS):
            if column in existing:
                batch.drop_column(column)
    _set_status_check(OLD_STATUS_VALUES)

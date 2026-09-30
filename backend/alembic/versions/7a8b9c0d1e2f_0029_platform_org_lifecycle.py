"""0029_platform_org_lifecycle

Platform-administration phase 3 (docs/platform-administration-design.md sections 8, 10 and 15):

- organizations: status_changed_at, status_changed_by_staff_id (FK platform_staff, RESTRICT),
  status_reason, deletion_scheduled_for - the last lifecycle transition. Existing rows keep NULLs;
  status and jobs_paused (0026) are unchanged.
- platform_audit_logs: staff_role_snapshot, target_type, target_id, organization_id (indexed, NO
  foreign key - platform history outlives tenants), organization_name_snapshot, reason, ticket_ref.
  On PostgreSQL these are plain ADD COLUMNs: existing rows are not rewritten, and the append-only
  triggers and privileges from 0028 stay exactly as they were.

Only nullable columns are added; no data is changed.

Revision ID: 7a8b9c0d1e2f
Revises: 6f7a8b9c0d1e
Create Date: 2026-09-30 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8b9c0d1e2f'
down_revision: Union[str, None] = '6f7a8b9c0d1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORG_FK = 'fk_organizations_status_changed_by_staff_id_platform_staff'
AUDIT_ORG_INDEX = 'ix_platform_audit_logs_organization_id'


def _org_columns():
    return [
        sa.Column('status_changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status_changed_by_staff_id', sa.String(length=36), nullable=True),
        sa.Column('status_reason', sa.String(length=500), nullable=True),
        sa.Column('deletion_scheduled_for', sa.DateTime(timezone=True), nullable=True),
    ]


def _audit_columns():
    return [
        sa.Column('staff_role_snapshot', sa.String(length=32), nullable=True),
        sa.Column('target_type', sa.String(length=32), nullable=True),
        sa.Column('target_id', sa.String(length=36), nullable=True),
        sa.Column('organization_id', sa.String(length=36), nullable=True),
        sa.Column('organization_name_snapshot', sa.String(length=200), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('ticket_ref', sa.String(length=100), nullable=True),
    ]


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set:
    return {c['name'] for c in _inspector().get_columns(table)}


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def upgrade() -> None:
    existing = _columns('organizations')
    fks = {fk.get('name') for fk in _inspector().get_foreign_keys('organizations')}
    with op.batch_alter_table('organizations') as batch:
        for column in _org_columns():
            if column.name not in existing:
                batch.add_column(column)
        if ORG_FK not in fks:
            batch.create_foreign_key(
                ORG_FK, 'platform_staff', ['status_changed_by_staff_id'], ['id'], ondelete='RESTRICT'
            )

    existing = _columns('platform_audit_logs')
    if _is_postgresql():
        for column in _audit_columns():
            if column.name not in existing:
                op.add_column('platform_audit_logs', column)
    else:
        with op.batch_alter_table('platform_audit_logs') as batch:
            for column in _audit_columns():
                if column.name not in existing:
                    batch.add_column(column)
    if AUDIT_ORG_INDEX not in {ix['name'] for ix in _inspector().get_indexes('platform_audit_logs')}:
        op.create_index(AUDIT_ORG_INDEX, 'platform_audit_logs', ['organization_id'])


def downgrade() -> None:
    if AUDIT_ORG_INDEX in {ix['name'] for ix in _inspector().get_indexes('platform_audit_logs')}:
        op.drop_index(AUDIT_ORG_INDEX, table_name='platform_audit_logs')
    existing = _columns('platform_audit_logs')
    names = [c.name for c in reversed(_audit_columns()) if c.name in existing]
    if _is_postgresql():
        for name in names:
            op.drop_column('platform_audit_logs', name)
    else:
        with op.batch_alter_table('platform_audit_logs') as batch:
            for name in names:
                batch.drop_column(name)

    existing = _columns('organizations')
    fks = {fk.get('name') for fk in _inspector().get_foreign_keys('organizations')}
    with op.batch_alter_table('organizations') as batch:
        if ORG_FK in fks:
            batch.drop_constraint(ORG_FK, type_='foreignkey')
        for column in reversed(_org_columns()):
            if column.name in existing:
                batch.drop_column(column.name)

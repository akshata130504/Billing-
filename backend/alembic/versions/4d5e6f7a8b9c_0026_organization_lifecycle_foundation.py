"""0026_organization_lifecycle_foundation

Platform-administration phase 1 (docs/platform-administration-design.md): the foundation for
an organization lifecycle. Nothing in the application changes these values yet.

- organizations.status: 'active' | 'suspended' | 'pending_deletion' | 'deleted'. Stored as a
  VARCHAR (the model uses a non-native Enum), so no PostgreSQL enum type is created. Every
  existing organization becomes 'active' through the server default.
- organizations.jobs_paused: boolean, default false.

The scheduler skips billing automation for any organization that is not 'active' or has
jobs_paused set (services/org_lifecycle.py); for existing organizations nothing changes.

Adding a column with a constant server default is a metadata-only change on PostgreSQL 11+,
so the upgrade does not rewrite or long-lock the organizations table.

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
Create Date: 2026-09-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d5e6f7a8b9c'
down_revision: Union[str, None] = '3c4d5e6f7a8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_CHECK = 'ck_organizations_status'
STATUS_VALUES = ('active', 'suspended', 'pending_deletion', 'deleted')


def _columns(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return set()
    return {c['name'] for c in insp.get_columns(table)}


def _check_constraints(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return set()
    return {c['name'] for c in insp.get_check_constraints(table)}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def upgrade() -> None:
    columns = _columns('organizations')
    if not columns:
        return
    if 'status' not in columns:
        op.add_column(
            'organizations',
            sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        )
    if 'jobs_paused' not in columns:
        op.add_column(
            'organizations',
            sa.Column('jobs_paused', sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    # PostgreSQL only: SQLite cannot add a CHECK constraint to an existing table without
    # rebuilding it. The model's Enum(validate_strings=True) rejects unknown values in the ORM
    # on every database.
    if _is_postgres() and STATUS_CHECK not in _check_constraints('organizations'):
        allowed = ", ".join(f"'{v}'" for v in STATUS_VALUES)
        op.create_check_constraint(STATUS_CHECK, 'organizations', f"status IN ({allowed})")


def downgrade() -> None:
    if _is_postgres() and STATUS_CHECK in _check_constraints('organizations'):
        op.drop_constraint(STATUS_CHECK, 'organizations', type_='check')
    columns = _columns('organizations')
    if 'jobs_paused' in columns:
        op.drop_column('organizations', 'jobs_paused')
    if 'status' in columns:
        op.drop_column('organizations', 'status')

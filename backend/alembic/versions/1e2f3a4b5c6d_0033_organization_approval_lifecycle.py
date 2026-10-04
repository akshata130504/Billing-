"""0033_organization_approval_lifecycle

Platform-administration organization approval lifecycle:
Adds 'pending_approval' and 'rejected' to the allowed organization status lifecycle.

- organizations.status: 'pending_approval' | 'active' | 'rejected' | 'suspended' | 'pending_deletion' | 'deleted'.
- Updates PostgreSQL check constraint ck_organizations_status.

Revision ID: 1e2f3a4b5c6d
Revises: 0d1e2f3a4b5c
Create Date: 2026-10-01 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e2f3a4b5c6d'
down_revision: Union[str, None] = '0d1e2f3a4b5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_CHECK = 'ck_organizations_status'
NEW_STATUS_VALUES = ('pending_approval', 'active', 'rejected', 'suspended', 'pending_deletion', 'deleted')
OLD_STATUS_VALUES = ('active', 'suspended', 'pending_deletion', 'deleted')


def _check_constraints(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return set()
    return {c['name'] for c in insp.get_check_constraints(table)}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def upgrade() -> None:
    if _is_postgres():
        if STATUS_CHECK in _check_constraints('organizations'):
            op.drop_constraint(STATUS_CHECK, 'organizations', type_='check')
        allowed = ", ".join(f"'{v}'" for v in NEW_STATUS_VALUES)
        op.create_check_constraint(STATUS_CHECK, 'organizations', f"status IN ({allowed})")


def _demote_new_statuses() -> None:
    """Move rows in the 0033-only statuses to one the pre-0033 schema/code understands.

    Both 'pending_approval' (never approved) and 'rejected' (explicitly refused) become
    'suspended', NOT 'active': the old lifecycle has no approval step, so mapping either to
    'active' would silently grant a tenant that was never approved full access and turn on its
    billing automation. 'suspended' keeps it locked out until platform staff act on it, and the
    original state stays visible in status_reason/platform_audit_logs.

    Runs on every dialect: on PostgreSQL it is required before the stricter CHECK constraint
    is re-created (otherwise the ALTER fails on existing rows); on SQLite there is no
    constraint, but the pre-0033 code would still choke on the unknown values, and with no
    such rows the UPDATE is a no-op.
    """
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('organizations'):
        return
    removed = [v for v in NEW_STATUS_VALUES if v not in OLD_STATUS_VALUES]
    bind.execute(
        sa.text("UPDATE organizations SET status = 'suspended' WHERE status IN :removed").bindparams(
            sa.bindparam('removed', value=removed, expanding=True)
        )
    )


def downgrade() -> None:
    _demote_new_statuses()
    if _is_postgres():
        if STATUS_CHECK in _check_constraints('organizations'):
            op.drop_constraint(STATUS_CHECK, 'organizations', type_='check')
        allowed = ", ".join(f"'{v}'" for v in OLD_STATUS_VALUES)
        op.create_check_constraint(STATUS_CHECK, 'organizations', f"status IN ({allowed})")

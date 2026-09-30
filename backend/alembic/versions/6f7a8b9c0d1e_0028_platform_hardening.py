"""0028_platform_hardening

Platform-administration phase 2.5 (security hardening):

- platform_sessions.step_up_at / step_up_expires_at: step-up re-authentication (a fresh TOTP within
  the last few minutes) bound to one session, for sensitive platform actions.
- platform_audit_logs becomes append-only IN THE DATABASE (PostgreSQL): a trigger function rejects
  every UPDATE, DELETE and TRUNCATE, whoever issues it. In addition, UPDATE / DELETE / TRUNCATE
  privileges on this one table are revoked from every role other than the table owner (the role
  running migrations), so the runtime role keeps SELECT and INSERT only. No other table's
  privileges are touched. deploy/sql/least_privilege.sql applies the same REVOKE when it (re)grants.

SQLite (local development) has no roles; there the rule is enforced by application code only.
Downgrade removes the triggers and columns; it does not re-grant the revoked privileges (re-run
deploy/sql/least_privilege.sql for the pre-0028 grants).

Revision ID: 6f7a8b9c0d1e
Revises: 5e6f7a8b9c0d
Create Date: 2026-09-30 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f7a8b9c0d1e'
down_revision: Union[str, None] = '5e6f7a8b9c0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of backend/app/models/platform.py PLATFORM_AUDIT_APPEND_ONLY_* at this revision.
APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION platform_audit_logs_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'platform_audit_logs is append-only: % is not allowed', TG_OP
        USING ERRCODE = '42501';
END
$$
"""
APPEND_ONLY_TRIGGERS = (
    "DROP TRIGGER IF EXISTS platform_audit_logs_no_update_delete ON platform_audit_logs",
    "CREATE TRIGGER platform_audit_logs_no_update_delete BEFORE UPDATE OR DELETE ON platform_audit_logs "
    "FOR EACH ROW EXECUTE FUNCTION platform_audit_logs_append_only()",
    "DROP TRIGGER IF EXISTS platform_audit_logs_no_truncate ON platform_audit_logs",
    "CREATE TRIGGER platform_audit_logs_no_truncate BEFORE TRUNCATE ON platform_audit_logs "
    "FOR EACH STATEMENT EXECUTE FUNCTION platform_audit_logs_append_only()",
)
# Revoke write-after-insert privileges on this table from every non-owner role that holds them.
REVOKE_FROM_NON_OWNERS = """
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT DISTINCT g.grantee
        FROM information_schema.role_table_grants g
        JOIN pg_class c ON c.relname = g.table_name
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = g.table_schema
        WHERE g.table_schema = current_schema()
          AND g.table_name = 'platform_audit_logs'
          AND g.privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE')
          AND g.grantee <> pg_get_userbyid(c.relowner)
    LOOP
        IF r.grantee = 'PUBLIC' THEN
            EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON platform_audit_logs FROM PUBLIC';
        ELSE
            EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON platform_audit_logs FROM %I', r.grantee);
        END IF;
    END LOOP;
END
$$
"""


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def _columns(table: str) -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    existing = _columns('platform_sessions')
    with op.batch_alter_table('platform_sessions') as batch:
        if 'step_up_at' not in existing:
            batch.add_column(sa.Column('step_up_at', sa.DateTime(timezone=True), nullable=True))
        if 'step_up_expires_at' not in existing:
            batch.add_column(sa.Column('step_up_expires_at', sa.DateTime(timezone=True), nullable=True))

    if _is_postgresql():
        op.execute(sa.text(APPEND_ONLY_FUNCTION))
        for statement in APPEND_ONLY_TRIGGERS:
            op.execute(sa.text(statement))
        op.execute(sa.text(REVOKE_FROM_NON_OWNERS))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("DROP TRIGGER IF EXISTS platform_audit_logs_no_truncate ON platform_audit_logs"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS platform_audit_logs_no_update_delete ON platform_audit_logs"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS platform_audit_logs_append_only()"))
    existing = _columns('platform_sessions')
    with op.batch_alter_table('platform_sessions') as batch:
        if 'step_up_expires_at' in existing:
            batch.drop_column('step_up_expires_at')
        if 'step_up_at' in existing:
            batch.drop_column('step_up_at')

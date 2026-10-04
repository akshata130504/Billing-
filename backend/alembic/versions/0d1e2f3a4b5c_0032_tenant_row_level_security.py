"""0032_tenant_row_level_security

Platform-administration defense-in-depth: PostgreSQL Row Level Security (RLS)
on sensitive business tables (docs/platform-administration-design.md sections 13, 18).

Enables RLS and FORCE ROW LEVEL SECURITY on sensitive tenant tables.
Policy ensures queries and mutations fail closed unless:
- app.current_organization_id matches the row's organization_id, OR
- app.current_organization_id is '__SYSTEM__' (for scheduler, migrations, system tasks).

On non-PostgreSQL dialects (e.g. SQLite test runners), this migration safely no-ops.

Revision ID: 0d1e2f3a4b5c
Revises: 9c0d1e2f3a4b
Create Date: 2026-10-01 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0d1e2f3a4b5c'
down_revision: Union[str, None] = '9c0d1e2f3a4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = [
    "customers",
    "invoices",
    "invoice_items",
    "payments",
    "payment_allocations",
    "refunds",
    "quotes",
    "quote_items",
    "subscriptions",
    "credit_notes",
    "credit_note_lines",
    "credit_applications",
    "customer_payment_methods",
    "organization_integrations",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE tablename = '{table}' AND policyname = 'tenant_isolation_policy'
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


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in reversed(RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

"""0037_rls_every_tenant_table

Row level security on EVERY tenant-scoped table.

Migration 0032 put the tenant isolation policy on 14 "sensitive" tables and 0036 on two more, so
the other 66 tables that carry organization_id (TenantMixin models: catalog, quotes/CPQ, dunning,
usage, projects, expenses, automation, AI, outbox/jobs, notifications, portal, ...) were protected
only by the ORM loader filter. Raw SQL, a forgotten filter or an UPDATE/DELETE outside the ORM
select path could cross tenants there. This migration applies the very same policy as 0032 to all
of them: rows are visible and writable only when app.current_organization_id equals the row's
organization_id, or is '__SYSTEM__' (scheduler, outbox, migrations, public token lookups).

backend/tests/test_rls_coverage.py fails when a TenantMixin table is not in 0032 + 0036 + this list,
and (on PostgreSQL) when any table with an organization_id column lacks the forced policy and is not
in its documented exemption list.

On non-PostgreSQL dialects (SQLite test runs) this migration is a no-op.

Revision ID: 5d6e7f809102
Revises: 4c5d6e7f8091
Create Date: 2026-10-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d6e7f809102"
down_revision: Union[str, None] = "4c5d6e7f8091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen list (do not compute it from the models: a migration must not change after it ran).
RLS_TABLES = (
    "ai_action_drafts",
    "ai_conversations",
    "ai_requests",
    "ai_source_references",
    "ai_tool_invocations",
    "approval_requests",
    "automation_actions",
    "automation_logs",
    "automation_rules",
    "automation_schedules",
    "billing_cycles",
    "bundle_items",
    "checkout_sessions",
    "checkout_templates",
    "collection_activities",
    "cpq_deal_items",
    "cpq_deals",
    "cpq_rules",
    "customer_contacts",
    "customer_lifecycles",
    "customer_portal_invitations",
    "customer_portal_settings",
    "customer_portal_users",
    "devices",
    "document_templates",
    "dunning_attempts",
    "dunning_cases",
    "dunning_communications",
    "dunning_policies",
    "durable_jobs",
    "expenses",
    "idempotency_records",
    "import_jobs",
    "inbox_events",
    "invoice_collections",
    "notification_deliveries",
    "notification_read_states",
    "notification_templates",
    "offerings",
    "outbound_webhook_deliveries",
    "outbox_events",
    "payment_attempts",
    "plans",
    "price_book_entries",
    "price_books",
    "price_snapshots",
    "products",
    "project_invoices",
    "projects",
    "promise_to_pay",
    "proration_adjustments",
    "recurring_expenses",
    "reporting_tags",
    "subscription_changes",
    "subscription_items",
    "time_entries",
    "transaction_number_series",
    "trial_conversion_attempts",
    "trial_extensions",
    "trial_periods",
    "trial_reminders",
    "usage_aggregates",
    "usage_events",
    "usage_meters",
    "user_notification_preferences",
    "web_tabs",
)

# Same predicate as 0032 (kept textually identical so the policies are interchangeable).
_PREDICATE = (
    "current_setting('app.current_organization_id', true) = '__SYSTEM__' "
    "OR organization_id = current_setting('app.current_organization_id', true)"
)


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = current_schema() AND tablename = '{table}'
                  AND policyname = 'tenant_isolation_policy'
            ) THEN
                CREATE POLICY tenant_isolation_policy ON {table}
                    FOR ALL
                    USING ({_PREDICATE})
                    WITH CHECK ({_PREDICATE});
            END IF;
        END $$;
    """)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in RLS_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in reversed(RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

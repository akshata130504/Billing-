"""Guard: every tenant-scoped table has the tenant row level security policy.

* Any dialect: every TenantMixin model's table is in one of the RLS migrations (0032, 0036, 0037),
  and every table with an organization_id column is either covered or in EXEMPT with a reason.
  A new tenant table therefore fails this test until a migration puts the policy on it.
* PostgreSQL (TEST_DATABASE_URL): the migrated database really has RLS enabled AND forced, with
  tenant_isolation_policy, on every table with an organization_id column outside EXEMPT; every such
  policy is the same ALL-commands policy (USING = WITH CHECK) as migration 0032; and the policy denies
  a NOSUPERUSER/NOBYPASSRLS role another tenant's rows (read, insert, move, update, delete) and
  shows nothing without a tenant context.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.core.database import Base, engine
from backend.app.models.base import TenantMixin

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
RLS_MIGRATIONS = (
    "0d1e2f3a4b5c_0032_tenant_row_level_security.py",
    "4c5d6e7f8091_0036_trial_subscription_lifecycle.py",
    "5d6e7f809102_0037_rls_every_tenant_table.py",
    "6e7f80910213_0038_upi_autopay_gateway_subscriptions.py",
)

# Tables with an organization_id column that are deliberately NOT under the tenant policy.
EXEMPT = {
    "memberships": "read before any tenant is chosen (login, invitation, organization switch); always filtered by user",
    "refresh_tokens": "looked up by token hash before a tenant context exists (refresh); organization_id nullable",
    "audit_logs": "written before a tenant exists (failed logins, signup) and read by the platform console; organization_id nullable",
    "platform_audit_logs": "platform-wide, append-only (trigger), never tenant-readable through the tenant API",
    "tenant_access_grants": "platform staff grants, checked before the granted tenant context is entered",
    "webhook_events": "payment gateway inbox: the organization is resolved after the signed event is stored; nullable",
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_rls_{name[:12]}", VERSIONS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def covered_tables() -> set[str]:
    out: set[str] = set()
    for name in RLS_MIGRATIONS:
        out |= set(_load(name).RLS_TABLES)
    return out


def tenant_tables() -> set[str]:
    return {m.local_table.name for m in Base.registry.mappers if issubclass(m.class_, TenantMixin)}


def org_column_tables() -> set[str]:
    return {name for name, table in Base.metadata.tables.items() if "organization_id" in table.c}


def test_every_tenant_model_is_in_an_rls_migration():
    missing = sorted(tenant_tables() - covered_tables())
    assert not missing, f"tenant tables without the RLS policy (add them to a new RLS migration): {missing}"


def test_every_organization_table_is_covered_or_exempt_with_a_reason():
    uncovered = org_column_tables() - covered_tables() - set(EXEMPT)
    assert not uncovered, f"tables with organization_id but neither RLS nor an EXEMPT reason: {sorted(uncovered)}"
    assert not (set(EXEMPT) & covered_tables()), "a table cannot be both exempt and covered"
    assert all(len(reason) > 20 for reason in EXEMPT.values())


def test_rls_migrations_name_only_real_tables():
    unknown = covered_tables() - set(Base.metadata.tables)
    assert not unknown, f"RLS migrations name tables that do not exist: {sorted(unknown)}"


postgres_only = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="needs TEST_DATABASE_URL (PostgreSQL)")


@postgres_only
def test_migrated_database_forces_the_policy_on_every_tenant_table():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   EXISTS (SELECT 1 FROM pg_policies p WHERE p.schemaname = n.nspname AND p.tablename = c.relname
                           AND p.policyname = 'tenant_isolation_policy') AS has_policy
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relkind = 'r'
              AND EXISTS (SELECT 1 FROM information_schema.columns col
                          WHERE col.table_schema = n.nspname AND col.table_name = c.relname
                            AND col.column_name = 'organization_id')
        """)).all()
    assert rows, "no tables with organization_id found: is the database migrated?"
    bad = [r.relname for r in rows if r.relname not in EXEMPT and not (r.relrowsecurity and r.relforcerowsecurity and r.has_policy)]
    assert not bad, f"tables with organization_id but without forced tenant RLS: {sorted(bad)}"


@postgres_only
def test_every_tenant_policy_is_the_same_all_commands_policy():
    """One policy per table, for ALL commands (SELECT, INSERT, UPDATE, DELETE), permissive, for every
    role, with WITH CHECK equal to USING and the same expression on every table. So the behaviour
    probed below on one table holds on all of them; a hand-edited or weakened policy fails here."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT tablename, policyname, cmd, permissive, roles::text AS roles, qual, with_check
            FROM pg_policies WHERE schemaname = current_schema()
        """)).all()
    by_table: dict[str, list] = {}
    for r in rows:
        by_table.setdefault(r.tablename, []).append(r)
    expected = tenant_tables() | (covered_tables() & set(Base.metadata.tables))
    assert expected <= set(by_table), f"tenant tables without a policy: {sorted(expected - set(by_table))}"
    reference = by_table["customers"][0].qual  # migration 0032
    assert "app.current_organization_id" in reference and "organization_id" in reference
    wrong = sorted(
        t for t in expected
        if len(by_table[t]) != 1
        or (p := by_table[t][0]).policyname != "tenant_isolation_policy"
        or p.cmd != "ALL" or p.permissive != "PERMISSIVE" or p.roles != "{public}"
        or p.qual != reference or p.with_check != reference
    )
    assert not wrong, f"tables whose tenant policy differs from migration 0032's: {wrong}"


@postgres_only
def test_policy_hides_other_tenants_rows_from_an_unprivileged_role():
    """Superusers bypass RLS, so prove it as a throwaway NOSUPERUSER NOBYPASSRLS role (SET ROLE)."""
    role = f"rls_probe_{uuid.uuid4().hex[:8]}"
    org_a, org_b = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.connect() as conn:
        is_super = conn.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar()
        can_create = conn.execute(text("SELECT rolcreaterole FROM pg_roles WHERE rolname = current_user")).scalar()
        if not (is_super or can_create):
            pytest.skip("the test database user cannot create the probe role")
        conn.rollback()
        trans = conn.begin()
        try:
            conn.execute(text(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS"))
            conn.execute(text(f"GRANT USAGE ON SCHEMA {conn.execute(text('SELECT current_schema()')).scalar()} TO {role}"))
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON products, outbox_events, organizations TO {role}"))
            conn.execute(text("SELECT set_config('app.current_organization_id', '__SYSTEM__', true)"))
            for org in (org_a, org_b):
                conn.execute(text("INSERT INTO organizations (id, name, slug, country, default_currency, timezone, "
                                  "invoice_prefix, invoice_next_number, quote_prefix, quote_next_number, payment_prefix, "
                                  "payment_next_number, subscription_prefix, subscription_next_number, customer_prefix, "
                                  "customer_next_number, default_payment_terms_days, default_tax_rate_pct, "
                                  "discount_approval_threshold_pct, status, jobs_paused, module_access, created_at, updated_at) "
                                  "VALUES (:id, :id, :id, 'IN', 'INR', 'UTC', 'INV-', 1, 'QT-', 1, 'PAY-', 1, 'SUB-', 1, "
                                  "'CUS-', 1, 30, 18, 20, 'active', false, 'unrestricted', now(), now())"), {"id": org})
                conn.execute(text("INSERT INTO outbox_events (id, organization_id, event_type, aggregate_type, aggregate_id, "
                                  "payload, status, retry_count, created_at) VALUES (:id, :org, 'probe', 'probe', 'p', "
                                  "'{}', 'PENDING', 0, now())"), {"id": str(uuid.uuid4()), "org": org})
            conn.execute(text(f"SET LOCAL ROLE {role}"))
            conn.execute(text("SELECT set_config('app.current_organization_id', :o, true)"), {"o": org_a})
            seen = {r[0] for r in conn.execute(text("SELECT organization_id FROM outbox_events WHERE event_type = 'probe'"))}
            assert seen == {org_a}
            conn.execute(text("SAVEPOINT cross_write"))
            with pytest.raises(Exception, match="row-level security"):
                conn.execute(text("INSERT INTO outbox_events (id, organization_id, event_type, aggregate_type, aggregate_id, "
                                  "payload, status, retry_count, created_at) VALUES (:id, :org, 'probe', 'probe', 'p', "
                                  "'{}', 'PENDING', 0, now())"), {"id": str(uuid.uuid4()), "org": org_b})
            conn.execute(text("ROLLBACK TO SAVEPOINT cross_write"))
            # moving an own row to another tenant is refused (WITH CHECK)
            conn.execute(text("SAVEPOINT cross_move"))
            with pytest.raises(Exception, match="row-level security"):
                conn.execute(text("UPDATE outbox_events SET organization_id = :b WHERE event_type = 'probe'"), {"b": org_b})
            conn.execute(text("ROLLBACK TO SAVEPOINT cross_move"))
            # another tenant's rows cannot be updated or deleted (they are invisible: 0 rows)
            assert conn.execute(text("UPDATE outbox_events SET retry_count = retry_count + 1 WHERE organization_id = :b"),
                                {"b": org_b}).rowcount == 0
            assert conn.execute(text("DELETE FROM outbox_events WHERE organization_id = :b"), {"b": org_b}).rowcount == 0
            conn.execute(text("SELECT set_config('app.current_organization_id', :o, true)"), {"o": org_b})
            assert conn.execute(text("SELECT count(*) FROM outbox_events WHERE event_type = 'probe'")).scalar() == 1
            # no tenant context at all: nothing is visible (fails closed)
            conn.execute(text("SELECT set_config('app.current_organization_id', '', true)"))
            assert conn.execute(text("SELECT count(*) FROM outbox_events WHERE event_type = 'probe'")).scalar() == 0
            conn.execute(text("SELECT set_config('app.current_organization_id', '__NONE__', true)"))
            assert conn.execute(text("SELECT count(*) FROM outbox_events WHERE event_type = 'probe'")).scalar() == 0
        finally:
            trans.rollback()
            # roles are cluster-wide: drop it outside the rolled-back transaction
            with engine.connect() as cleanup:
                cleanup.execute(text(f"DROP ROLE IF EXISTS {role}"))
                cleanup.commit()

"""0036 (trial & subscription lifecycle): upgrade, downgrade and re-upgrade.

- No data changes: organizations waiting for approval stay 'pending_approval' (no trial starts at
  migration time) and every existing organization is 'unrestricted' (keeps all modules).
- New tables (subscription_requests, organization_entitlements) exist; on PostgreSQL with row
  level security and the widened status CHECK constraint.
- Downgrade returns trial / trial_expired organizations to 'pending_approval' - never 'active'.
Runs on SQLite and (when TEST_DATABASE_URL is PostgreSQL) on a scratch Postgres database.
"""
import os
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from alembic import command

from backend.tests.test_migration_0033 import _cfg, _insert_org

BEFORE = "3b4c5d6e7f80"
TARGET = "4c5d6e7f8091"


def _aware(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _run(url: str) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        columns = sa.inspect(engine).get_columns("organizations")
        ids = {}
        with engine.begin() as conn:
            for n, status in enumerate(("pending_approval", "active", "suspended", "rejected")):
                ids[status] = _insert_org(conn, columns, status, n)

        command.upgrade(cfg, TARGET)
        insp = sa.inspect(engine)
        assert insp.has_table("subscription_requests") and insp.has_table("organization_entitlements")
        with engine.connect() as conn:
            rows = {r.id: r for r in conn.execute(sa.text(
                "SELECT id, status, module_access, trial_started_at, trial_ends_at, seat_limit FROM organizations"))}
        for status in ("pending_approval", "active", "suspended", "rejected"):
            row = rows[ids[status]]
            assert row.status == status and row.module_access == "unrestricted" and row.seat_limit is None

        if engine.dialect.name == "postgresql":
            with engine.connect() as conn:
                rls = dict(conn.execute(sa.text(
                    "SELECT relname, relrowsecurity AND relforcerowsecurity FROM pg_class "
                    "WHERE relname IN ('subscription_requests', 'organization_entitlements')")).all())
            assert rls == {"subscription_requests": True, "organization_entitlements": True}
            with engine.begin() as conn:  # the new statuses are accepted
                conn.execute(sa.text("UPDATE organizations SET status = 'trial_expired' WHERE id = :id"),
                             {"id": ids["pending_approval"]})

        command.downgrade(cfg, BEFORE)
        insp = sa.inspect(engine)
        assert not insp.has_table("subscription_requests") and not insp.has_table("organization_entitlements")
        assert "module_access" not in {c["name"] for c in insp.get_columns("organizations")}
        with engine.connect() as conn:
            got = dict(conn.execute(sa.text("SELECT id, status FROM organizations")).all())
        assert got[ids["pending_approval"]] == "pending_approval"  # never 'active'
        assert got[ids["active"]] == "active" and got[ids["suspended"]] == "suspended"

        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT status FROM organizations WHERE id = :id"),
                                {"id": ids["pending_approval"]}).scalar() == "pending_approval"
    finally:
        engine.dispose()


def test_0036_upgrade_downgrade_reupgrade_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0036.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0036_upgrade_downgrade_reupgrade_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0036"
    admin = sa.create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{scratch}"'))
        conn.execute(sa.text(f'CREATE DATABASE "{scratch}"'))
    try:
        _run(base_url.set(database=scratch).render_as_string(hide_password=False))
    finally:
        with admin.connect() as conn:
            conn.execute(
                sa.text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n AND pid <> pg_backend_pid()"),
                {"n": scratch},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{scratch}"'))
        admin.dispose()

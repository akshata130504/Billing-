"""0039 (platform checkout): upgrade, downgrade and re-upgrade on a scratch database.

- New tables platform_provider_plans and platform_checkout_attempts; existing rows untouched.
- Constraints: one provider plan per (provider, mode, terms); one OPEN checkout per organization.
- Downgrade refuses while either table holds rows (they refer to objects at Razorpay).
Runs on SQLite and (when TEST_DATABASE_URL is PostgreSQL) on a scratch Postgres database. Never the
application's own database.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from alembic import command

from backend.tests.test_migration_0033 import _cfg, _insert_org

BEFORE = "6e7f80910213"
TARGET = "7f8091021324"
TABLES = ("platform_provider_plans", "platform_checkout_attempts")


def _plan(conn, mode, fingerprint="a" * 64):
    now = datetime.now(timezone.utc)
    conn.execute(sa.text(
        "INSERT INTO platform_provider_plans (id, provider, mode, plan_code, fingerprint, amount_minor, currency, "
        "billing_interval, billing_interval_count, status, reconcile_ref, attempts, created_at, updated_at) VALUES "
        "(:id, 'razorpay', :mode, 'starter', :fp, 79900, 'INR', 'month', 1, 'pending', :ref, 0, :now, :now)"),
        {"id": str(uuid.uuid4()), "mode": mode, "fp": fingerprint, "ref": uuid.uuid4().hex, "now": now})


def _attempt(conn, org_id, status):
    now = datetime.now(timezone.utc)
    conn.execute(sa.text(
        "INSERT INTO platform_checkout_attempts (id, organization_id, plan_code, catalog_version, fingerprint, "
        "amount_minor, currency, billing_interval, billing_interval_count, seat_limit, provider, mode, "
        "provider_subscription_id, status, expires_at, created_at, updated_at) VALUES (:id, :org, 'starter', 1, :fp, "
        "79900, 'INR', 'month', 1, 3, 'razorpay', 'test', :sub, :status, :exp, :now, :now)"),
        {"id": str(uuid.uuid4()), "org": org_id, "fp": "f" * 64, "sub": f"sub_{uuid.uuid4().hex[:14]}",
         "status": status, "exp": now + timedelta(minutes=30), "now": now})


def _run(url: str) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            org_id = _insert_org(conn, sa.inspect(engine).get_columns("organizations"), "active", 1)
        command.upgrade(cfg, TARGET)
        insp = sa.inspect(engine)
        assert all(insp.has_table(t) for t in TABLES)
        assert "uq_platform_checkout_one_open" in {i["name"] for i in insp.get_indexes("platform_checkout_attempts")}

        with engine.begin() as conn:
            _plan(conn, "test")
            _plan(conn, "live")  # same terms, other mode: allowed
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _plan(conn, "test")  # same terms, same mode: refused
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _plan(conn, "sandbox", fingerprint="b" * 64)  # unknown mode
        with engine.begin() as conn:
            for status in ("failed", "expired", "created"):
                _attempt(conn, org_id, status)  # one open + closed ones
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _attempt(conn, org_id, "pending")  # a second open attempt: refused

        with pytest.raises(RuntimeError, match="Refusing to downgrade 0039"):
            command.downgrade(cfg, BEFORE)
        with engine.begin() as conn:  # scratch database only
            for t in TABLES:
                conn.execute(sa.text(f"DELETE FROM {t}"))
        command.downgrade(cfg, BEFORE)
        insp = sa.inspect(engine)
        assert not any(insp.has_table(t) for t in TABLES)
        assert insp.has_table("platform_subscriptions") and insp.has_table("organizations")

        command.upgrade(cfg, "head")
        assert all(sa.inspect(engine).has_table(t) for t in TABLES)
    finally:
        engine.dispose()


def test_0039_upgrade_downgrade_reupgrade_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0039.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0039_upgrade_downgrade_reupgrade_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0039"
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

"""0040 (platform payment verification): upgrade, downgrade and re-upgrade on a scratch database.

- Existing checkout attempts and trial rows keep their values; 'authorized' becomes a valid OPEN status.
- platform_subscriptions gains the Razorpay link (unique); platform_webhook_events has a unique event_id.
- Downgrade refuses while anything depends on the new columns or the ledger has rows.
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
from backend.tests.test_migration_0039 import _attempt

BEFORE = "7f8091021324"
TARGET = "80910213243a"


def _event(conn, event_id):
    conn.execute(sa.text(
        "INSERT INTO platform_webhook_events (id, provider, event_id, event_type, status, outcome, received_at) "
        "VALUES (:id, 'razorpay', :eid, 'subscription.charged', 'processed', 'renewed', :now)"),
        {"id": str(uuid.uuid4()), "eid": event_id, "now": datetime.now(timezone.utc)})


def _run(url: str) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            cols = sa.inspect(engine).get_columns("organizations")
            org_a, org_b = _insert_org(conn, cols, "active", 1), _insert_org(conn, cols, "active", 2)
            _attempt(conn, org_a, "created")  # an open attempt from before 0040
        command.upgrade(cfg, TARGET)
        insp = sa.inspect(engine)
        assert {"provider_payment_id", "authorized_at", "completed_at"} <= {c["name"] for c in insp.get_columns("platform_checkout_attempts")}
        assert {"provider_subscription_id", "provider_mode", "provider_paid_count"} <= {c["name"] for c in insp.get_columns("platform_subscriptions")}
        assert insp.has_table("platform_webhook_events")
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT status FROM platform_checkout_attempts")).scalars().all() == ["created"]

        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _attempt(conn, org_a, "authorized")  # 'authorized' is open: a second open attempt is refused
        with engine.begin() as conn:
            _attempt(conn, org_b, "authorized")  # and valid on its own
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _attempt(conn, org_b, "bogus")
        with engine.begin() as conn:
            _event(conn, "evt_1")
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _event(conn, "evt_1")

        with pytest.raises(RuntimeError, match="Refusing to downgrade 0040"):
            command.downgrade(cfg, BEFORE)
        with engine.begin() as conn:  # scratch database only
            conn.execute(sa.text("DELETE FROM platform_webhook_events"))
            conn.execute(sa.text("DELETE FROM platform_checkout_attempts WHERE status = 'authorized'"))
        command.downgrade(cfg, BEFORE)
        insp = sa.inspect(engine)
        assert not insp.has_table("platform_webhook_events")
        assert "authorized_at" not in {c["name"] for c in insp.get_columns("platform_checkout_attempts")}
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _attempt(conn, org_b, "authorized")  # no longer a valid status
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _attempt(conn, org_a, "pending")  # the open-attempt index survived the downgrade

        command.upgrade(cfg, "head")
        assert sa.inspect(engine).has_table("platform_webhook_events")
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT status FROM platform_checkout_attempts")).scalars().all() == ["created"]
    finally:
        engine.dispose()


def test_0040_upgrade_downgrade_reupgrade_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0040.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0040_upgrade_downgrade_reupgrade_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0040"
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

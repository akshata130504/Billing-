"""0038 (platform subscription lifecycle): upgrade, downgrade and re-upgrade on a scratch database.

- An existing trial row is unchanged by the upgrade and satisfies every new constraint.
- After the upgrade a paid row can be stored, and the constraints refuse incomplete paid rows.
- Downgrade refuses to run while a paid row exists (it would lose its plan and period).
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

BEFORE = "5d6e7f809102"
TARGET = "6e7f80910213"
NEW_COLUMNS = {"plan_code", "billing_interval", "billing_interval_count", "current_period_start",
               "current_period_end", "cancel_at_period_end", "cancelled_at", "grace_period_end"}


def _insert_sub(conn, org_id, **fields):
    now = datetime.now(timezone.utc)
    row = {"id": str(uuid.uuid4()), "organization_id": org_id, "state": "trialing", "trial_started_at": now,
           "trial_ends_at": now + timedelta(minutes=15), "reminders_sent": [], "created_at": now, "updated_at": now}
    row.update(fields)
    cols = ", ".join(row)
    stmt = sa.text(f"INSERT INTO platform_subscriptions ({cols}) VALUES ({', '.join(':' + k for k in row)})")
    conn.execute(stmt.bindparams(sa.bindparam("reminders_sent", type_=sa.JSON)), row)
    return row["id"]


def _run(url: str) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        org_columns = sa.inspect(engine).get_columns("organizations")
        with engine.begin() as conn:
            org_id = _insert_org(conn, org_columns, "active", 1)
            paid_org = _insert_org(conn, org_columns, "active", 2)
        # A pre-0038 row: only the trial columns.
        sub_columns = {c["name"] for c in sa.inspect(engine).get_columns("platform_subscriptions")}
        with engine.begin() as conn:
            trial_fields = {} if "cancel_at_period_end" not in sub_columns else {"cancel_at_period_end": False}
            trial_id = _insert_sub(conn, org_id, **trial_fields)

        command.upgrade(cfg, TARGET)
        insp = sa.inspect(engine)
        assert NEW_COLUMNS <= {c["name"] for c in insp.get_columns("platform_subscriptions")}
        with engine.connect() as conn:
            row = conn.execute(sa.text("SELECT state, trial_ends_at, plan_code, cancel_at_period_end "
                                       "FROM platform_subscriptions WHERE id = :id"), {"id": trial_id}).one()
        assert row.state == "trialing" and row.trial_ends_at is not None
        assert row.plan_code is None and not row.cancel_at_period_end

        now = datetime.now(timezone.utc)
        with engine.begin() as conn:  # a complete paid row without a trial is accepted
            _insert_sub(conn, paid_org, state="active", trial_started_at=None, trial_ends_at=None, plan_code="starter",
                        billing_interval="month", billing_interval_count=1, current_period_start=now,
                        current_period_end=now + timedelta(days=30), cancel_at_period_end=False)
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:  # incomplete paid row refused
            extra = _insert_org(conn, org_columns, "active", 3)
            _insert_sub(conn, extra, state="active", plan_code=None, cancel_at_period_end=False)
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:  # a trial row needs its window
            extra = _insert_org(conn, org_columns, "active", 4)
            _insert_sub(conn, extra, trial_ends_at=None, cancel_at_period_end=False)

        with pytest.raises(RuntimeError, match="Refusing to downgrade 0038"):
            command.downgrade(cfg, BEFORE)
        with engine.connect() as conn:  # the refused downgrade changed nothing
            assert conn.execute(sa.text("SELECT COUNT(*) FROM platform_subscriptions")).scalar() == 2

        with engine.begin() as conn:  # scratch database only: remove the paid row to test the downgrade
            conn.execute(sa.text("DELETE FROM platform_subscriptions WHERE organization_id = :id"), {"id": paid_org})
        command.downgrade(cfg, BEFORE)
        cols = {c["name"]: c for c in sa.inspect(engine).get_columns("platform_subscriptions")}
        assert not NEW_COLUMNS & set(cols)
        assert cols["trial_ends_at"]["nullable"] is False
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT state FROM platform_subscriptions WHERE id = :id"),
                                {"id": trial_id}).scalar() == "trialing"

        command.upgrade(cfg, "head")
        assert NEW_COLUMNS <= {c["name"] for c in sa.inspect(engine).get_columns("platform_subscriptions")}
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT state FROM platform_subscriptions WHERE id = :id"),
                                {"id": trial_id}).scalar() == "trialing"
    finally:
        engine.dispose()


def test_0038_upgrade_downgrade_reupgrade_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0038.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0038_upgrade_downgrade_reupgrade_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0038"
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

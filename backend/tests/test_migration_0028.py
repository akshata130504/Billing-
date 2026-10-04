"""0028 (platform hardening): step-up columns and the append-only audit trigger. Upgrade from 0027
with existing data, downgrade and re-upgrade, on SQLite and (when TEST_DATABASE_URL is
PostgreSQL) Postgres - where the trigger and the privilege revocation are also verified."""
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BEFORE = "5e6f7a8b9c0d"
TARGET = "6f7a8b9c0d1e"
STEP_UP_COLUMNS = {"step_up_at", "step_up_expires_at"}
TRIGGERS = {"platform_audit_logs_no_update_delete", "platform_audit_logs_no_truncate"}


def _cfg(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    return cfg


def _session_columns(engine):
    return {c["name"] for c in sa.inspect(engine).get_columns("platform_sessions")}


def _triggers(engine):
    with engine.connect() as conn:
        return set(conn.execute(sa.text(
            "SELECT tgname FROM pg_trigger WHERE tgrelid = 'platform_audit_logs'::regclass AND NOT tgisinternal"
        )).scalars())


def _insert_audit(conn, entry_id):
    conn.execute(sa.text(
        "INSERT INTO platform_audit_logs (id, occurred_at, action, result) "
        "VALUES (:i, CURRENT_TIMESTAMP, 'PLATFORM_TEST_EVENT', 'success')"
    ), {"i": entry_id})


def _run(url: str, probe_role: str | None = None) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BEFORE)  # the true 0027 shape (early revisions build from current models)
    engine = sa.create_engine(url)
    pg = engine.dialect.name == "postgresql"
    try:
        entry_id = str(uuid.uuid4())
        with engine.begin() as conn:
            _insert_audit(conn, entry_id)
            if pg and probe_role:
                # What default privileges / an old least_privilege.sql run would have granted.
                conn.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON platform_audit_logs TO "{probe_role}"'))
        assert not (STEP_UP_COLUMNS & _session_columns(engine))

        command.upgrade(cfg, TARGET)
        assert STEP_UP_COLUMNS <= _session_columns(engine)
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM platform_audit_logs WHERE id = :i"), {"i": entry_id}).scalar() == 1

        if pg:
            assert TRIGGERS <= _triggers(engine)
            with pytest.raises(sa.exc.DBAPIError):
                with engine.begin() as conn:
                    conn.execute(sa.text("DELETE FROM platform_audit_logs WHERE id = :i"), {"i": entry_id})
            with engine.begin() as conn:  # inserting still works
                _insert_audit(conn, str(uuid.uuid4()))
            if probe_role:
                with engine.connect() as conn:
                    privs = {p: conn.execute(sa.text("SELECT has_table_privilege(:r, 'platform_audit_logs', :p)"),
                                             {"r": probe_role, "p": p}).scalar()
                             for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")}
                    # other tables are untouched by 0028
                    other = conn.execute(sa.text("SELECT has_table_privilege(:r, 'platform_sessions', 'UPDATE')"),
                                         {"r": probe_role}).scalar()
                assert privs == {"SELECT": True, "INSERT": True, "UPDATE": False, "DELETE": False, "TRUNCATE": False}
                assert other is False  # never granted in this test: 0028 granted nothing either

        command.downgrade(cfg, BEFORE)
        assert not (STEP_UP_COLUMNS & _session_columns(engine))
        if pg:
            assert not (TRIGGERS & _triggers(engine))
        command.upgrade(cfg, "head")
        assert STEP_UP_COLUMNS <= _session_columns(engine)
        if pg:
            assert TRIGGERS <= _triggers(engine)
    finally:
        engine.dispose()


def test_0028_upgrade_downgrade_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0028.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0028_upgrade_downgrade_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0028"
    admin = sa.create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{scratch}"'))
        conn.execute(sa.text(f'CREATE DATABASE "{scratch}"'))
        can_create_roles = conn.execute(sa.text(
            "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")).scalar()
    probe = f"rb_m0028_probe_{uuid.uuid4().hex[:8]}" if can_create_roles else None
    if probe:
        with admin.connect() as conn:
            conn.execute(sa.text(f'CREATE ROLE "{probe}" NOLOGIN'))
    try:
        _run(base_url.set(database=scratch).render_as_string(hide_password=False), probe)
    finally:
        with admin.connect() as conn:
            conn.execute(
                sa.text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n AND pid <> pg_backend_pid()"),
                {"n": scratch},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{scratch}"'))
            if probe:
                conn.execute(sa.text(f'DROP ROLE IF EXISTS "{probe}"'))
        admin.dispose()

"""0031 (tenant access grants): creates one new table only; downgrade and re-upgrade cleanly on
SQLite and (when TEST_DATABASE_URL is PostgreSQL) Postgres. No tenant table is touched."""
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BEFORE = "8b9c0d1e2f3a"
TARGET = "9c0d1e2f3a4b"
TABLES = {"tenant_access_grants"}


def _cfg(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    return cfg


def _run(url: str) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        before = set(sa.inspect(engine).get_table_names())
        assert not (TABLES & before)
        command.upgrade(cfg, TARGET)
        after = set(sa.inspect(engine).get_table_names())
        assert after - before == TABLES  # only the grants table is added
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM tenant_access_grants")).scalar() == 0  # no data written
        command.downgrade(cfg, BEFORE)
        assert set(sa.inspect(engine).get_table_names()) == before
        command.upgrade(cfg, "head")
        assert TABLES <= set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_0031_upgrade_downgrade_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0031.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0031_upgrade_downgrade_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0031"
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

"""0035 (app UI visual editor): creates two new platform tables only (plus the one-draft-per-page
partial unique index and CHECK constraints); downgrade and re-upgrade cleanly on SQLite and (when
TEST_DATABASE_URL is PostgreSQL) Postgres. No tenant table is touched and no data is written."""
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BEFORE = "2f3a4b5c6d7e"
TARGET = "3b4c5d6e7f80"
TABLES = {"app_ui_pages", "app_ui_versions"}


def _cfg(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    return cfg


def _insert(engine, state, version, key="overview"):
    content = "CAST(:content AS JSON)" if engine.dialect.name == "postgresql" else ":content"
    insert = sa.text(
        "INSERT INTO app_ui_versions (id, page_key, state, version, revision, content, content_sha256, created_at,"
        f" updated_at) VALUES (:id, :key, :state, :version, 1, {content}, :sha, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    with engine.begin() as conn:
        conn.execute(insert, {"id": str(uuid.uuid4()), "key": key, "state": state, "version": version,
                              "content": '{"schema_version": 1}', "sha": "0" * 64})


def _check_constraints(engine) -> None:
    _insert(engine, "draft", None)  # one draft per page is fine
    _insert(engine, "published", 1)
    _insert(engine, "draft", None, key="theme")  # a draft on another page is fine
    for state, version in (("published", None), ("draft", 3), ("archived", None)):
        with pytest.raises(sa.exc.IntegrityError):
            _insert(engine, state, version)
    with pytest.raises(sa.exc.IntegrityError):
        _insert(engine, "draft", None)  # second draft for the same page: partial unique index
    with pytest.raises(sa.exc.IntegrityError):
        _insert(engine, "published", 1)  # duplicate version number
    _insert(engine, "published", 2)  # many published rows per page are fine
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM app_ui_versions"))


def _run(url: str) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        before = set(sa.inspect(engine).get_table_names())
        assert not (TABLES & before)
        command.upgrade(cfg, TARGET)
        inspector = sa.inspect(engine)
        after = set(inspector.get_table_names())
        assert after - before == TABLES  # only the app UI tables are added
        indexes = {i["name"]: i for i in inspector.get_indexes("app_ui_versions")}
        assert indexes["uq_app_ui_one_draft_per_page"]["unique"]
        assert indexes["uq_app_ui_one_draft_per_page"]["column_names"] == ["page_key"]
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM app_ui_pages")).scalar() == 0  # no data written
            assert conn.execute(sa.text("SELECT count(*) FROM app_ui_versions")).scalar() == 0
        _check_constraints(engine)
        command.downgrade(cfg, BEFORE)
        assert set(sa.inspect(engine).get_table_names()) == before
        command.upgrade(cfg, "head")
        assert TABLES <= set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_0035_upgrade_downgrade_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0035.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0035_upgrade_downgrade_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0035"
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

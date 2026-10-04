"""0033 (organization approval lifecycle): downgrade must first move rows in the 0033-only
statuses ('pending_approval', 'rejected') to 'suspended' (never 'active'), so the old
CHECK constraint can be re-created on PostgreSQL and no unapproved tenant silently gains
access. Runs on SQLite and (when TEST_DATABASE_URL is PostgreSQL) Postgres."""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BEFORE = "0d1e2f3a4b5c"
TARGET = "1e2f3a4b5c6d"


def _cfg(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    return cfg


def _value_for(column: dict, n: int):
    name = column["name"]
    type_ = column["type"]
    if name == "id":
        return str(uuid.uuid4())
    if name == "slug":
        return f"org-{n}-{uuid.uuid4().hex[:6]}"
    if isinstance(type_, (sa.DateTime, sa.Date)):
        return datetime.now(timezone.utc)
    if isinstance(type_, (sa.Integer, sa.Numeric)):
        return 1
    if isinstance(type_, sa.Boolean):
        return False
    length = getattr(type_, "length", None) or 20
    return ("X" * length)[: min(length, 3)] if length < 10 else f"v{n}"


def _insert_org(conn, columns, status: str, n: int) -> str:
    row = {c["name"]: _value_for(c, n) for c in columns if not c["nullable"] and c.get("default") is None}
    row["status"] = status
    cols = ", ".join(row)
    params = ", ".join(f":{k}" for k in row)
    conn.execute(sa.text(f"INSERT INTO organizations ({cols}) VALUES ({params})"), row)
    return row["id"]


def _run(url: str) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, TARGET)
    engine = sa.create_engine(url)
    try:
        columns = sa.inspect(engine).get_columns("organizations")
        ids = {}
        with engine.begin() as conn:
            for n, status in enumerate(("pending_approval", "rejected", "active", "suspended", "pending_deletion")):
                ids[status] = _insert_org(conn, columns, status, n)

        command.downgrade(cfg, BEFORE)

        with engine.connect() as conn:
            got = dict(conn.execute(sa.text("SELECT id, status FROM organizations")).all())
        assert got[ids["pending_approval"]] == "suspended"
        assert got[ids["rejected"]] == "suspended"
        # rows already valid under the old lifecycle are untouched
        assert got[ids["active"]] == "active"
        assert got[ids["suspended"]] == "suspended"
        assert got[ids["pending_deletion"]] == "pending_deletion"
        assert "active" not in {got[ids["pending_approval"]], got[ids["rejected"]]}

        if engine.dialect.name == "postgresql":
            # the old constraint is back and enforced
            with pytest.raises(sa.exc.IntegrityError):
                with engine.begin() as conn:
                    conn.execute(
                        sa.text("UPDATE organizations SET status = 'pending_approval' WHERE id = :id"),
                        {"id": ids["active"]},
                    )

        command.upgrade(cfg, "head")
    finally:
        engine.dispose()


def test_0033_downgrade_demotes_new_statuses_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0033.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0033_downgrade_demotes_new_statuses_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0033"
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

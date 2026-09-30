"""0026 (organization lifecycle foundation): upgrade over existing organizations as production
has them, downgrade and re-upgrade, on SQLite and (when TEST_DATABASE_URL is PostgreSQL) Postgres.

Early revisions build tables from the current models, so a fresh database already has the new
columns. Upgrading to head and downgrading one revision reproduces the real production shape
(0025: organizations without status / jobs_paused) before existing rows are inserted.
"""
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BEFORE = "3c4d5e6f7a8b"
TARGET = "4d5e6f7a8b9c"


def _cfg(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    return cfg


def _columns(engine):
    return {c["name"] for c in sa.inspect(engine).get_columns("organizations")}


def _insert_legacy_org(conn, n: int) -> str:
    """An organization row exactly as a 0025 database holds it (no lifecycle columns)."""
    org_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO organizations (id, name, slug, country, default_currency, timezone,"
            " invoice_prefix, invoice_next_number, quote_prefix, quote_next_number,"
            " payment_prefix, payment_next_number, subscription_prefix, subscription_next_number,"
            " customer_prefix, customer_next_number, default_payment_terms_days,"
            " default_tax_rate_pct, discount_approval_threshold_pct, created_at, updated_at)"
            " VALUES (:id, :name, :slug, 'IN', 'INR', 'Asia/Kolkata', 'INV-', 1, 'QT-', 1,"
            " 'PAY-', 1, 'SUB-', 1, 'CUS-', 1, 30, 18, 20, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": org_id, "name": f"Legacy {n}", "slug": f"legacy-{n}-{org_id[:8]}"},
    )
    return org_id


def _lifecycle(conn, org_id):
    row = conn.execute(
        sa.text("SELECT status, jobs_paused FROM organizations WHERE id = :i"), {"i": org_id}
    ).one()
    return row[0], bool(row[1])


def _run(url: str) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        assert not ({"status", "jobs_paused"} & _columns(engine))
        with engine.begin() as conn:
            orgs = [_insert_legacy_org(conn, n) for n in range(3)]

        command.upgrade(cfg, TARGET)
        assert {"status", "jobs_paused"} <= _columns(engine)
        with engine.connect() as conn:
            for org_id in orgs:
                assert _lifecycle(conn, org_id) == ("active", False)
        # A row inserted without naming the columns (as older code paths would) gets the defaults.
        with engine.begin() as conn:
            later = _insert_legacy_org(conn, 99)
        with engine.connect() as conn:
            assert _lifecycle(conn, later) == ("active", False)

        if engine.dialect.name == "postgresql":
            # The CHECK constraint rejects anything outside the four lifecycle values.
            with pytest.raises(sa.exc.IntegrityError):
                with engine.begin() as conn:
                    conn.execute(sa.text("UPDATE organizations SET status = 'bogus' WHERE id = :i"), {"i": later})

        command.downgrade(cfg, BEFORE)
        assert not ({"status", "jobs_paused"} & _columns(engine))
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM organizations")).scalar() == 4

        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            for org_id in orgs + [later]:
                assert _lifecycle(conn, org_id) == ("active", False)
    finally:
        engine.dispose()


def test_0026_upgrade_existing_orgs_become_active_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0026.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0026_upgrade_existing_orgs_become_active_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0026"
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

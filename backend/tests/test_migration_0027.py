"""0027 (platform identity): upgrade from the Phase 1 (0026) schema with existing data, downgrade
and re-upgrade, on SQLite and (when TEST_DATABASE_URL is PostgreSQL) Postgres."""
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BEFORE = "4d5e6f7a8b9c"
TARGET = "5e6f7a8b9c0d"
TABLES = {"platform_staff", "platform_sessions", "platform_login_challenges", "platform_audit_logs"}


def _cfg(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    return cfg


def _tables(engine):
    return set(sa.inspect(engine).get_table_names())


def _run(url: str) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BEFORE)  # the true Phase 1 shape (early revisions build from models)
    engine = sa.create_engine(url)
    try:
        assert not (TABLES & _tables(engine))
        org_id = str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO organizations (id, name, slug, country, default_currency, timezone,"
                    " invoice_prefix, invoice_next_number, quote_prefix, quote_next_number,"
                    " payment_prefix, payment_next_number, subscription_prefix, subscription_next_number,"
                    " customer_prefix, customer_next_number, default_payment_terms_days,"
                    " default_tax_rate_pct, discount_approval_threshold_pct, created_at, updated_at)"
                    " VALUES (:id, 'Tenant', :slug, 'IN', 'INR', 'Asia/Kolkata', 'INV-', 1, 'QT-', 1,"
                    " 'PAY-', 1, 'SUB-', 1, 'CUS-', 1, 30, 18, 20, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": org_id, "slug": f"t-{org_id[:8]}"},
            )

        command.upgrade(cfg, TARGET)
        assert TABLES <= _tables(engine)
        cols = {c["name"] for c in sa.inspect(engine).get_columns("organizations")}
        assert {"status", "jobs_paused"} <= cols  # 0026 untouched
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM organizations WHERE id = :i"), {"i": org_id}).scalar() == 1
            assert conn.execute(sa.text("SELECT count(*) FROM platform_staff")).scalar() == 0  # nothing seeded

        if engine.dialect.name == "postgresql":
            with pytest.raises(sa.exc.IntegrityError):
                with engine.begin() as conn:
                    conn.execute(sa.text(
                        "INSERT INTO platform_staff (id, email, full_name, hashed_password, role, is_active,"
                        " created_at, updated_at) VALUES (:i, 'x@example.test', 'X', 'h', 'superuser', true,"
                        " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ), {"i": str(uuid.uuid4())})

        command.downgrade(cfg, BEFORE)
        assert not (TABLES & _tables(engine))
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM organizations WHERE id = :i"), {"i": org_id}).scalar() == 1

        command.upgrade(cfg, "head")
        assert TABLES <= _tables(engine)
    finally:
        engine.dispose()


def test_0027_upgrade_downgrade_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0027.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0027_upgrade_downgrade_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0027"
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

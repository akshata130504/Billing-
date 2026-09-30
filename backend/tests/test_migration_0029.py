"""0029 (platform organization lifecycle): upgrade from 0028 with existing data, downgrade and
re-upgrade, on SQLite and (when TEST_DATABASE_URL is PostgreSQL) Postgres - where the append-only
audit triggers must survive the added audit columns."""
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BEFORE = "6f7a8b9c0d1e"
TARGET = "7a8b9c0d1e2f"
ORG_COLUMNS = {"status_changed_at", "status_changed_by_staff_id", "status_reason", "deletion_scheduled_for"}
AUDIT_COLUMNS = {"staff_role_snapshot", "target_type", "target_id", "organization_id",
                 "organization_name_snapshot", "reason", "ticket_ref"}
TRIGGERS = {"platform_audit_logs_no_update_delete", "platform_audit_logs_no_truncate"}


def _cfg(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    return cfg


def _cols(engine, table):
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def _run(url: str) -> None:
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BEFORE)  # the true 0028 shape (early revisions build from current models)
    engine = sa.create_engine(url)
    pg = engine.dialect.name == "postgresql"
    try:
        assert not (ORG_COLUMNS & _cols(engine, "organizations"))
        assert not (AUDIT_COLUMNS & _cols(engine, "platform_audit_logs"))
        org_id, entry_id = str(uuid.uuid4()), str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO organizations (id, name, slug, country, default_currency, timezone,"
                " invoice_prefix, invoice_next_number, quote_prefix, quote_next_number,"
                " payment_prefix, payment_next_number, subscription_prefix, subscription_next_number,"
                " customer_prefix, customer_next_number, default_payment_terms_days,"
                " default_tax_rate_pct, discount_approval_threshold_pct, status, jobs_paused, created_at, updated_at)"
                " VALUES (:id, 'Tenant', :slug, 'IN', 'INR', 'Asia/Kolkata', 'INV-', 1, 'QT-', 1,"
                " 'PAY-', 1, 'SUB-', 1, 'CUS-', 1, 30, 18, 20, 'suspended', false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ), {"id": org_id, "slug": f"t-{org_id[:8]}"})
            conn.execute(sa.text(
                "INSERT INTO platform_audit_logs (id, occurred_at, action, result)"
                " VALUES (:i, CURRENT_TIMESTAMP, 'PLATFORM_TEST_EVENT', 'success')"
            ), {"i": entry_id})

        command.upgrade(cfg, TARGET)
        assert ORG_COLUMNS <= _cols(engine, "organizations")
        assert AUDIT_COLUMNS <= _cols(engine, "platform_audit_logs")
        with engine.connect() as conn:
            row = conn.execute(sa.text("SELECT status, jobs_paused, status_reason FROM organizations WHERE id = :i"),
                               {"i": org_id}).one()
            assert (row[0], bool(row[1]), row[2]) == ("suspended", False, None)  # data unchanged
            assert conn.execute(sa.text("SELECT count(*) FROM platform_audit_logs WHERE id = :i"),
                                {"i": entry_id}).scalar() == 1
        assert "ix_platform_audit_logs_organization_id" in {ix["name"] for ix in sa.inspect(engine).get_indexes("platform_audit_logs")}
        if pg:
            with engine.connect() as conn:
                names = set(conn.execute(sa.text(
                    "SELECT tgname FROM pg_trigger WHERE tgrelid = 'platform_audit_logs'::regclass AND NOT tgisinternal"
                )).scalars())
            assert TRIGGERS <= names
            with pytest.raises(sa.exc.DBAPIError):
                with engine.begin() as conn:
                    conn.execute(sa.text("UPDATE platform_audit_logs SET reason = 'x' WHERE id = :i"), {"i": entry_id})

        command.downgrade(cfg, BEFORE)
        assert not (ORG_COLUMNS & _cols(engine, "organizations"))
        assert not (AUDIT_COLUMNS & _cols(engine, "platform_audit_logs"))
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM platform_audit_logs WHERE id = :i"),
                                {"i": entry_id}).scalar() == 1
        command.upgrade(cfg, "head")
        assert ORG_COLUMNS <= _cols(engine, "organizations")
    finally:
        engine.dispose()


def test_0029_upgrade_downgrade_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0029.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0029_upgrade_downgrade_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0029"
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

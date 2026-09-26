"""0024 (offering-linked plans, quote -> subscription link): upgrade over existing data,
downgrade and re-upgrade, on SQLite and (when TEST_DATABASE_URL is PostgreSQL) Postgres."""
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BEFORE = "1a2b3c4d5e6f"
TARGET = "2b3c4d5e6f7a"
NEW_COLUMNS = {
    "plans": {"offering_id", "offering_terms_key"},
    "products": {"offering_id"},
    "quotes": {"converted_subscription_id"},
}


def _cfg(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    return cfg


def _dummy(column: sa.Column, token: str):
    t = column.type
    enums = getattr(t, "enums", None)
    if enums:
        return enums[0]
    if isinstance(t, sa.Boolean):
        return False
    if isinstance(t, sa.Integer):
        return 1
    if isinstance(t, sa.Numeric):
        return 0
    if isinstance(t, sa.DateTime):
        return datetime.now(timezone.utc)
    if isinstance(t, sa.Date):
        return date.today()
    if isinstance(t, sa.JSON):
        return {}
    if isinstance(t, (sa.String, sa.Text)):
        length = getattr(t, "length", None) or 32
        return f"{column.name[:6]}{token}"[:length]
    return None


def _insert(conn, meta: sa.MetaData, table_name: str, **values):
    table = meta.tables[table_name]
    token = uuid.uuid4().hex[:8]
    row = dict(values)
    row.setdefault("id", str(uuid.uuid4()))
    for column in table.columns:
        if column.name in row or column.nullable or column.server_default is not None:
            continue
        row[column.name] = _dummy(column, token)
    conn.execute(table.insert().values(**row))
    return row["id"]


def _columns(engine, table):
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def _run(url: str):
    cfg = _cfg(url)
    command.upgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        meta = sa.MetaData()
        meta.reflect(bind=engine, only=["organizations", "products", "plans", "customers", "quotes", "subscriptions"])
        with engine.begin() as conn:
            org = _insert(conn, meta, "organizations")
            product = _insert(conn, meta, "products", organization_id=org)
            plan = _insert(conn, meta, "plans", organization_id=org, product_id=product)
            customer = _insert(conn, meta, "customers", organization_id=org)
            quote = _insert(conn, meta, "quotes", organization_id=org, customer_id=customer)
            sub = _insert(conn, meta, "subscriptions", organization_id=org, customer_id=customer, plan_id=plan)

        command.upgrade(cfg, TARGET)
        for table, cols in NEW_COLUMNS.items():
            assert cols <= _columns(engine, table), table
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT offering_id, offering_terms_key FROM plans WHERE id = :i"), {"i": plan}).one() == (None, None)
            assert conn.execute(sa.text("SELECT offering_id FROM products WHERE id = :i"), {"i": product}).scalar() is None
            assert conn.execute(sa.text("SELECT converted_subscription_id FROM quotes WHERE id = :i"), {"i": quote}).scalar() is None
            assert conn.execute(sa.text("SELECT plan_id FROM subscriptions WHERE id = :i"), {"i": sub}).scalar() == plan
        # Legacy plans (offering_id NULL) never collide on the new unique constraints.
        with engine.begin() as conn:
            _insert(conn, meta, "plans", organization_id=org, product_id=product)

        command.downgrade(cfg, BEFORE)
        for table, cols in NEW_COLUMNS.items():
            assert not (cols & _columns(engine, table)), table
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM plans WHERE organization_id = :o"), {"o": org}).scalar() == 2
            assert conn.execute(sa.text("SELECT count(*) FROM quotes WHERE id = :i"), {"i": quote}).scalar() == 1

        command.upgrade(cfg, "head")
        for table, cols in NEW_COLUMNS.items():
            assert cols <= _columns(engine, table), table
    finally:
        engine.dispose()


def test_0024_upgrade_with_existing_data_downgrade_sqlite(tmp_path):
    _run(f"sqlite:///{(tmp_path / 'm0024.sqlite3').as_posix()}")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)
def test_0024_upgrade_with_existing_data_downgrade_postgres():
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    scratch = f"{base_url.database}_m0024"
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

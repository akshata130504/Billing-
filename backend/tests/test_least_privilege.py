"""Least-privilege verification against a REAL migrated PostgreSQL database.

Skipped unless LEAST_PRIVILEGE_DATABASE_URL is set. That URL must connect as the *runtime*
role to a database that was migrated by a separate *owner* role (`alembic upgrade head`)
and then prepared with deploy/sql/least_privilege.sql. Optionally set
LEAST_PRIVILEGE_OWNER_DATABASE_URL (owner role, same database) to also verify that tables
created later by the owner are granted to the runtime role through default privileges.

Nothing here runs DDL as the runtime role except the statements that are expected to fail.
Keep TEST_DATABASE_URL pointed at a *different* scratch database: conftest.py drops and
recreates the schema of TEST_DATABASE_URL.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

LP_URL = os.environ.get("LEAST_PRIVILEGE_DATABASE_URL")
OWNER_URL = os.environ.get("LEAST_PRIVILEGE_OWNER_DATABASE_URL")

pytestmark = pytest.mark.skipif(not LP_URL, reason="LEAST_PRIVILEGE_DATABASE_URL not set")

REPO_ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "Str0ngPassw0rd!"
# Tables the runtime role may only INSERT into and SELECT from (migration 0028, least_privilege.sql).
APPEND_ONLY_TABLES = ("platform_audit_logs",)


@pytest.fixture(scope="module")
def lp_engine():
    from sqlalchemy import create_engine

    engine = create_engine(LP_URL, connect_args={"options": "-c timezone=UTC"}, pool_pre_ping=True)
    yield engine
    engine.dispose()


def _sqlstate(exc) -> str | None:
    orig = getattr(exc, "orig", exc)
    return getattr(orig, "sqlstate", None)


def test_runtime_role_has_no_elevated_attributes(lp_engine):
    from sqlalchemy import text

    with lp_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolreplication, r.rolbypassrls, "
                "has_schema_privilege(current_user, 'public', 'CREATE'), "
                "has_database_privilege(current_user, current_database(), 'CREATE') "
                "FROM pg_roles r WHERE r.rolname = current_user"
            )
        ).one()
        assert tuple(row) == (False, False, False, False, False, False, False)
        owned = conn.execute(
            text(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)"
            )
        ).scalar()
        assert owned == 0


def test_runtime_role_can_read_alembic_version_at_head(lp_engine):
    from sqlalchemy import text

    from backend.app.core.migrations import script_heads

    with lp_engine.connect() as conn:
        versions = {r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version"))}
    assert versions == set(script_heads())


def test_runtime_role_has_dml_on_every_table(lp_engine):
    from sqlalchemy import text

    with lp_engine.connect() as conn:
        missing = conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r','p') AND c.relname <> ALL(:append_only) AND NOT ("
                " has_table_privilege(current_user, c.oid, 'SELECT') AND has_table_privilege(current_user, c.oid, 'INSERT')"
                " AND has_table_privilege(current_user, c.oid, 'UPDATE') AND has_table_privilege(current_user, c.oid, 'DELETE'))"
            ),
            {"append_only": list(APPEND_ONLY_TABLES)},
        ).scalars().all()
        seq_missing = conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'S' AND NOT has_sequence_privilege(current_user, c.oid, 'USAGE')"
            )
        ).scalars().all()
    assert missing == []
    assert seq_missing == []


def test_runtime_role_has_only_select_insert_on_platform_audit_logs(lp_engine):
    from sqlalchemy import text

    with lp_engine.connect() as conn:
        privs = {
            p: conn.execute(text("SELECT has_table_privilege(current_user, 'platform_audit_logs', :p)"), {"p": p}).scalar()
            for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER", "REFERENCES")
        }
    assert privs == {"SELECT": True, "INSERT": True, "UPDATE": False, "DELETE": False,
                     "TRUNCATE": False, "TRIGGER": False, "REFERENCES": False}


def test_runtime_role_cannot_rewrite_platform_audit_logs(lp_engine):
    """INSERT and SELECT work; UPDATE, DELETE and TRUNCATE fail (privilege and trigger); the
    runtime role cannot disable or drop the trigger. The platform audit service still writes."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.orm import Session

    from backend.app.services import platform_audit

    with Session(lp_engine) as db:
        entry = platform_audit.record(db, action="PLATFORM_LP_CHECK", result=platform_audit.SUCCESS,
                                      email="lp@rooman.test", details={"note": "least privilege"})
        db.commit()
        entry_id = entry.id
    for statement in (
        "UPDATE platform_audit_logs SET action = 'TAMPERED' WHERE id = :i",
        "DELETE FROM platform_audit_logs WHERE id = :i",
        "TRUNCATE platform_audit_logs",
        "ALTER TABLE platform_audit_logs DISABLE TRIGGER USER",
        "DROP TRIGGER platform_audit_logs_no_update_delete ON platform_audit_logs",
        "DROP FUNCTION platform_audit_logs_append_only() CASCADE",
    ):
        with lp_engine.connect() as conn:
            with pytest.raises(DBAPIError) as exc_info:
                conn.execute(text(statement), {"i": entry_id} if ":i" in statement else {})
            conn.rollback()
        assert _sqlstate(exc_info.value) == "42501", (statement, str(exc_info.value.orig))
    with lp_engine.connect() as conn:
        assert conn.execute(text("SELECT action FROM platform_audit_logs WHERE id = :i"), {"i": entry_id}).scalar() == "PLATFORM_LP_CHECK"


def test_crud_on_core_tables(lp_engine):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from backend.app.core.security import hash_password
    from backend.app.models import Customer, Membership, MemberRole, MembershipStatus, Organization, User

    suffix = uuid.uuid4().hex[:8]
    with Session(lp_engine) as db:
        org = Organization(name=f"LP Org {suffix}", slug=f"lp-org-{suffix}")
        db.add(org)
        db.flush()
        user = User(email=f"lp-{suffix}@example.test", full_name="LP User", hashed_password=hash_password(PASSWORD))
        db.add(user)
        db.flush()
        db.add(Membership(organization_id=org.id, user_id=user.id, role=MemberRole.OWNER, status=MembershipStatus.ACTIVE))
        cust = Customer(
            organization_id=org.id, customer_number="CUS-000001", display_name="LP Customer",
            currency="INR", payment_terms_days=30,
        )
        db.add(cust)
        db.commit()

        got = db.scalars(select(Customer).where(Customer.organization_id == org.id)).one()
        got.display_name = "LP Customer Renamed"
        db.commit()
        db.expire_all()
        assert db.get(Customer, cust.id).display_name == "LP Customer Renamed"

        db.delete(db.get(Customer, cust.id))
        db.delete(db.scalars(select(Membership).where(Membership.user_id == user.id)).one())
        db.delete(db.get(User, user.id))
        db.delete(db.get(Organization, org.id))
        db.commit()
        assert db.get(Organization, org.id) is None


def test_select_for_update_and_skip_locked(lp_engine):
    from sqlalchemy import select
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    from backend.app.models import Organization

    suffix = uuid.uuid4().hex[:8]
    with Session(lp_engine) as setup:
        org = Organization(name=f"LP Lock {suffix}", slug=f"lp-lock-{suffix}")
        setup.add(org)
        setup.commit()
        org_id = org.id
    try:
        with Session(lp_engine) as a, Session(lp_engine) as b:
            locked = a.scalars(select(Organization).where(Organization.id == org_id).with_for_update()).one()
            assert locked.id == org_id
            # Another transaction cannot take the row lock...
            with pytest.raises(OperationalError) as exc_info:
                b.scalars(select(Organization).where(Organization.id == org_id).with_for_update(nowait=True)).all()
            assert _sqlstate(exc_info.value) == "55P03"  # lock_not_available, NOT a privilege error
            b.rollback()
            # ...and SKIP LOCKED (durable job / outbox claiming) simply skips it.
            skipped = b.scalars(select(Organization).where(Organization.id == org_id).with_for_update(skip_locked=True)).all()
            assert skipped == []
            a.rollback()
            b.rollback()
    finally:
        with Session(lp_engine) as cleanup:
            cleanup.delete(cleanup.get(Organization, org_id))
            cleanup.commit()


def test_scheduler_advisory_lock(lp_engine):
    from sqlalchemy import text

    from backend.app.services.scheduler import ADVISORY_LOCK_KEY

    with lp_engine.connect() as one, lp_engine.connect() as two:
        assert one.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar() is True
        assert two.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar() is False
        assert one.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar() is True


def test_scheduler_run_as_runtime_role(lp_engine):
    """A full billing-job run (advisory lock, outbox, durable jobs, heartbeat upsert)."""
    from sqlalchemy.orm import Session

    from backend.app.services.scheduler import run_billing_jobs

    with Session(lp_engine) as db:
        counts = run_billing_jobs(db)
    assert counts.get("skipped_locked", 0) == 0
    assert counts.get("errors", 0) == 0, counts


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE lp_should_fail (id int)",
        "DROP TABLE users",
        "ALTER TABLE users ADD COLUMN lp_should_fail int",
        "CREATE INDEX lp_should_fail_ix ON users (email)",
        "TRUNCATE TABLE audit_logs",
        "CREATE SCHEMA lp_should_fail",
        "ALTER TABLE alembic_version RENAME TO lp_should_fail",
        "DROP TABLE alembic_version",
        "CREATE FUNCTION public.lp_should_fail() RETURNS int LANGUAGE sql AS 'SELECT 1'",
        "ALTER TABLE users OWNER TO CURRENT_USER",
        "CREATE TRIGGER lp_should_fail BEFORE INSERT ON users FOR EACH ROW EXECUTE FUNCTION suppress_redundant_updates_trigger()",
    ],
)
def test_ddl_is_denied(lp_engine, statement):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with lp_engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_info:
            conn.execute(text(statement))
        conn.rollback()
    # 42501 insufficient_privilege (also raised for "must be owner of ...").
    assert _sqlstate(exc_info.value) == "42501", str(exc_info.value.orig)


def test_runtime_role_cannot_regrant(lp_engine):
    """GRANT without the grant option is a no-op (PostgreSQL only warns), so PUBLIC gains nothing."""
    from sqlalchemy import text

    with lp_engine.connect() as conn:
        conn.execute(text("GRANT SELECT ON users TO PUBLIC"))
        conn.commit()
        public_grants = conn.execute(
            text(
                "SELECT count(*) FROM pg_class c, aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a "
                "WHERE c.relname = 'users' AND c.relnamespace = 'public'::regnamespace AND a.grantee = 0"
            )
        ).scalar()
    assert public_grants == 0


@pytest.mark.skipif(not OWNER_URL, reason="LEAST_PRIVILEGE_OWNER_DATABASE_URL not set")
def test_future_owner_tables_are_granted_by_default_privileges(lp_engine):
    """What a future migration does: the owner creates a table; the runtime role can use it."""
    from sqlalchemy import create_engine, text

    owner = create_engine(OWNER_URL)
    name = f"lp_future_{uuid.uuid4().hex[:8]}"
    try:
        with owner.begin() as conn:
            conn.execute(text(f"CREATE TABLE {name} (id bigserial PRIMARY KEY, note text)"))
        with lp_engine.begin() as conn:
            new_id = conn.execute(text(f"INSERT INTO {name} (note) VALUES ('x') RETURNING id")).scalar()
            conn.execute(text(f"UPDATE {name} SET note = 'y' WHERE id = :i"), {"i": new_id})
            assert conn.execute(text(f"SELECT note FROM {name} WHERE id = :i"), {"i": new_id}).scalar() == "y"
            conn.execute(text(f"DELETE FROM {name} WHERE id = :i"), {"i": new_id})
        with lp_engine.connect() as conn, pytest.raises(Exception):
            conn.execute(text(f"DROP TABLE {name}"))
    finally:
        with owner.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
        owner.dispose()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_api_serves_as_runtime_role(lp_engine):
    """Boot the real app (uvicorn subprocess) as the runtime role: readiness, login, CRUD."""
    import httpx
    from sqlalchemy.orm import Session

    from backend.app.core.security import hash_password
    from backend.app.models import Membership, MemberRole, MembershipStatus, Organization, User

    suffix = uuid.uuid4().hex[:8]
    email = f"lp-api-{suffix}@example.test"
    with Session(lp_engine) as db:
        org = Organization(name=f"LP API {suffix}", slug=f"lp-api-{suffix}")
        db.add(org)
        db.flush()
        user = User(email=email, full_name="LP Api", hashed_password=hash_password(PASSWORD))
        db.add(user)
        db.flush()
        db.add(Membership(organization_id=org.id, user_id=user.id, role=MemberRole.OWNER, status=MembershipStatus.ACTIVE))
        db.commit()

    port = _free_port()
    env = {
        **os.environ,
        "DATABASE_URL": LP_URL,
        "ENVIRONMENT": "development",
        "DEBUG": "false",
        "SCHEDULER_ENABLED": "false",
        "SMTP_HOST": "",
        "REDIS_URL": "",
        "ALERT_WEBHOOK_URL": "",
        "SECRET_KEY": "lp-verification-secret-key-0123456789abcdef0123456789",
    }
    for key in ("MIGRATION_DATABASE_URL", "MIGRATION_POSTGRES_USER", "MIGRATION_POSTGRES_PASSWORD"):
        env.pop(key, None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO_ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}/api/v1"
    try:
        deadline = time.monotonic() + float(os.environ.get("LP_API_START_TIMEOUT", "300"))
        while True:
            try:
                if httpx.get(f"{base}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            assert proc.poll() is None, "uvicorn exited early"
            assert time.monotonic() < deadline, "API did not start"
            time.sleep(0.5)

        ready = httpx.get(f"{base}/health/ready", timeout=10)
        assert ready.status_code == 200, ready.text
        assert ready.json()["checks"]["migrations"]["status"] == "at_head"

        login = httpx.post(f"{base}/auth/login", json={"email": email, "password": PASSWORD}, timeout=20)
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert httpx.get(f"{base}/auth/me", headers=headers, timeout=10).status_code == 200

        created = httpx.post(
            f"{base}/customers",
            json={"display_name": "LP Runtime Customer", "email": "lp-runtime@example.test", "payment_terms_days": 15},
            headers=headers, timeout=20,
        )
        assert created.status_code == 201, created.text
        listed = httpx.get(f"{base}/customers", headers=headers, timeout=10)
        assert listed.status_code == 200
        assert "LP Runtime Customer" in listed.text

        bad = httpx.post(f"{base}/auth/login", json={"email": email, "password": "wrong-Passw0rd"}, timeout=20)
        assert bad.status_code == 401
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

"""Row level security verified as the PRODUCTION runtime role (NOSUPERUSER, NOBYPASSRLS).

A superuser (the compose bootstrap POSTGRES_USER) ignores every RLS policy, so RLS is only
verified here, connected as the least-privilege role created by deploy/sql/least_privilege.sql.

Skipped unless LEAST_PRIVILEGE_DATABASE_URL is set (runtime role, migrated database prepared with
deploy/sql/least_privilege.sql). LEAST_PRIVILEGE_OWNER_DATABASE_URL (owner/superuser, same
database) additionally checks that the startup guard refuses the superuser. Keep TEST_DATABASE_URL
on a different database: conftest truncates it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

LP_URL = os.environ.get("LEAST_PRIVILEGE_DATABASE_URL")
OWNER_URL = os.environ.get("LEAST_PRIVILEGE_OWNER_DATABASE_URL")

pytestmark = pytest.mark.skipif(not LP_URL, reason="LEAST_PRIVILEGE_DATABASE_URL not set")

REPO_ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "Str0ngPassw0rd!"


@pytest.fixture(scope="module")
def lp_engine():
    """Runtime-role engine wired exactly like the app engine (core/database.py)."""
    from sqlalchemy import create_engine, event

    from backend.app.core.tenant_context import sync_pg_rls_context

    engine = create_engine(LP_URL, connect_args={"options": "-c timezone=UTC"}, pool_pre_ping=True)

    @event.listens_for(engine, "before_cursor_execute")
    def _sync(conn, cursor, statement, parameters, context, executemany):
        sync_pg_rls_context(conn, statement)

    @event.listens_for(engine, "rollback")
    def _clear_rb(conn):
        conn.info.pop("rls_org_id", None)

    @event.listens_for(engine, "commit")
    def _clear_c(conn):
        conn.info.pop("rls_org_id", None)

    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def two_tenants(lp_engine):
    """Two organizations, each with an owner, a customer and an invoice, created as the system."""
    from sqlalchemy.orm import Session

    from backend.app.core.security import hash_password
    from backend.app.core.tenant_context import system_context
    from backend.app.models import Customer, Membership, MemberRole, MembershipStatus, Organization, User

    out = {}
    with system_context(), Session(lp_engine) as db:
        for label in ("a", "b"):
            suffix = uuid.uuid4().hex[:8]
            org = Organization(name=f"RLS {label.upper()} {suffix}", slug=f"rls-{label}-{suffix}")
            db.add(org)
            db.flush()
            user = User(email=f"rls-{label}-{suffix}@example.com", full_name=f"RLS {label}", hashed_password=hash_password(PASSWORD))
            db.add(user)
            db.flush()
            db.add(Membership(organization_id=org.id, user_id=user.id, role=MemberRole.OWNER, status=MembershipStatus.ACTIVE))
            cust = Customer(
                organization_id=org.id, customer_number=f"RLS-{suffix}", display_name=f"RLS Customer {label.upper()} {suffix}",
                currency="INR", payment_terms_days=30,
            )
            db.add(cust)
            db.commit()
            out[label] = {"org_id": org.id, "customer_id": cust.id, "email": user.email, "customer_name": cust.display_name}
    return out


def test_runtime_role_is_nosuperuser_nobypassrls(lp_engine):
    from sqlalchemy import text

    with lp_engine.connect() as conn:
        row = conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
    assert row == (False, False)


def test_startup_guard_accepts_runtime_role_in_production(lp_engine, monkeypatch):
    from backend.app.core import database

    monkeypatch.setattr(database.settings, "ENVIRONMENT", "production")
    database.assert_runtime_role_unprivileged(lp_engine)  # no exception


@pytest.mark.skipif(not OWNER_URL, reason="LEAST_PRIVILEGE_OWNER_DATABASE_URL not set")
def test_startup_guard_refuses_superuser_in_production(monkeypatch):
    from sqlalchemy import create_engine

    from backend.app.core import database

    owner = create_engine(OWNER_URL)
    try:
        monkeypatch.setattr(database.settings, "ENVIRONMENT", "production")
        with pytest.raises(database.PrivilegedDatabaseRoleError):
            database.assert_runtime_role_unprivileged(owner)
    finally:
        owner.dispose()


def test_rls_raw_sql_sees_only_the_context_tenant(lp_engine, two_tenants):
    """Raw SQL bypasses the ORM filter: only the database policy can stop it."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from backend.app.core.tenant_context import reset_tenant_context, system_context, tenant_context

    a, b = two_tenants["a"], two_tenants["b"]
    with Session(lp_engine) as db:
        with tenant_context(a["org_id"]):
            ids = {r[0] for r in db.execute(text("SELECT id FROM customers"))}
            assert a["customer_id"] in ids
            assert b["customer_id"] not in ids
            # Explicitly asking for B's row returns nothing.
            assert db.execute(text("SELECT id FROM customers WHERE id = :i"), {"i": b["customer_id"]}).all() == []
        db.rollback()

        reset_tenant_context()
        assert db.execute(text("SELECT id FROM customers")).all() == []
        db.rollback()

        with system_context():
            ids = {r[0] for r in db.execute(text("SELECT id FROM customers"))}
            assert {a["customer_id"], b["customer_id"]} <= ids
        db.rollback()


def test_rls_context_switch_inside_one_transaction(lp_engine, two_tenants):
    """A system lookup followed by a tenant query on the same connection must re-sync (the bug
    class fixed in core/tenant_context.sync_pg_rls_context): never run under __SYSTEM__."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from backend.app.core.tenant_context import system_context, tenant_context

    a, b = two_tenants["a"], two_tenants["b"]
    with Session(lp_engine) as db:
        with system_context():
            assert len(db.execute(text("SELECT id FROM customers WHERE id IN (:x, :y)"), {"x": a["customer_id"], "y": b["customer_id"]}).all()) == 2
        with tenant_context(a["org_id"]):
            ids = {r[0] for r in db.execute(text("SELECT id FROM customers"))}
        assert b["customer_id"] not in ids
        assert a["customer_id"] in ids
        db.rollback()


def test_rls_blocks_cross_tenant_writes(lp_engine, two_tenants):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.orm import Session

    from backend.app.core.tenant_context import tenant_context

    a, b = two_tenants["a"], two_tenants["b"]
    with Session(lp_engine) as db:
        with tenant_context(a["org_id"]):
            res = db.execute(text("UPDATE customers SET display_name = 'hijacked' WHERE id = :i"), {"i": b["customer_id"]})
            assert res.rowcount == 0
            res = db.execute(text("DELETE FROM customers WHERE id = :i"), {"i": b["customer_id"]})
            assert res.rowcount == 0
        db.rollback()

        with tenant_context(a["org_id"]):
            with pytest.raises(DBAPIError) as exc:
                db.execute(
                    text(
                        "INSERT INTO customers (id, organization_id, customer_number, display_name, currency, payment_terms_days, "
                        "status, created_at, updated_at) VALUES (:id, :org, 'CUS-X', 'planted', 'INR', 30, 'ACTIVE', now(), now())"
                    ),
                    {"id": str(uuid.uuid4()), "org": b["org_id"]},
                )
            assert "row-level security" in str(exc.value).lower()
        db.rollback()


def test_orm_and_rls_together_for_a_tenant(lp_engine, two_tenants):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from backend.app.core.tenant_context import tenant_context
    from backend.app.models import Customer

    a, b = two_tenants["a"], two_tenants["b"]
    with Session(lp_engine) as db, tenant_context(b["org_id"]):
        ids = {c.id for c in db.scalars(select(Customer))}
        assert b["customer_id"] in ids
        assert a["customer_id"] not in ids
        assert db.get(Customer, a["customer_id"]) is None


def test_platform_console_counts_see_the_organization_under_rls(lp_engine, two_tenants):
    """Platform requests carry no tenant context; the console's per-organization document counts
    must still be scoped to that organization (not fail closed to 0 under RLS, not cross tenants)."""
    from sqlalchemy.orm import Session

    from backend.app.core.tenant_context import get_current_tenant_id, reset_tenant_context
    from backend.app.models.platform import PlatformRole, PlatformStaff
    from backend.app.services import platform_org_service

    reset_tenant_context()
    actor = platform_org_service.Actor(
        staff=PlatformStaff(email="console@rooman.test", full_name="Console", role=PlatformRole.PLATFORM_ADMINISTRATOR),
        session_id=None, ip_address=None, user_agent=None,
    )
    with Session(lp_engine) as db:
        for label in ("a", "b"):
            detail = platform_org_service.organization_detail(db, two_tenants[label]["org_id"], actor)
            assert detail["documents"]["customer_count"] == 1
            assert platform_org_service.renewals_waiting(db, two_tenants[label]["org_id"]) == 0
        db.rollback()
    assert get_current_tenant_id() is None


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_real_api_as_runtime_role_isolates_tenants(two_tenants):
    """Boot the real app as the runtime role and use it as tenant A: B's data is invisible."""
    import httpx

    a, b = two_tenants["a"], two_tenants["b"]
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
        "SECRET_KEY": "rls-verification-secret-key-0123456789abcdef0123456789",
    }
    for key in ("MIGRATION_DATABASE_URL", "MIGRATION_POSTGRES_USER", "MIGRATION_POSTGRES_PASSWORD", "TEST_DATABASE_URL"):
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

        login = httpx.post(f"{base}/auth/login", json={"email": a["email"], "password": PASSWORD}, timeout=20)
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        listed = httpx.get(f"{base}/customers", headers=headers, timeout=10)
        assert listed.status_code == 200, listed.text
        assert a["customer_name"] in listed.text
        assert b["customer_name"] not in listed.text
        assert httpx.get(f"{base}/customers/{b['customer_id']}", headers=headers, timeout=10).status_code == 404

        created = httpx.post(
            f"{base}/customers",
            json={"display_name": "RLS Runtime Created", "email": "rls-created@example.com", "payment_terms_days": 15},
            headers=headers, timeout=20,
        )
        assert created.status_code == 201, created.text
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def _trial_org_with_request(db, label: str):
    """A trial organization with an Owner and one submitted subscription request (as the system)."""
    from backend.app.models import Membership, MemberRole, MembershipStatus, Organization, OrganizationStatus, User
    from backend.app.models.base import utcnow
    from backend.app.models.subscription_access import SubscriptionRequest

    suffix = uuid.uuid4().hex[:8]
    org = Organization(name=f"RLS trial {label} {suffix}", slug=f"rls-trial-{label}-{suffix}", status=OrganizationStatus.ACTIVE,
                       trial_started_at=utcnow(), trial_ends_at=utcnow(), module_access="trial")
    db.add(org)
    db.flush()
    user = User(email=f"rls-trial-{label}-{suffix}@example.com", full_name="Trial Owner", hashed_password="x")
    db.add(user)
    db.flush()
    db.add(Membership(organization_id=org.id, user_id=user.id, role=MemberRole.OWNER, status=MembershipStatus.ACTIVE))
    req = SubscriptionRequest(organization_id=org.id, modules=["quotes"], seats=3, billing_cycle="annual",
                              requested_by_user_id=user.id)
    db.add(req)
    db.commit()
    return org.id, req.id


def test_rls_isolates_subscription_requests_and_entitlements(lp_engine):
    """The trial/subscription tables are tenant tables under the runtime role too."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from backend.app.core.tenant_context import system_context, tenant_context

    with system_context(), Session(lp_engine) as db:
        org_a, req_a = _trial_org_with_request(db, "a")
        org_b, req_b = _trial_org_with_request(db, "b")
    with Session(lp_engine) as db:
        with tenant_context(org_a):
            ids = {r[0] for r in db.execute(text("SELECT id FROM subscription_requests"))}
            assert req_a in ids and req_b not in ids
            # Writing another organization's row is refused by the policy's WITH CHECK.
            with pytest.raises(Exception):
                db.execute(text(
                    "INSERT INTO organization_entitlements (id, organization_id, module_key, source, created_at, updated_at) "
                    "VALUES (:i, :o, 'reports', 'platform', now(), now())"), {"i": str(uuid.uuid4()), "o": org_b})
                db.flush()
        db.rollback()


def test_approval_works_as_runtime_role(lp_engine):
    """Regression: approving read the request back after commit outside the tenant context, which
    row level security hides from the runtime role (500 after a committed approval)."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from backend.app.core.security import hash_password
    from backend.app.core.tenant_context import system_context, tenant_context
    from backend.app.models import Organization, OrganizationStatus
    from backend.app.models.platform import PlatformRole, PlatformStaff
    from backend.app.models.subscription_access import OrganizationEntitlement
    from backend.app.services import subscription_request_service as svc
    from backend.app.services.platform_org_service import Actor

    with system_context(), Session(lp_engine) as db:
        org_id, req_id = _trial_org_with_request(db, "approve")
        staff = PlatformStaff(email=f"rls-admin-{uuid.uuid4().hex[:8]}@rooman.test", full_name="RLS Admin",
                              hashed_password=hash_password(PASSWORD), role=PlatformRole.PLATFORM_ADMINISTRATOR)
        db.add(staff)
        db.commit()
        staff_id = staff.id
    with Session(lp_engine) as db:
        actor = Actor(staff=db.get(PlatformStaff, staff_id), session_id=None, ip_address=None, user_agent=None)
        with patch("backend.app.services.subscription_request_service.send_email", return_value=True):
            out = svc.approve(db, req_id, actor, seats=4, reason="Runtime role approval")
        assert out["status"] == "approved" and out["approved_seats"] == 4
        assert db.get(Organization, org_id).status == OrganizationStatus.ACTIVE
        with tenant_context(org_id):
            assert db.scalars(select(OrganizationEntitlement.module_key)
                              .where(OrganizationEntitlement.organization_id == org_id)).all() == ["quotes"]

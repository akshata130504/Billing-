"""Phase 3: the platform console API - directory, organization detail, lifecycle, staff, audit,
dashboard and health. Authorization is server-side by platform role; responses are metadata only.

Suspension acts through the Phase 1 scheduler safeguards; the end-to-end scheduler tests here drive
the lifecycle through the platform API and reuse the Phase 1 fixtures.
"""
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.api.platform_deps import CSRF_COOKIE, CSRF_HEADER, get_platform_context
from backend.app.core.config import settings
from backend.app.core.database import engine
from backend.app.core.totp import totp
from backend.app.models import Customer, MemberRole, Organization, OrganizationStatus
from backend.app.models.platform import PlatformAuditLog, PlatformRole, PlatformStaff
from backend.app.services import org_lifecycle
from backend.app.services import platform_auth_service as auth_svc
from backend.app.services import platform_staff_service
from backend.app.services.scheduler import run_billing_jobs
from backend.tests.test_scheduler_org_lifecycle import (  # noqa: F401  (fixtures)
    _assert_processed,
    _assert_untouched,
    _seed_due_work,
    _state,
    gateway,
    outbox_seen,
)

PLATFORM = "http://platform.test"
API = "/api/v1/platform"
PASSWORD = "Platform-Passw0rd-2026!"
ADMIN = PlatformRole.PLATFORM_ADMINISTRATOR
OPS = PlatformRole.PLATFORM_OPERATIONS
SUPPORT = PlatformRole.PLATFORM_SUPPORT
REASON = "Customer asked us to pause the account (test)"


# --- helpers -----------------------------------------------------------------------------------------------


class Staff:
    def __init__(self, db, role):
        from backend.app.main import app

        self.db = db
        self.enrolment = auth_svc.create_staff(
            db, email=f"console-{uuid.uuid4().hex[:8]}@rooman.test", full_name=f"Console {role.value}",
            role=role, password=PASSWORD, actor="test",
        )
        self.id = self.enrolment.staff.id
        self.client = TestClient(app, base_url=PLATFORM)
        self.sign_in()

    def sign_in(self):
        self.db.expire_all()
        staff = self.db.get(PlatformStaff, self.id)
        staff.totp_last_used_step = None
        self.db.commit()
        first = self.client.post(f"{API}/auth/login", json={"email": self.enrolment.staff.email, "password": PASSWORD})
        assert first.status_code == 200, first.text
        # Current step, not the previous one: the server accepts its own step +/- 1, so a current-step
        # code stays valid even if a 30 s boundary passes before the request is verified (a previous-
        # step code would then fall outside the window and be refused). Replay protection is
        # unaffected: totp_last_used_step was cleared above and step_up() pins it again.
        resp = self.client.post(f"{API}/auth/2fa", json={"challenge_token": first.json()["challenge_token"],
                                                         "code": totp(self.enrolment.totp_secret, at=time.time())})
        assert resp.status_code == 200, resp.text
        self.session_id = resp.json()["session_id"]
        return resp

    def csrf(self):
        return {CSRF_HEADER: self.client.cookies.get(CSRF_COOKIE, path="/")}

    def get(self, path, **kw):
        return self.client.get(f"{API}{path}", **kw)

    def post(self, path, body=None, **kw):
        return self.client.post(f"{API}{path}", json=body or {}, headers=self.csrf(), **kw)

    def step_up(self):
        self.db.expire_all()
        staff = self.db.get(PlatformStaff, self.id)
        staff.totp_last_used_step = int(time.time() // 30) - 1  # below the current step, whatever sign-in used
        self.db.commit()
        resp = self.post("/auth/step-up", {"code": totp(self.enrolment.totp_secret, at=time.time())})
        assert resp.status_code == 200, resp.text


@pytest.fixture
def admin(db):
    return Staff(db, ADMIN)


@pytest.fixture
def ops(db):
    return Staff(db, OPS)


@pytest.fixture
def support(db):
    return Staff(db, SUPPORT)


def _audit(db, action, **filters):
    db.expire_all()
    stmt = select(PlatformAuditLog).where(PlatformAuditLog.action == action)
    for key, value in filters.items():
        stmt = stmt.where(getattr(PlatformAuditLog, key) == value)
    return db.scalars(stmt.order_by(PlatformAuditLog.occurred_at)).all()


def _org(db, org_id):
    db.expire_all()
    return db.get(Organization, org_id)


def _automation(db, org_id):
    """org_lifecycle.automation_allowed reads the row FOR NO KEY UPDATE on PostgreSQL (by design);
    end the transaction so the test session does not keep that lock."""
    allowed = org_lifecycle.automation_allowed(db, org_id)
    db.rollback()
    return allowed


def _suspend(actor, org_id, ticket="SUP-1001"):
    return actor.post(f"/organizations/{org_id}/suspend", {"reason": REASON, "ticket_ref": ticket})


FORBIDDEN_KEYS = {"amount", "total", "subtotal", "balance", "invoice", "invoices", "payment", "payments",
                  "customer", "customers", "price", "razorpay", "key_id", "key_secret", "smtp", "password",
                  "hashed_password", "totp_secret", "refresh_token_hash", "token_hash", "secret"}


def _keys(value, found=None):
    found = set() if found is None else found
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(k.lower())
            _keys(v, found)
    elif isinstance(value, list):
        for v in value:
            _keys(v, found)
    return found


# --- authentication / boundary -------------------------------------------------------------------------------


CONSOLE_GETS = ["/dashboard", "/health", "/audit", "/organizations", "/staff"]


@pytest.mark.parametrize("path", CONSOLE_GETS)
def test_console_routes_need_a_platform_session(path, tenant):
    from backend.app.main import app

    anon = TestClient(app, base_url=PLATFORM)
    assert anon.get(f"{API}{path}").status_code == 401
    assert anon.get(f"{API}{path}", headers=tenant.headers()).status_code == 401  # tenant Owner token
    assert TestClient(app).get(f"{API}{path}", headers=tenant.headers()).status_code == 404  # tenant host


def test_every_console_route_requires_platform_authentication():
    """Route table: every platform route except the sign-in steps depends on the platform session."""
    from fastapi.routing import APIRoute

    from backend.app.main import app

    def depends_on_context(dependant):
        return any(d.call is get_platform_context or depends_on_context(d) for d in dependant.dependencies)

    open_routes = {f"{API}/auth/login", f"{API}/auth/2fa", f"{API}/auth/refresh"}
    platform_routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith(f"{API}/")]
    assert len(platform_routes) >= 25
    unguarded = [r.path for r in platform_routes if r.path not in open_routes and not depends_on_context(r.dependant)]
    assert unguarded == []


def test_no_route_deletes_organizations_or_audit_or_creates_staff():
    from fastapi.routing import APIRoute

    from backend.app.main import app

    routes = {(m, r.path) for r in app.routes if isinstance(r, APIRoute) and r.path.startswith(f"{API}/") for m in r.methods}
    assert not [p for m, p in routes if m in ("DELETE", "PUT", "PATCH") and "sessions" not in p]
    assert ("POST", f"{API}/staff") not in routes
    assert not [p for m, p in routes if "purge" in p or "impersonat" in p or "login-as" in p or p.endswith("/delete")]
    assert not [p for m, p in routes if "jobs/run" in p]


# --- directory ------------------------------------------------------------------------------------------------


def test_directory_lists_metadata_only(admin, db, tenant):
    tenant.customer(display_name="Zebra Secret Customer Pvt Ltd")
    tenant.add_member("finance", MemberRole.FINANCE)
    db.commit()
    resp = admin.get("/organizations", params={"q": tenant.organization.slug})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1 and body["page"] == 1
    item = body["items"][0]
    assert set(item) == {"id", "name", "slug", "status", "jobs_paused", "member_count", "created_at",
                         "updated_at", "status_changed_at", "deletion_scheduled_for"}
    assert item["id"] == tenant.organization.id and item["status"] == "active"
    assert item["member_count"] == 2
    assert "Zebra Secret Customer" not in resp.text


def test_directory_search_filter_sort_and_pages(admin, db):
    from backend.tests.conftest import Tenant

    tag = uuid.uuid4().hex[:6]
    tenants = [Tenant(db, f"{tag}{i}") for i in range(3)]
    for i, t in enumerate(tenants):
        t.organization.name = f"Dirtest {tag} {'CBA'[i]}"
    db.commit()
    by_name = admin.get("/organizations", params={"q": f"dirtest {tag}", "sort": "name", "direction": "asc"}).json()
    assert [o["name"][-1] for o in by_name["items"]] == ["A", "B", "C"]
    assert admin.get("/organizations", params={"q": tenants[0].organization.id}).json()["total"] == 1
    # wildcards are literal, not "match everything"
    assert admin.get("/organizations", params={"q": "%"}).json()["total"] == 0
    assert admin.get("/organizations", params={"q": "_"}).json()["total"] == 0
    paged = admin.get("/organizations", params={"q": f"dirtest {tag}", "page_size": 2, "sort": "name"}).json()
    assert paged["total"] == 3 and len(paged["items"]) == 2 and paged["total_pages"] == 2
    page2 = admin.get("/organizations", params={"q": f"dirtest {tag}", "page_size": 2, "page": 2, "sort": "name"}).json()
    assert len(page2["items"]) == 1
    assert admin.get("/organizations", params={"page_size": 101}).status_code == 422
    assert admin.get("/organizations", params={"sort": "legal_name"}).status_code == 422
    assert _suspend_direct(db, tenants[1].organization.id)
    suspended = admin.get("/organizations", params={"q": f"dirtest {tag}", "status": "suspended"}).json()
    assert [o["id"] for o in suspended["items"]] == [tenants[1].organization.id]
    assert admin.get("/organizations", params={"status": "bogus"}).status_code == 422


def _suspend_direct(db, org_id):
    org = db.get(Organization, org_id)
    org.status = OrganizationStatus.SUSPENDED
    db.commit()
    return True


def test_detail_is_metadata_only_and_audited(admin, db, tenant):
    tenant.customer(display_name="Hidden Customer Name 42")
    tenant.invoice(tenant.customer(display_name="Another Hidden Customer"), amount="98765.43")
    resp = admin.get(f"/organizations/{tenant.organization.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["owners"] == [{"full_name": tenant.owner.full_name, "email": tenant.owner.email}]
    assert body["members"]["active"] == 1 and body["members"]["by_role"]["owner"] == 1
    assert body["lifecycle"]["status"] == "active" and body["lifecycle"]["automation_running"] is True
    assert set(body["allowed_actions"]) == {"suspend", "schedule_deletion", "pause_jobs", "revoke_sessions"}
    assert set(body["documents"]) == {"customer_count", "quote_count", "invoice_count", "credit_note_count",
                                      "payment_count", "subscription_count"}
    assert body["documents"]["customer_count"] == 2 and body["documents"]["invoice_count"] == 1  # counts only
    assert not (_keys(body) & FORBIDDEN_KEYS), _keys(body) & FORBIDDEN_KEYS
    for leaked in ("Hidden Customer Name 42", "Another Hidden Customer", "98765", "98,765"):
        assert leaked not in resp.text
    rows = _audit(db, "ORGANIZATION_VIEWED", organization_id=tenant.organization.id)
    assert rows and rows[-1].platform_staff_id == admin.id and rows[-1].organization_name_snapshot == tenant.organization.name


def test_detail_unknown_org_404(admin):
    assert admin.get(f"/organizations/{uuid.uuid4()}").status_code == 404


def test_allowed_actions_follow_the_role(ops, support, tenant):
    assert set(ops.get(f"/organizations/{tenant.organization.id}").json()["allowed_actions"]) == {"suspend", "revoke_sessions"}
    assert support.get(f"/organizations/{tenant.organization.id}").json()["allowed_actions"] == []


# --- authorization by platform role ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/staff", "/audit"])
def test_administrator_only_reads(path, admin, ops, support, db):
    assert admin.get(path).status_code == 200
    for actor in (ops, support):
        resp = actor.get(path)
        assert resp.status_code == 403
        assert _audit(db, "PLATFORM_ACCESS_DENIED", platform_staff_id=actor.id)


def test_every_role_reads_directory_dashboard_and_health(admin, ops, support, tenant):
    for actor in (admin, ops, support):
        for path in ("/organizations", f"/organizations/{tenant.organization.id}",
                     f"/organizations/{tenant.organization.id}/activity", "/dashboard", "/health"):
            assert actor.get(path).status_code == 200, (actor, path)


def test_support_cannot_change_lifecycle(support, db, tenant):
    oid = tenant.organization.id
    support.step_up()
    for path, body in (("suspend", {"reason": REASON, "ticket_ref": "SUP-1"}), ("reactivate", {"reason": REASON}),
                       ("schedule-deletion", {"reason": REASON, "ticket_ref": "SUP-1"}),
                       ("cancel-deletion", {"reason": REASON}), ("jobs/pause", {"reason": REASON}),
                       ("jobs/resume", {"reason": REASON}), ("revoke-sessions", {"reason": REASON})):
        assert support.post(f"/organizations/{oid}/{path}", body).status_code == 403, path
    assert _org(db, oid).status == OrganizationStatus.ACTIVE
    assert len(_audit(db, "PLATFORM_ACCESS_DENIED", platform_staff_id=support.id)) >= 7


def test_operations_can_suspend_but_not_delete_or_pause(ops, db, tenant):
    oid = tenant.organization.id
    ops.step_up()
    assert _suspend(ops, oid).status_code == 200
    assert ops.post(f"/organizations/{oid}/schedule-deletion", {"reason": REASON, "ticket_ref": "SUP-2"}).status_code == 403
    assert ops.post(f"/organizations/{oid}/jobs/pause", {"reason": REASON}).status_code == 403
    assert ops.post(f"/organizations/{oid}/reactivate", {"reason": REASON}).status_code == 200


def test_sensitive_actions_need_a_step_up(admin, db, tenant):
    oid = tenant.organization.id
    resp = _suspend(admin, oid)
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "STEP_UP_REQUIRED"
    assert admin.post(f"/organizations/{oid}/schedule-deletion", {"reason": REASON, "ticket_ref": "T-1"}).status_code == 403
    assert admin.post(f"/organizations/{oid}/jobs/pause", {"reason": REASON}).status_code == 403
    assert _org(db, oid).status == OrganizationStatus.ACTIVE
    admin.step_up()
    assert _suspend(admin, oid).status_code == 200


def test_writes_need_the_csrf_header(admin, tenant):
    admin.step_up()
    resp = admin.client.post(f"{API}/organizations/{tenant.organization.id}/suspend",
                             json={"reason": REASON, "ticket_ref": "SUP-3"})
    assert resp.status_code == 403 and resp.json()["error"]["code"] != "STEP_UP_REQUIRED"


# --- lifecycle ---------------------------------------------------------------------------------------------------


def test_suspend_requires_reason_and_ticket(admin, db, tenant):
    oid = tenant.organization.id
    admin.step_up()
    assert admin.post(f"/organizations/{oid}/suspend", {"reason": REASON}).status_code == 422
    assert admin.post(f"/organizations/{oid}/suspend", {"reason": "short", "ticket_ref": "SUP-1"}).status_code == 422
    assert admin.post(f"/organizations/{oid}/suspend", {"reason": "          x", "ticket_ref": "SUP-1"}).status_code == 422
    assert admin.post(f"/organizations/{oid}/suspend", {"reason": REASON, "ticket_ref": "  "}).status_code == 422
    assert _org(db, oid).status == OrganizationStatus.ACTIVE


def test_suspend_then_reactivate_keeps_automation_paused(admin, db, tenant):
    oid = tenant.organization.id
    admin.step_up()
    resp = _suspend(admin, oid, ticket="SUP-4242")
    assert resp.status_code == 200, resp.text
    org = _org(db, oid)
    assert org.status == OrganizationStatus.SUSPENDED and org.status_reason == REASON
    assert org.status_changed_by_staff_id == admin.id and org.status_changed_at is not None
    assert _automation(db, oid) is False
    row = _audit(db, "ORGANIZATION_SUSPENDED", organization_id=oid)[-1]
    assert (row.reason, row.ticket_ref, row.platform_staff_id, row.staff_role_snapshot, row.target_type) == (
        REASON, "SUP-4242", admin.id, "platform_administrator", "organization")
    assert row.details["from"]["status"] == "active" and row.details["to"]["status"] == "suspended"

    resp = admin.post(f"/organizations/{oid}/reactivate", {"reason": "Payment issue resolved by the customer"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["changed"]["to"] == {"status": "active", "jobs_paused": True, "deletion_scheduled_for": None}
    org = _org(db, oid)
    assert org.status == OrganizationStatus.ACTIVE and org.jobs_paused is True
    assert _automation(db, oid) is False  # nothing replays until resumed
    detail = admin.get(f"/organizations/{oid}").json()
    assert detail["lifecycle"]["automation_running"] is False and "resume_jobs" in detail["allowed_actions"]

    resp = admin.post(f"/organizations/{oid}/jobs/resume", {"reason": "Tenant owner confirmed on call SUP-4242"})
    assert resp.status_code == 200, resp.text
    assert _automation(db, oid) is True
    assert _audit(db, "TENANT_JOBS_RESUMED", organization_id=oid)


@pytest.mark.parametrize("action,body,start", [
    ("suspend", {"reason": REASON, "ticket_ref": "T-9"}, OrganizationStatus.SUSPENDED),
    ("suspend", {"reason": REASON, "ticket_ref": "T-9"}, OrganizationStatus.PENDING_DELETION),
    ("reactivate", {"reason": REASON}, OrganizationStatus.ACTIVE),
    ("reactivate", {"reason": REASON}, OrganizationStatus.PENDING_DELETION),
    ("cancel-deletion", {"reason": REASON}, OrganizationStatus.ACTIVE),
    ("cancel-deletion", {"reason": REASON}, OrganizationStatus.SUSPENDED),
    ("schedule-deletion", {"reason": REASON, "ticket_ref": "T-9"}, OrganizationStatus.PENDING_DELETION),
    ("suspend", {"reason": REASON, "ticket_ref": "T-9"}, OrganizationStatus.DELETED),
    ("reactivate", {"reason": REASON}, OrganizationStatus.DELETED),
    ("schedule-deletion", {"reason": REASON, "ticket_ref": "T-9"}, OrganizationStatus.DELETED),
])
def test_invalid_transitions_are_refused_and_audited(admin, db, tenant, action, body, start):
    oid = tenant.organization.id
    org = db.get(Organization, oid)
    org.status = start
    db.commit()
    admin.step_up()
    resp = admin.post(f"/organizations/{oid}/{action}", body)
    assert resp.status_code == 409, resp.text
    assert _org(db, oid).status == start
    refused = _audit(db, "ORGANIZATION_LIFECYCLE_REFUSED", organization_id=oid)
    assert refused and refused[-1].result == "denied" and refused[-1].details["attempted"] == action.replace("-", "_")


def test_schedule_and_cancel_deletion(admin, db, tenant):
    oid = tenant.organization.id
    admin.step_up()
    resp = admin.post(f"/organizations/{oid}/schedule-deletion", {"reason": "Owner requested closure by email",
                                                                   "ticket_ref": "SUP-77"})
    assert resp.status_code == 200, resp.text
    org = _org(db, oid)
    assert org.status == OrganizationStatus.PENDING_DELETION
    scheduled = org.deletion_scheduled_for.replace(tzinfo=org.deletion_scheduled_for.tzinfo or timezone.utc)
    expected = datetime.now(timezone.utc) + timedelta(days=settings.PLATFORM_DELETION_WAITING_DAYS)
    assert abs((scheduled - expected).total_seconds()) < 120
    assert _automation(db, oid) is False
    assert db.get(Organization, oid) is not None  # nothing is deleted
    assert admin.get(f"/organizations/{oid}").json()["allowed_actions"] == ["cancel_deletion", "pause_jobs", "revoke_sessions"]

    resp = admin.post(f"/organizations/{oid}/cancel-deletion", {"reason": "Owner changed their mind (SUP-77)"})
    assert resp.status_code == 200, resp.text
    org = _org(db, oid)
    assert org.status == OrganizationStatus.SUSPENDED and org.deletion_scheduled_for is None
    assert _audit(db, "ORGANIZATION_DELETION_SCHEDULED", organization_id=oid)
    assert _audit(db, "ORGANIZATION_DELETION_CANCELLED", organization_id=oid)


def test_schedule_deletion_from_suspended(admin, db, tenant):
    oid = tenant.organization.id
    admin.step_up()
    assert _suspend(admin, oid).status_code == 200
    assert admin.post(f"/organizations/{oid}/schedule-deletion", {"reason": REASON, "ticket_ref": "T-3"}).status_code == 200
    assert _org(db, oid).status == OrganizationStatus.PENDING_DELETION


def test_jobs_pause_resume_rules(admin, db, tenant):
    oid = tenant.organization.id
    admin.step_up()
    assert admin.post(f"/organizations/{oid}/jobs/resume", {"reason": REASON}).status_code == 409  # not paused
    assert admin.post(f"/organizations/{oid}/jobs/pause", {"reason": REASON}).status_code == 200
    assert _org(db, oid).jobs_paused is True
    assert admin.post(f"/organizations/{oid}/jobs/pause", {"reason": REASON}).status_code == 409
    assert _suspend(admin, oid).status_code == 200
    # a suspended organization must be reactivated before its automation can resume
    assert admin.post(f"/organizations/{oid}/jobs/resume", {"reason": REASON}).status_code == 409
    assert _audit(db, "TENANT_JOBS_PAUSED", organization_id=oid)


def test_lifecycle_on_one_tenant_never_touches_another(admin, db, tenant):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    admin.step_up()
    assert _suspend(admin, tenant.organization.id).status_code == 200
    assert _org(db, other.organization.id).status == OrganizationStatus.ACTIVE
    assert _automation(db, other.organization.id) is True


def test_suspension_does_not_change_tenant_access(client, admin, db, tenant):
    """Platform-side suspension only (Phase 3 decision): tenant sign-in and reads are unchanged."""
    admin.step_up()
    assert _suspend(admin, tenant.organization.id).status_code == 200
    assert client.get("/api/v1/auth/me", headers=tenant.headers()).status_code == 200
    assert client.get("/api/v1/customers", headers=tenant.headers()).status_code == 200


def test_platform_staff_get_no_tenant_data_through_tenant_routes(admin, client, tenant):
    token = admin.client.cookies.get("rb_platform_access", path="/api/v1/platform")
    for path in ("/api/v1/customers", "/api/v1/invoices", "/api/v1/payments", "/api/v1/auth/me"):
        assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 401
        assert admin.client.get(path).status_code == 404  # tenant routes do not exist on the platform host


# --- scheduler behaviour through the console --------------------------------------------------------------------


def test_suspended_org_gets_no_billing_work_then_resumes_only_when_told(admin, db, tenant, gateway, outbox_seen):
    ids = _seed_due_work(db, tenant)
    admin.step_up()
    assert _suspend(admin, tenant.organization.id).status_code == 200
    before = _state(db, ids)
    run_billing_jobs(db)
    after = _state(db, ids)
    _assert_untouched(before, after, ids)
    assert gateway.charges == []

    # reactivation does not replay anything: automation stays paused
    assert admin.post(f"/organizations/{tenant.organization.id}/reactivate", {"reason": REASON}).status_code == 200
    detail = admin.get(f"/organizations/{tenant.organization.id}").json()
    assert detail["lifecycle"]["renewals_waiting"] >= 1
    run_billing_jobs(db)
    _assert_untouched(before, _state(db, ids), ids)
    assert gateway.charges == []

    # an explicit resume by a Platform Administrator lets the normal billing run proceed
    assert admin.post(f"/organizations/{tenant.organization.id}/jobs/resume", {"reason": REASON}).status_code == 200
    run_billing_jobs(db)
    _assert_processed(_state(db, ids))


def test_pending_deletion_org_gets_no_billing_work(admin, db, tenant, gateway, outbox_seen):
    ids = _seed_due_work(db, tenant)
    admin.step_up()
    assert admin.post(f"/organizations/{tenant.organization.id}/schedule-deletion",
                      {"reason": REASON, "ticket_ref": "T-5"}).status_code == 200
    before = _state(db, ids)
    run_billing_jobs(db)
    _assert_untouched(before, _state(db, ids), ids)
    assert gateway.charges == []


# --- staff ----------------------------------------------------------------------------------------------------


STAFF_KEYS = {"id", "email", "full_name", "role", "is_active", "deactivated_at", "two_factor_enrolled",
              "last_login_at", "created_at", "active_sessions", "sign_in_locked"}


def test_staff_list_and_detail_hold_no_credentials(admin, ops, db):
    resp = admin.get("/staff")
    assert resp.status_code == 200
    items = {s["id"]: s for s in resp.json()["items"]}
    assert set(items[ops.id]) == STAFF_KEYS
    assert items[ops.id]["role"] == "platform_operations" and items[ops.id]["two_factor_enrolled"] is True
    assert items[ops.id]["active_sessions"] == 1 and items[ops.id]["last_login_at"]
    detail = admin.get(f"/staff/{ops.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["sessions"][0]["id"] == ops.session_id and body["is_self"] is False
    staff = db.get(PlatformStaff, ops.id)
    for text in (resp.text, detail.text):
        assert staff.hashed_password not in text and staff.totp_secret not in text
        assert not (_keys(json.loads(text)) & {"hashed_password", "totp_secret", "refresh_token_hash", "token_hash"})


def test_deactivate_and_activate_staff(admin, ops, db):
    admin.step_up()
    resp = admin.post(f"/staff/{ops.id}/deactivate", {"reason": "Left the operations team"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False and resp.json()["active_sessions"] == 0
    assert ops.get("/dashboard").status_code == 401  # their session ended
    row = _audit(db, "PLATFORM_STAFF_DEACTIVATED", target_id=ops.id)[-1]
    assert row.platform_staff_id == admin.id and row.reason == "Left the operations team"

    resp = admin.post(f"/staff/{ops.id}/activate", {"reason": "Rejoined the operations team"})
    assert resp.status_code == 200 and resp.json()["is_active"] is True
    assert ops.get("/dashboard").status_code == 401  # old credentials stay dead
    ops.sign_in()
    assert ops.get("/dashboard").status_code == 200
    assert _audit(db, "PLATFORM_STAFF_ACTIVATED", target_id=ops.id)


def test_staff_guard_rails(admin, db, monkeypatch):
    admin.step_up()
    resp = admin.post(f"/staff/{admin.id}/deactivate", {"reason": "Trying to lock myself out"})
    assert resp.status_code == 409
    other = Staff(db, ADMIN)
    monkeypatch.setattr(platform_staff_service, "_active_administrators", lambda db: 1)
    assert admin.post(f"/staff/{other.id}/deactivate", {"reason": "Would remove the last administrator"}).status_code == 409
    assert db.get(PlatformStaff, other.id).is_active is True
    assert admin.post(f"/staff/{uuid.uuid4()}/deactivate", {"reason": "No such staff member here"}).status_code == 404


def test_staff_actions_need_administrator_and_step_up(admin, ops, support, db):
    assert admin.post(f"/staff/{support.id}/deactivate", {"reason": "Needs a fresh code first"}).status_code == 403
    ops.step_up()
    assert ops.post(f"/staff/{support.id}/deactivate", {"reason": "Operations may not do this"}).status_code == 403
    assert ops.post(f"/staff/{support.id}/revoke-sessions", {"reason": "Operations may not do this"}).status_code == 403
    assert db.get(PlatformStaff, support.id).is_active is True


def test_revoke_staff_sessions(admin, support, db):
    assert support.get("/dashboard").status_code == 200
    resp = admin.post(f"/staff/{support.id}/revoke-sessions", {"reason": "Lost laptop reported (SEC-9)"})
    assert resp.status_code == 200 and resp.json()["sessions_revoked"] == 1
    assert support.get("/dashboard").status_code == 401
    assert _audit(db, "PLATFORM_STAFF_SESSIONS_REVOKED", target_id=support.id)[-1].platform_staff_id == admin.id


# --- audit ------------------------------------------------------------------------------------------------------


def test_audit_view_filters_and_pages(admin, db, tenant):
    admin.step_up()
    assert _suspend(admin, tenant.organization.id, ticket="SUP-8").status_code == 200
    resp = admin.get("/audit", params={"organization_id": tenant.organization.id, "action": "ORGANIZATION_SUSPENDED"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1 and body["items"][0]["ticket_ref"] == "SUP-8"
    assert body["items"][0]["staff_email_snapshot"] == admin.enrolment.staff.email
    everything = admin.get("/audit", params={"page_size": 5}).json()
    assert len(everything["items"]) == 5 and everything["total"] > 5
    assert admin.get("/audit", params={"result": "maybe"}).status_code == 422
    activity = admin.get(f"/organizations/{tenant.organization.id}/activity").json()
    assert {i["action"] for i in activity["items"]} >= {"ORGANIZATION_SUSPENDED"}
    assert all(i["organization_id"] == tenant.organization.id for i in activity["items"])


def test_audit_entries_never_carry_credentials(admin, db):
    resp = admin.get("/audit", params={"staff_id": admin.id, "page_size": 100})
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert not (_keys(item.get("details") or {}) & {"password", "code", "token", "secret", "totp"})
    assert admin.enrolment.totp_secret not in resp.text and PASSWORD not in resp.text


def test_audit_has_no_write_methods(admin):
    for method in ("put", "patch", "delete"):
        assert getattr(admin.client, method)(f"{API}/audit", headers=admin.csrf()).status_code == 405


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="append-only enforcement is PostgreSQL's (0028)")
def test_lifecycle_audit_rows_are_immutable(admin, db, tenant):
    import sqlalchemy as sa
    from sqlalchemy.exc import DBAPIError

    admin.step_up()
    assert _suspend(admin, tenant.organization.id).status_code == 200
    row = _audit(db, "ORGANIZATION_SUSPENDED", organization_id=tenant.organization.id)[-1]
    db.close()
    for statement in ("UPDATE platform_audit_logs SET reason = 'x' WHERE id = :i",
                      "DELETE FROM platform_audit_logs WHERE id = :i"):
        with engine.connect() as conn:
            with pytest.raises(DBAPIError):
                conn.execute(sa.text(statement), {"i": row.id})
            conn.rollback()


# --- dashboard and health -----------------------------------------------------------------------------------


def test_dashboard_counts(admin, db, tenant):
    body = admin.get("/dashboard").json()
    counts = body["organizations"]
    assert counts["total"] >= 1 and counts["total"] == sum(counts[s.value] for s in OrganizationStatus)
    assert body["created_last_7_days"] >= 1
    assert any(o["id"] == tenant.organization.id for o in body["recent_organizations"]) or len(body["recent_organizations"]) == 5
    assert body["health"]["api"] == "ok" and body["health"]["database"] == "connected"
    assert set(body["recent_organizations"][0]) == {"id", "name", "slug", "status", "created_at"}


def test_health_exposes_no_secrets_or_connection_details(admin):
    resp = admin.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] == {"status": "connected"}
    assert body["migrations"]["status"] in ("at_head", "behind", "ahead", "unknown", "no_version_table", "empty")
    assert body["platform"]["auth_enabled"] is True and body["platform"]["step_up_minutes"] == 15
    for secret in (settings.SECRET_KEY, settings.PLATFORM_JWT_SECRET, settings.DATABASE_URL or "unused-url"):
        assert secret not in resp.text
    assert "url" not in _keys(body) and "dialect" not in _keys(body)


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="row locks are PostgreSQL behaviour")
def test_lifecycle_waits_briefly_for_a_billing_transaction_then_says_busy(admin, db, tenant, monkeypatch):
    import sqlalchemy as sa

    from backend.app.services import platform_org_service

    monkeypatch.setattr(platform_org_service, "LOCK_TIMEOUT", "1s")
    oid = tenant.organization.id
    admin.step_up()
    with engine.connect() as billing:  # what org_lifecycle.automation_allowed holds during a charge
        billing.execute(sa.text("SELECT id FROM organizations WHERE id = :i FOR NO KEY UPDATE"), {"i": oid})
        resp = _suspend(admin, oid)
        assert resp.status_code == 409 and "try again" in resp.json()["error"]["message"]
        billing.rollback()
    assert _org(db, oid).status == OrganizationStatus.ACTIVE
    assert _suspend(admin, oid).status_code == 200


# --- phase 3 completion: sessions, history, jobs, activity, audit search ----------------------------


def test_revoke_tenant_sessions_signs_the_org_out_only(client, admin, ops, db, tenant):
    from backend.tests.conftest import Tenant

    login = client.post("/api/v1/auth/login", json={"email": tenant.owner.email, "password": "Str0ngPassw0rd!"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    other = Tenant(db, uuid.uuid4().hex[:8])
    db.commit()
    other_login = client.post("/api/v1/auth/login", json={"email": other.owner.email, "password": "Str0ngPassw0rd!"})
    other_token = other_login.json()["access_token"]

    oid = tenant.organization.id
    assert ops.post(f"/organizations/{oid}/revoke-sessions", {"reason": REASON}).json()["error"]["code"] == "STEP_UP_REQUIRED"
    ops.step_up()
    resp = ops.post(f"/organizations/{oid}/revoke-sessions", {"reason": REASON, "ticket_ref": "SEC-1"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["changed"]["tenant_sessions_revoked"] >= 1
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {other_token}"}).status_code == 200
    row = _audit(db, "TENANT_SESSIONS_REVOKED", organization_id=oid)[-1]
    assert row.platform_staff_id == ops.id and row.ticket_ref == "SEC-1"
    # the tenant can simply sign in again; nothing else changed
    assert client.post("/api/v1/auth/login", json={"email": tenant.owner.email, "password": "Str0ngPassw0rd!"}).status_code == 200


def test_lifecycle_history_filters_to_lifecycle_events(admin, db, tenant):
    oid = tenant.organization.id
    admin.get(f"/organizations/{oid}")  # a view, not lifecycle
    admin.step_up()
    assert _suspend(admin, oid).status_code == 200
    history = admin.get(f"/organizations/{oid}/activity", params={"lifecycle": "true"}).json()
    actions = [i["action"] for i in history["items"]]
    assert "ORGANIZATION_SUSPENDED" in actions and "ORGANIZATION_VIEWED" not in actions
    everything = admin.get(f"/organizations/{oid}/activity").json()
    assert "ORGANIZATION_VIEWED" in [i["action"] for i in everything["items"]]


def test_jobs_view_is_counts_only_and_observation_only(admin, ops, support):
    resp = admin.get("/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"scheduler", "durable_jobs", "durable_jobs_failed_24h", "outbox", "webhooks_received_24h",
                         "organizations_not_running"}
    assert all(isinstance(v, int) for v in body["durable_jobs"].values())
    assert ops.get("/jobs").status_code == 200
    assert support.get("/jobs").status_code == 403
    for method in ("post", "put", "delete"):
        assert getattr(admin.client, method)(f"{API}/jobs", headers=admin.csrf()).status_code == 405


def test_dashboard_recent_activity_respects_the_role(admin, support, db, tenant):
    admin.step_up()
    assert _suspend(admin, tenant.organization.id).status_code == 200
    admin_items = admin.get("/dashboard").json()["recent_activity"]
    assert "ORGANIZATION_SUSPENDED" in [i["action"] for i in admin_items]
    assert any(not i["action"].startswith("ORGANIZATION_") for i in admin_items)  # admins see security events too
    support_items = support.get("/dashboard").json()["recent_activity"]
    from backend.app.services.platform_org_service import LIFECYCLE_EVENTS

    assert support_items and all(i["action"] in LIFECYCLE_EVENTS for i in support_items)


def test_audit_search_by_text_target_and_time(admin, ops, db, tenant):
    admin.step_up()
    assert _suspend(admin, tenant.organization.id, ticket="FIND-ME-77").status_code == 200
    hit = admin.get("/audit", params={"q": "find-me-77"}).json()
    assert hit["total"] == 1 and hit["items"][0]["ticket_ref"] == "FIND-ME-77"
    wildcard = admin.get("/audit", params={"q": "%"}).json()
    assert all("%" in (i["reason"] or "") + (i["action"] or "") for i in wildcard["items"])
    assert admin.post(f"/staff/{ops.id}/revoke-sessions", {"reason": "Target filter test run"}).status_code == 200
    by_target = admin.get("/audit", params={"target_type": "platform_staff", "target_id": ops.id}).json()
    assert by_target["total"] >= 1 and all(i["target_id"] == ops.id for i in by_target["items"])
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert admin.get("/audit", params={"since": future}).json()["total"] == 0
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert admin.get("/audit", params={"until": past, "q": "find-me-77"}).json()["total"] == 0

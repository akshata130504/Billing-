"""Phase 4: tenant access grants, Owner approval, Enter/Exit tenant, emergency dual control.

Platform staff reach tenant data ONLY through an approved, scoped, time-limited grant; every
request re-validates it, is limited to read routes of the granted scopes, and is recorded in both
the platform audit and the tenant's own audit log.
"""
import uuid
from datetime import timedelta

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.grant_scopes import GRANT_READ_ROUTES, READ_METHODS
from backend.app.models import AuditLog, MemberRole, Organization, OrganizationStatus
from backend.app.models.access_grants import TenantAccessGrant
from backend.app.models.base import utcnow
from backend.app.models.platform import PlatformAuditLog, PlatformStaff
from backend.app.services import access_grant_service
from backend.app.services import platform_auth_service as auth_svc
from backend.tests.test_platform_console import ADMIN, OPS, SUPPORT, Staff

G = "/access-grants"
REASON = "Customer reports invoices showing the wrong GST split (ticket)"


@pytest.fixture
def support(db):
    return Staff(db, SUPPORT)


@pytest.fixture
def admin(db):
    return Staff(db, ADMIN)


@pytest.fixture
def tenant_api():
    from backend.app.main import app

    return TestClient(app)  # same application, tenant credentials


@pytest.fixture(autouse=True)
def mail(monkeypatch):
    sent = []
    monkeypatch.setattr("backend.app.services.email.send_email", lambda **kw: sent.append(kw) or True)
    return sent


@pytest.fixture(autouse=True)
def alerts(monkeypatch):
    raised = []
    monkeypatch.setattr(access_grant_service, "send_alert", lambda *a, **kw: raised.append((a, kw)))
    return raised


def _request(staff, org_id, scopes=("READ_CUSTOMERS",), minutes=60, reason=REASON, ticket="SUP-501"):
    return staff.post(G, {"organization_id": org_id, "scopes": list(scopes), "duration_minutes": minutes,
                          "reason": reason, "ticket_ref": ticket})


def _approve(tenant_api, tenant, grant_id, role=MemberRole.OWNER):
    headers = tenant.headers() if role == MemberRole.OWNER else tenant.headers_for_role(role)
    return tenant_api.post(f"/api/v1/organization/platform-access/{grant_id}/approve", headers=headers, json={})


def _enter(staff, grant_id):
    staff.step_up()
    resp = staff.post(f"{G}/{grant_id}/enter")
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _granted(support, tenant, tenant_api, scopes=("READ_CUSTOMERS",)):
    gid = _request(support, tenant.organization.id, scopes).json()["id"]
    assert _approve(tenant_api, tenant, gid).status_code == 200
    return gid, _enter(support, gid)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _grant(db, gid):
    db.expire_all()
    return db.get(TenantAccessGrant, gid)


def _platform_rows(db, action, gid):
    db.expire_all()
    return db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.action == action,
                                                     PlatformAuditLog.target_id == gid)).all()


def _tenant_rows(db, action, gid):
    db.expire_all()
    return db.scalars(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == gid)).all()


# --- request ------------------------------------------------------------------------------------------------


def test_support_requests_and_owners_are_told(support, db, tenant, mail):
    resp = _request(support, tenant.organization.id, ["READ_CUSTOMERS", "READ_INVOICES"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending" and body["expires_at"] is None
    assert body["scopes"] == ["READ_METADATA", "READ_CUSTOMERS", "READ_INVOICES"]  # metadata always included
    assert _platform_rows(db, "ACCESS_GRANT_REQUESTED", body["id"])
    tenant_row = _tenant_rows(db, "PLATFORM_ACCESS_REQUESTED", body["id"])[0]
    assert tenant_row.organization_id == tenant.organization.id and tenant_row.actor_user_id is None
    assert tenant_row.actor_label.startswith("Rooman Platform Support - ")
    assert tenant_row.after_state["actor_type"] == "platform_support" and tenant_row.after_state["ticket_ref"] == "SUP-501"
    assert mail and tenant.owner.email in mail[0]["to"] and "requested access" in mail[0]["subject"]


@pytest.mark.parametrize("body,status", [
    ({"reason": "too short"}, 422),
    ({"scopes": ["WRITE_INVOICES"]}, 422),
    ({"scopes": ["*"]}, 422),
    ({"minutes": 241}, 422),
    ({"minutes": 1}, 422),
    ({"ticket": ""}, 422),
])
def test_invalid_requests_are_refused(support, tenant, body, status):
    kwargs = {"scopes": body.get("scopes", ["READ_CUSTOMERS"]), "minutes": body.get("minutes", 60),
              "reason": body.get("reason", REASON), "ticket": body.get("ticket", "SUP-1")}
    assert _request(support, tenant.organization.id, **kwargs).status_code == status


def test_operations_and_tenants_cannot_request(db, tenant, tenant_api):
    ops = Staff(db, OPS)
    assert _request(ops, tenant.organization.id).status_code == 403
    assert tenant_api.post(f"/api/v1/platform{G}", headers=tenant.headers(), json={}).status_code == 401


def test_one_open_request_per_staff_and_org(support, tenant):
    assert _request(support, tenant.organization.id).status_code == 200
    assert _request(support, tenant.organization.id).status_code == 409


def test_deleted_org_and_unknown_org(support, db, tenant):
    assert _request(support, str(uuid.uuid4())).status_code == 404
    org = db.get(Organization, tenant.organization.id)
    org.status = OrganizationStatus.DELETED
    db.commit()
    assert _request(support, tenant.organization.id).status_code == 409


def test_support_sees_only_own_requests_admin_sees_all(support, admin, db, tenant):
    other = Staff(db, SUPPORT)
    mine = _request(support, tenant.organization.id).json()["id"]
    theirs = _request(other, tenant.organization.id).json()["id"]
    assert [g["id"] for g in support.get(G).json()["items"]] == [mine]
    assert support.get(f"{G}/{theirs}").status_code == 404
    ids = {g["id"] for g in admin.get(G).json()["items"]}
    assert {mine, theirs} <= ids


# --- tenant Owner decision ------------------------------------------------------------------------------------


def test_owner_approves_admin_cannot_but_can_see_and_revoke(support, db, tenant, tenant_api):
    gid = _request(support, tenant.organization.id).json()["id"]
    listed = tenant_api.get("/api/v1/organization/platform-access", headers=tenant.headers_for_role(MemberRole.ADMIN))
    assert listed.status_code == 200 and listed.json()["items"][0]["reason"] == REASON
    assert _approve(tenant_api, tenant, gid, MemberRole.ADMIN).status_code == 403
    for role in (MemberRole.FINANCE, MemberRole.VIEWER):
        assert tenant_api.get("/api/v1/organization/platform-access", headers=tenant.headers_for_role(role)).status_code == 403
    before = utcnow()
    resp = _approve(tenant_api, tenant, gid)
    assert resp.status_code == 200, resp.text
    grant = _grant(db, gid)
    assert grant.status == "approved" and grant.approved_by_user_id == tenant.owner.id
    expires = grant.expires_at.replace(tzinfo=grant.expires_at.tzinfo or before.tzinfo)
    assert timedelta(minutes=59) < expires - before <= timedelta(minutes=61)
    row = _tenant_rows(db, "PLATFORM_ACCESS_APPROVED", gid)[0]
    assert row.actor_label == tenant.owner.full_name
    assert _platform_rows(db, "ACCESS_GRANT_APPROVED", gid)
    assert _approve(tenant_api, tenant, gid).status_code == 409  # already decided
    revoked = tenant_api.post(f"/api/v1/organization/platform-access/{gid}/revoke",
                              headers=tenant.headers_for_role(MemberRole.ADMIN), json={"reason": "No longer needed"})
    assert revoked.status_code == 200 and _grant(db, gid).status == "revoked"


def test_owner_denies_and_requester_cancels(support, db, tenant, tenant_api):
    gid = _request(support, tenant.organization.id).json()["id"]
    resp = tenant_api.post(f"/api/v1/organization/platform-access/{gid}/deny", headers=tenant.headers(),
                           json={"reason": "Please call us instead"})
    assert resp.status_code == 200 and _grant(db, gid).status == "denied"
    assert _tenant_rows(db, "PLATFORM_ACCESS_DENIED", gid)
    gid2 = _request(support, tenant.organization.id).json()["id"]
    assert support.post(f"{G}/{gid2}/cancel").status_code == 200 and _grant(db, gid2).status == "cancelled"
    assert support.post(f"{G}/{gid2}/cancel").status_code == 409


def test_another_tenant_cannot_see_or_decide(support, db, tenant, tenant_api):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    db.commit()
    gid = _request(support, tenant.organization.id).json()["id"]
    assert tenant_api.get("/api/v1/organization/platform-access", headers=other.headers()).json()["items"] == []
    assert _approve(tenant_api, other, gid).status_code == 404
    assert _grant(db, gid).status == "pending"


# --- enter / scopes ---------------------------------------------------------------------------------------------


def test_enter_needs_approval_step_up_and_the_requester(support, db, tenant, tenant_api):
    gid = _request(support, tenant.organization.id).json()["id"]
    support.step_up()
    assert support.post(f"{G}/{gid}/enter").status_code == 409  # still pending
    assert _approve(tenant_api, tenant, gid).status_code == 200
    other = Staff(db, SUPPORT)
    other.step_up()
    assert other.post(f"{G}/{gid}/enter").status_code == 404
    fresh = Staff(db, SUPPORT)
    gid2 = _request(fresh, tenant.organization.id).json()["id"]
    assert _approve(tenant_api, tenant, gid2).status_code == 200
    assert fresh.post(f"{G}/{gid2}/enter").json()["error"]["code"] == "STEP_UP_REQUIRED"


def test_granted_scope_reads_only_this_tenant(support, db, tenant, tenant_api):
    from backend.tests.conftest import Tenant

    mine = tenant.customer(display_name="Granted Customer")
    other = Tenant(db, uuid.uuid4().hex[:8])
    theirs = other.customer(display_name="Other Tenant Customer")
    db.commit()
    gid, token = _granted(support, tenant, tenant_api)
    resp = tenant_api.get("/api/v1/customers", headers=_bearer(token))
    assert resp.status_code == 200, resp.text
    assert "Granted Customer" in resp.text and "Other Tenant Customer" not in resp.text
    assert tenant_api.get(f"/api/v1/customers/{mine.id}", headers=_bearer(token)).status_code == 200
    assert tenant_api.get(f"/api/v1/customers/{theirs.id}", headers=_bearer(token)).status_code == 404
    assert tenant_api.get("/api/v1/organization", headers=_bearer(token)).status_code == 200  # READ_METADATA
    grant = _grant(db, gid)
    assert grant.status == "active" and grant.request_count == 4
    platform = _platform_rows(db, "TENANT_DATA_ACCESSED", gid)
    tenant_side = _tenant_rows(db, "PLATFORM_DATA_VIEWED", gid)
    assert len(platform) == len(tenant_side) == 4
    assert platform[0].platform_staff_id == support.id and platform[0].details["scope"] == "READ_CUSTOMERS"
    assert tenant_side[0].actor_user_id is None and tenant_side[0].after_state["access_grant_id"] == gid


@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/invoices"),                  # scope not granted
    ("get", "/api/v1/payments"),
    ("get", "/api/v1/audit-logs"),
    ("get", "/api/v1/audit-logs/export"),         # never under any grant
    ("get", "/api/v1/reports/export"),
    ("get", "/api/v1/settings/integrations"),
    ("get", "/api/v1/dashboard/financial-summary"),
    ("get", "/api/v1/imports"),
    ("post", "/api/v1/customers"),                # writes are never allowed
    ("post", "/api/v1/payments"),
    ("post", "/api/v1/credit-notes"),
    ("post", "/api/v1/team/invite"),
    ("patch", "/api/v1/organization"),
    ("delete", "/api/v1/organization"),
])
def test_everything_outside_the_scopes_is_refused_and_audited(support, db, tenant, tenant_api, method, path):
    gid, token = _granted(support, tenant, tenant_api)
    resp = getattr(tenant_api, method)(path, headers=_bearer(token), **({"json": {}} if method != "get" and method != "delete" else {}))
    assert resp.status_code in (403, 404, 405), (path, resp.status_code, resp.text)
    if resp.status_code == 403:
        assert _platform_rows(db, "TENANT_ACCESS_DENIED", gid)
        assert _tenant_rows(db, "PLATFORM_ACCESS_REFUSED", gid)


def test_even_all_scopes_allow_no_write_or_money_action(support, db, tenant, tenant_api):
    all_scopes = ["READ_CUSTOMERS", "READ_QUOTES", "READ_INVOICES", "READ_PAYMENTS", "READ_SUBSCRIPTIONS", "READ_AUDIT", "READ_CONFIG"]
    gid, token = _granted(support, tenant, tenant_api, all_scopes)
    customer = tenant.customer()
    invoice = tenant.invoice(customer)
    db.commit()
    for method, path in [
        ("post", f"/api/v1/invoices/{invoice.id}/void"), ("post", f"/api/v1/invoices/{invoice.id}/send"),
        ("post", "/api/v1/payments"), ("post", f"/api/v1/invoices/{invoice.id}/payments"),
        ("post", "/api/v1/credit-notes"), ("put", f"/api/v1/customers/{customer.id}"),
        ("patch", f"/api/v1/customers/{customer.id}"), ("delete", f"/api/v1/customers/{customer.id}"),
        ("post", "/api/v1/checkout/razorpay/order"), ("put", "/api/v1/settings/integrations/razorpay"),
        ("post", "/api/v1/team/invite"), ("patch", f"/api/v1/team/{tenant.owner.id}"),
        ("get", "/api/v1/audit-logs/export"), ("get", "/api/v1/reports/export"), ("get", "/api/v1/settings/integrations"),
    ]:
        kwargs = {"json": {}} if method in ("post", "put", "patch") else {}
        resp = getattr(tenant_api, method)(path, headers=_bearer(token), **kwargs)
        assert resp.status_code in (401, 403, 404, 405), (method, path, resp.status_code)
        assert resp.status_code != 200
    # the allowed reads still work under the same grant
    assert tenant_api.get(f"/api/v1/invoices/{invoice.id}", headers=_bearer(token)).status_code == 200


def test_grant_token_is_not_a_user_session(support, db, tenant, tenant_api):
    gid, token = _granted(support, tenant, tenant_api)
    for path in ("/api/v1/auth/me", "/api/v1/auth/sessions"):
        # refused: 401 where the route needs a user session, 403 where the grant allow-list refuses it
        assert tenant_api.get(path, headers=_bearer(token)).status_code in (401, 403), path
    assert tenant_api.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code in (401, 422)
    # grant decisions can never be made under a grant (no self-approval path)
    assert tenant_api.post(f"/api/v1/organization/platform-access/{gid}/approve", headers=_bearer(token), json={}).status_code == 403
    assert tenant_api.post(f"/api/v1/organization/platform-access/{gid}/revoke", headers=_bearer(token), json={}).status_code == 403
    # and a tenant user cannot use the grant-session endpoints
    assert tenant_api.get("/api/v1/platform-access/session", headers=tenant.headers()).status_code == 401


def test_grant_token_is_useless_on_platform_routes(support, tenant, tenant_api):
    gid, token = _granted(support, tenant, tenant_api)
    assert support.client.get("/api/v1/platform/dashboard", headers=_bearer(token)).status_code == 401


# --- revalidation on every request ------------------------------------------------------------------------------


@pytest.mark.parametrize("ending", ["tenant_revoke", "staff_revoke", "expiry", "platform_logout", "deactivated", "exit"])
def test_access_ends_on_the_next_request(support, admin, db, tenant, tenant_api, ending):
    gid, token = _granted(support, tenant, tenant_api)
    assert tenant_api.get("/api/v1/customers", headers=_bearer(token)).status_code == 200
    if ending == "tenant_revoke":
        assert tenant_api.post(f"/api/v1/organization/platform-access/{gid}/revoke", headers=tenant.headers(),
                               json={"reason": "Done, thanks"}).status_code == 200
    elif ending == "staff_revoke":
        assert admin.post(f"{G}/{gid}/revoke", {"reason": "Ticket resolved already"}).status_code == 200
    elif ending == "expiry":
        grant = db.get(TenantAccessGrant, gid)
        grant.approved_at = utcnow() - timedelta(hours=2)  # expiry must stay after approval (DB check)
        grant.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    elif ending == "platform_logout":
        assert support.post("/auth/logout").status_code == 204
    elif ending == "deactivated":
        auth_svc.deactivate_staff(db, email=db.get(PlatformStaff, support.id).email, reason="left", actor="test")
    elif ending == "exit":
        assert tenant_api.post("/api/v1/platform-access/exit", headers=_bearer(token)).status_code == 204
        assert _tenant_rows(db, "PLATFORM_ACCESS_ENDED", gid)
    assert tenant_api.get("/api/v1/customers", headers=_bearer(token)).status_code == 401
    if ending == "expiry":
        assert _grant(db, gid).status == "expired"
        assert _platform_rows(db, "ACCESS_GRANT_EXPIRED", gid) and _tenant_rows(db, "PLATFORM_ACCESS_EXPIRED", gid)


def test_exit_then_re_enter_issues_a_new_token_and_kills_the_old(support, db, tenant, tenant_api):
    gid, first = _granted(support, tenant, tenant_api)
    assert tenant_api.post("/api/v1/platform-access/exit", headers=_bearer(first)).status_code == 204
    second = _enter(support, gid)
    assert tenant_api.get("/api/v1/customers", headers=_bearer(first)).status_code == 401
    assert tenant_api.get("/api/v1/customers", headers=_bearer(second)).status_code == 200


def test_grant_session_endpoint_describes_the_access(support, tenant, tenant_api):
    gid, token = _granted(support, tenant, tenant_api, ["READ_CUSTOMERS", "READ_INVOICES"])
    info = tenant_api.get("/api/v1/platform-access/session", headers=_bearer(token)).json()
    assert info["organization_id"] == tenant.organization.id and info["grant_id"] == gid
    assert info["scopes"] == ["READ_METADATA", "READ_CUSTOMERS", "READ_INVOICES"]
    assert "Customers" in info["areas"] and info["expires_at"]


def test_tampered_or_foreign_grant_tokens_fail(support, db, tenant, tenant_api):
    import jwt

    gid, token = _granted(support, tenant, tenant_api)
    claims = jwt.decode(token, options={"verify_signature": False})
    forged = jwt.encode({**claims, "scp": claims["scp"] + ["READ_PAYMENTS"]}, "not-the-key", algorithm="HS256")
    assert tenant_api.get("/api/v1/payments", headers=_bearer(forged)).status_code == 401
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    db.commit()
    from backend.app.core.config import settings

    moved = jwt.encode({**claims, "org": other.organization.id}, settings.SECRET_KEY, algorithm="HS256")
    assert tenant_api.get("/api/v1/customers", headers=_bearer(moved)).status_code == 401


# --- tenant visibility ---------------------------------------------------------------------------------------------


def test_tenant_sees_platform_access_in_its_own_audit_log(support, db, tenant, tenant_api):
    gid, token = _granted(support, tenant, tenant_api)
    tenant_api.get("/api/v1/customers", headers=_bearer(token))
    resp = tenant_api.get("/api/v1/audit-logs", headers=tenant.headers(), params={"page_size": 100})
    assert resp.status_code == 200
    text = resp.text
    for action in ("PLATFORM_ACCESS_REQUESTED", "PLATFORM_ACCESS_APPROVED", "PLATFORM_ACCESS_STARTED", "PLATFORM_DATA_VIEWED"):
        assert action in text, action
    assert "Rooman Platform Support - " in text
    active = tenant_api.get("/api/v1/organization/platform-access/active", headers=tenant.headers()).json()["items"]
    assert [g["id"] for g in active] == [gid]


# --- emergency ------------------------------------------------------------------------------------------------------


def _emergency(admin, org_id, minutes=30):
    return admin.post(f"{G}/emergency", {"organization_id": org_id, "scopes": ["READ_INVOICES"],
                                         "duration_minutes": minutes, "reason": "Active fraud on invoices, owner unreachable",
                                         "ticket_ref": "INC-77"})


def test_emergency_requires_a_second_administrator(admin, support, db, tenant, tenant_api, alerts, mail):
    assert support.post(f"{G}/emergency", {"organization_id": tenant.organization.id, "scopes": [], "duration_minutes": 30,
                                           "reason": REASON, "ticket_ref": "INC-1"}).status_code == 403
    assert _emergency(admin, tenant.organization.id, minutes=61).status_code == 422
    resp = _emergency(admin, tenant.organization.id)
    assert resp.status_code == 200, resp.text
    gid = resp.json()["id"]
    assert resp.json()["is_emergency"] and alerts and alerts[0][0][0] == "platform.emergency_access.requested"
    # the tenant Owner does not approve emergency access, and the requester cannot approve it
    assert _approve(tenant_api, tenant, gid).status_code == 409
    admin.step_up()
    assert admin.post(f"{G}/{gid}/emergency-approve").status_code == 403
    assert _platform_rows(db, "EMERGENCY_ACCESS_APPROVED", gid)[0].result == "denied"
    second = Staff(db, ADMIN)
    assert second.post(f"{G}/{gid}/emergency-approve").json()["error"]["code"] == "STEP_UP_REQUIRED"
    second.step_up()
    approved = second.post(f"{G}/{gid}/emergency-approve")
    assert approved.status_code == 200, approved.text
    grant = _grant(db, gid)
    assert grant.status == "approved" and grant.approved_by_staff_id == second.id and grant.approved_by_user_id is None
    assert any(a[0][0] == "platform.emergency_access.approved" and a[1]["severity"] == "critical" for a in alerts)
    assert mail and "EMERGENCY" in mail[-1]["subject"]
    assert _tenant_rows(db, "PLATFORM_ACCESS_APPROVED", gid)[0].after_state["emergency"] is True
    token = _enter(admin, gid)
    assert tenant_api.get("/api/v1/invoices", headers=_bearer(token)).status_code == 200
    assert tenant_api.post("/api/v1/payments", headers=_bearer(token), json={}).status_code == 403  # still no financial writes
    # post-incident review
    item = admin.get(f"{G}/{gid}").json()
    assert item["review_due_at"] and item["review_overdue"] is False
    assert admin.post(f"{G}/{gid}/review", {"notes": "short"}).status_code == 422
    reviewed = second.post(f"{G}/{gid}/review", {"notes": "Fraud confirmed and contained; owner informed by phone."})
    assert reviewed.status_code == 200 and reviewed.json()["reviewed_at"]
    assert _platform_rows(db, "EMERGENCY_ACCESS_REVIEWED", gid)


def test_normal_requests_are_not_staff_approvable(admin, support, db, tenant):
    gid = _request(support, tenant.organization.id).json()["id"]
    admin.step_up()
    assert admin.post(f"{G}/{gid}/emergency-approve").status_code == 409
    assert _grant(db, gid).status == "pending"


# --- database constraints ----------------------------------------------------------------------------------------------


def test_database_refuses_self_approval_and_a_second_open_grant(support, db, tenant):
    from sqlalchemy.exc import IntegrityError

    gid = _request(support, tenant.organization.id).json()["id"]
    grant = db.get(TenantAccessGrant, gid)
    grant.approved_by_staff_id = support.id  # approver == requester
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    dup = TenantAccessGrant(organization_id=tenant.organization.id, requested_by_staff_id=support.id, status="pending",
                            scopes=["READ_METADATA"], reason=REASON, ticket_ref="X-1", requested_duration_minutes=60,
                            is_emergency=False, request_count=0)
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# --- the allow-list itself ----------------------------------------------------------------------------------------------


def test_every_allow_listed_route_exists_and_is_read_only():
    from backend.app.main import app

    reads = {(r.path, m) for r in app.routes if isinstance(r, APIRoute) for m in r.methods}
    for template in GRANT_READ_ROUTES:
        assert (f"/api/v1{template}", "GET") in reads, template
    assert READ_METHODS == frozenset({"GET", "HEAD"})
    forbidden_words = ("export", "integrations", "secret", "credential", "import", "report", "webhook", "auth", "ai/", "device")
    assert not [t for t in GRANT_READ_ROUTES if any(w in t for w in forbidden_words)]


def test_every_allow_listed_route_works_under_a_grant(support, db, tenant, tenant_api):
    """Smoke: no allowed read route crashes for a grant context (no tenant user / membership)."""
    all_scopes = ["READ_CUSTOMERS", "READ_QUOTES", "READ_INVOICES", "READ_PAYMENTS", "READ_SUBSCRIPTIONS", "READ_AUDIT", "READ_CONFIG"]
    gid, token = _granted(support, tenant, tenant_api, all_scopes)
    missing = str(uuid.uuid4())
    for template in GRANT_READ_ROUTES:
        path = "/api/v1" + template
        for param in ("{customer_id}", "{quote_id}", "{deal_id}", "{invoice_id}", "{credit_note_id}", "{payment_id}",
                      "{case_id}", "{subscription_id}", "{plan_id}", "{product_id}", "{meter_id}", "{template_id}",
                      "{rule_id}", "{schedule_id}", "{series_id}"):
            path = path.replace(param, missing)
        resp = tenant_api.get(path, headers=_bearer(token))
        assert resp.status_code in (200, 404, 422), (template, resp.status_code, resp.text[:300])

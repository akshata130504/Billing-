"""Trial -> subscription request -> Platform Administrator decision -> entitlements and seats.

Covers the backend rules: trial expiry decided by the server (UTC), the trial-expired allow-list,
one open request per organization, Administrator-only decisions with step-up (Operations and
Support read only), approval keeping the trial Owner as the organization's Owner (no platform
account), module entitlement on the API (FEATURE_NOT_ENTITLED), seat limits, IDOR / cross-tenant
refusals, pre-existing organizations keeping unrestricted access, and the scheduler step.
"""
import json
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.app.core.entitlements import module_for_path, registry
from backend.app.core.security import create_access_token
from backend.app.core.tenant_context import tenant_context
from backend.app.models import (
    Membership,
    MemberRole,
    MembershipStatus,
    Organization,
    OrganizationStatus,
    User,
)
from backend.app.models.base import utcnow
from backend.app.models.platform import PlatformAuditLog, PlatformRole, PlatformStaff
from backend.app.models.subscription_access import OrganizationEntitlement, SubscriptionRequest
from backend.app.services import platform_audit
from backend.app.services.org_access import expire_due_trials
from backend.tests.test_platform_console import Staff

API = "/api/v1"
REPO = Path(__file__).resolve().parents[2]
SEND = "backend.app.services.subscription_request_service.send_email"


class Member:
    def __init__(self, db, org: Organization, role: MemberRole):
        self.user = User(email=f"m-{uuid.uuid4().hex[:8]}@trial.test", full_name=f"{role.value} person",
                         hashed_password="unused-in-token-tests", is_active=True)
        db.add(self.user)
        db.flush()
        self.membership = Membership(organization_id=org.id, user_id=self.user.id, role=role,
                                     status=MembershipStatus.ACTIVE)
        db.add(self.membership)
        db.commit()
        self.headers = {"Authorization": f"Bearer {create_access_token(self.user.id, org.id, role.value)}"}


def _org(db, *, status=OrganizationStatus.ACTIVE, ends_in=timedelta(days=3), module_access="trial") -> Organization:
    """An approved self-service organization in its trial (ACTIVE + module_access 'trial') by default."""
    now = utcnow()
    org = Organization(name=f"Trial Co {uuid.uuid4().hex[:6]}", slug=f"trial-{uuid.uuid4().hex[:8]}", status=status,
                       trial_started_at=now - timedelta(days=3) + ends_in, trial_ends_at=now + ends_in,
                       module_access=module_access)
    db.add(org)
    db.commit()
    return org


def _code(resp) -> str:
    return resp.json()["error"]["code"]


def _request(client, member, **overrides):
    body = {"modules": ["quotes", "reports"], "seats": 5, "billing_cycle": "annual", "notes": "Need quotes"}
    body.update(overrides)
    return client.post(f"{API}/subscription-requests", json=body, headers=member.headers)


@pytest.fixture
def admin(db):
    staff = Staff(db, PlatformRole.PLATFORM_ADMINISTRATOR)
    staff.step_up()
    return staff


# --- registry ------------------------------------------------------------------------------------


def test_module_registry_is_shared_with_frontend_and_matches_api_routes(client):
    backend = (REPO / "backend/app/core/modules.json").read_bytes()
    frontend = (REPO / "frontend/src/entitlements/modules.json").read_bytes()
    assert backend == frontend
    reg = registry()
    assert {"customers", "products", "invoices", "payments"} == set(reg.base_keys)
    # Every prefix matches at least one mounted API route.
    from backend.app.main import app
    paths = [r.path[len(API):] for r in app.routes if getattr(r, "path", "").startswith(API)]
    for prefix, key in reg.prefixes:
        assert any(p == prefix or p.startswith(prefix + "/") for p in paths), (prefix, key)
    # Whole-segment, longest-prefix matching.
    assert module_for_path("/payments/reconciliation/summary") == "reconciliation"
    assert module_for_path("/payments/{payment_id}") == "payments"
    assert module_for_path("/paymentsx") is None
    assert module_for_path("/auth/me") is None
    assert module_for_path("/settings/integrations/smtp") == "integrations"
    assert module_for_path("/settings/number-series") is None


def test_nav_items_in_registry_exist_in_frontend_navigation():
    keys = json.loads((REPO / "frontend/src/appUi/keys.json").read_text(encoding="utf-8"))
    nav = set(keys["nav"]) if isinstance(keys, dict) and "nav" in keys else None
    reg = registry()
    mapped = list(reg.core_nav_items) + [n for m in reg.modules for n in m.nav_items]
    assert len(mapped) == len(set(mapped))
    if nav is not None:
        assert set(mapped) <= nav


# --- trial ---------------------------------------------------------------------------------------


def test_trial_org_can_use_every_module(client, db):
    org = _org(db)
    owner = Member(db, org, MemberRole.OWNER)
    for path in ("/customers", "/quotes", "/expenses", "/reports/dashboard", "/projects"):
        r = client.get(f"{API}{path}", headers=owner.headers)
        assert r.status_code != 403, (path, r.text)
    me = client.get(f"{API}/auth/me", headers=owner.headers).json()
    assert me["access"]["status"] == "trial"
    assert set(me["access"]["modules"]) == set(registry().all_keys)


def test_trial_expiry_is_decided_by_the_server(client, db):
    org = _org(db, ends_in=timedelta(seconds=-1))  # stored status is still 'trial'
    owner = Member(db, org, MemberRole.OWNER)
    r = client.get(f"{API}/customers", headers=owner.headers)
    assert r.status_code == 403 and _code(r) == "ORGANIZATION_TRIAL_EXPIRED"
    r = client.post(f"{API}/customers", json={"display_name": "x"}, headers=owner.headers)
    assert r.status_code == 403 and _code(r) == "ORGANIZATION_TRIAL_EXPIRED"
    # Allowed: who am I, the subscription page, organization settings and UI config.
    assert client.get(f"{API}/auth/me", headers=owner.headers).json()["access"]["status"] == "trial_expired"
    assert client.get(f"{API}/subscription-requests", headers=owner.headers).status_code == 200
    assert client.get(f"{API}/organization", headers=owner.headers).status_code == 200
    assert client.get(f"{API}/ui-config", headers=owner.headers).status_code == 200


def test_scheduler_records_expired_trials_with_audit(db):
    org = _org(db, ends_in=timedelta(minutes=-5))
    live = _org(db, ends_in=timedelta(days=1))
    assert expire_due_trials(db) >= 1
    db.commit()
    assert expire_due_trials(db) == 0  # recorded once
    db.commit()
    db.refresh(org)
    db.refresh(live)
    # The lifecycle status stays ACTIVE (suspend/reactivate keep working); access is decided per request.
    assert org.status == OrganizationStatus.ACTIVE and live.status == OrganizationStatus.ACTIVE
    rows = db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.organization_id == org.id,
                                                    PlatformAuditLog.action == platform_audit.ORGANIZATION_TRIAL_EXPIRED)).all()
    assert len(rows) == 1
    assert rows[0].staff_email_snapshot == "system:scheduler"  # BUG-16: not "unknown" in the console
    assert db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.organization_id == live.id,
                                                    PlatformAuditLog.action == platform_audit.ORGANIZATION_TRIAL_EXPIRED)).first() is None


# --- organizations created as PENDING_APPROVAL by earlier builds (signup no longer does this) ------


def _pending(db) -> Organization:
    org = Organization(name=f"Pending Co {uuid.uuid4().hex[:6]}", slug=f"pending-{uuid.uuid4().hex[:8]}",
                       status=OrganizationStatus.PENDING_APPROVAL, module_access="trial")
    db.add(org)
    db.commit()
    return org


def test_pending_organization_has_no_tenant_access_and_no_trial(client, db):
    org = _pending(db)
    owner = Member(db, org, MemberRole.OWNER)
    for path in ("/customers", "/subscription-requests", "/reports/dashboard"):
        r = client.get(f"{API}{path}", headers=owner.headers)
        assert r.status_code == 403 and _code(r) == "ORGANIZATION_PENDING_APPROVAL", (path, r.text)
    r = _request(client, owner)
    assert r.status_code == 403 and _code(r) == "ORGANIZATION_PENDING_APPROVAL"
    access = client.get(f"{API}/auth/me", headers=owner.headers).json()["access"]
    assert access["status"] == "pending_approval" and access["trial_ends_at"] is None


def test_organization_approval_starts_the_trial_and_keeps_the_owner(client, db, admin):
    org = _pending(db)
    owner = Member(db, org, MemberRole.OWNER)
    before = utcnow()
    r = admin.post(f"/organizations/{org.id}/approve", {"reason": "Verified business details"})
    assert r.status_code == 200, r.text
    assert r.json()["organization"]["status"] == "active"
    db.expire_all()
    org = db.get(Organization, org.id)
    assert org.status == OrganizationStatus.ACTIVE and org.module_access == "trial"
    started = org.trial_started_at if org.trial_started_at.tzinfo else org.trial_started_at.replace(tzinfo=before.tzinfo)
    ends = org.trial_ends_at if org.trial_ends_at.tzinfo else org.trial_ends_at.replace(tzinfo=before.tzinfo)
    assert started >= before - timedelta(seconds=5) and (ends - started) == timedelta(days=3)
    assert db.get(Membership, owner.membership.id).role == MemberRole.OWNER
    for action in (platform_audit.ORGANIZATION_APPROVED, platform_audit.ORGANIZATION_TRIAL_STARTED):
        assert db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.organization_id == org.id,
                                                         PlatformAuditLog.action == action)).first() is not None
    access = client.get(f"{API}/auth/me", headers=owner.headers).json()["access"]
    assert access["status"] == "trial" and set(access["modules"]) == set(registry().all_keys)
    assert client.get(f"{API}/reports/dashboard", headers=owner.headers).status_code == 200
    # Approving again is refused by the lifecycle (the trial starts once).
    assert admin.post(f"/organizations/{org.id}/approve", {"reason": "Again please"}).status_code == 409


def test_organization_rejection_keeps_it_inaccessible_with_reason(client, db, admin):
    org = _pending(db)
    owner = Member(db, org, MemberRole.OWNER)
    assert admin.post(f"/organizations/{org.id}/reject", {"reason": "short"}).status_code in (409, 422)
    r = admin.post(f"/organizations/{org.id}/reject", {"reason": "Could not verify the business registration"})
    assert r.status_code == 200 and r.json()["organization"]["status"] == "rejected"
    db.expire_all()
    org = db.get(Organization, org.id)
    assert org.status == OrganizationStatus.REJECTED and org.trial_ends_at is None
    r = client.get(f"{API}/customers", headers=owner.headers)
    assert r.status_code == 403 and _code(r) == "ORGANIZATION_REJECTED"
    assert "Could not verify the business registration" in r.json()["error"]["message"]
    me = client.get(f"{API}/auth/me", headers=owner.headers).json()
    assert me["organization"]["status_reason"] == "Could not verify the business registration"
    assert _request(client, owner).status_code == 403


def test_only_administrator_decides_organization_approval(db):
    org = _pending(db)
    for role in (PlatformRole.PLATFORM_OPERATIONS, PlatformRole.PLATFORM_SUPPORT):
        staff = Staff(db, role)
        staff.step_up()
        assert staff.post(f"/organizations/{org.id}/approve", {"reason": "Looks fine to me"}).status_code == 403
        assert staff.post(f"/organizations/{org.id}/reject", {"reason": "Not a fit for us now"}).status_code == 403
    fresh = Staff(db, PlatformRole.PLATFORM_ADMINISTRATOR)  # no recent password re-entry
    r = fresh.post(f"/organizations/{org.id}/approve", {"reason": "Verified business details"})
    assert r.status_code == 403 and _code(r) == "STEP_UP_REQUIRED"
    db.expire_all()
    assert db.get(Organization, org.id).status == OrganizationStatus.PENDING_APPROVAL


def test_suspend_and_reactivate_an_organization_in_its_trial(client, db, admin):
    org = _org(db)
    owner = Member(db, org, MemberRole.OWNER)
    r = admin.post(f"/organizations/{org.id}/suspend", {"reason": "Payment dispute review", "ticket_ref": "SUP-1"})
    assert r.status_code == 200 and r.json()["organization"]["status"] == "suspended"
    assert client.get(f"{API}/customers", headers=owner.headers).status_code == 200  # owner read-only
    r = client.post(f"{API}/customers", json={"display_name": "x"}, headers=owner.headers)
    assert r.status_code == 403 and _code(r) == "ORGANIZATION_SUSPENDED"
    r = admin.post(f"/organizations/{org.id}/reactivate", {"reason": "Dispute resolved now"})
    assert r.status_code == 200 and r.json()["organization"]["status"] == "active"
    assert client.get(f"{API}/auth/me", headers=owner.headers).json()["access"]["status"] == "trial"


# --- tenant request ------------------------------------------------------------------------------


def test_request_validation_roles_and_single_open_request(client, db):
    org = _org(db, ends_in=timedelta(seconds=-1))
    owner = Member(db, org, MemberRole.OWNER)
    viewer = Member(db, org, MemberRole.VIEWER)
    finance = Member(db, org, MemberRole.FINANCE)

    assert _request(client, viewer).status_code == 403
    assert _request(client, finance).status_code == 403
    assert _request(client, owner, modules=["nope"]).status_code == 422
    assert _request(client, owner, seats=0).status_code == 422
    assert _request(client, owner, billing_cycle="weekly").status_code == 422
    assert _request(client, owner, entitlement_override=True).status_code == 422  # unknown field
    r = _request(client, owner, seats=2)  # 3 members already
    assert r.status_code == 409

    r = _request(client, owner, modules=["timesheets", "customers", "quotes", "quotes"])
    assert r.status_code == 201, r.text
    body = r.json()
    # base modules are implied (dropped); requirements added (timesheets -> projects); no duplicates
    assert body["modules"] == ["quotes", "projects", "timesheets"]
    assert body["status"] == "submitted"

    r = _request(client, owner)
    assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "SUBSCRIPTION_REQUEST_OPEN"

    state = client.get(f"{API}/subscription-requests", headers=viewer.headers).json()
    assert state["current_request"]["id"] == body["id"]
    assert state["access"]["status"] == "trial_expired"
    assert len(state["modules"]) == len(registry().modules)

    r = client.post(f"{API}/subscription-requests/{body['id']}/withdraw", headers=owner.headers)
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
    assert _request(client, owner).status_code == 201


def test_subscription_request_events_record_the_tenant_actor(client, db):
    """BUG-16: tenant-originated platform audit events name the tenant user, not "unknown"."""
    org = _org(db)
    owner = Member(db, org, MemberRole.OWNER)
    with patch(SEND, return_value=True):
        req_id = _request(client, owner).json()["id"]
        assert client.post(f"{API}/subscription-requests/{req_id}/withdraw", headers=owner.headers).status_code == 200
    for action in (platform_audit.SUBSCRIPTION_REQUEST_SUBMITTED, platform_audit.SUBSCRIPTION_REQUEST_WITHDRAWN):
        row = db.scalars(select(PlatformAuditLog).where(
            PlatformAuditLog.action == action, PlatformAuditLog.organization_id == org.id)).one()
        assert row.platform_staff_id is None
        assert row.staff_email_snapshot == owner.user.email
        assert row.staff_role_snapshot == "tenant_owner"
        assert row.details["actor_user_id"] == owner.user.id


def test_active_unrestricted_org_cannot_request(client, db, tenant, auth_headers):
    r = client.post(f"{API}/subscription-requests", json={"modules": [], "seats": 5, "billing_cycle": "monthly"},
                    headers=auth_headers)
    assert r.status_code == 409


def test_cross_tenant_request_access_is_refused(client, db):
    org_a, org_b = _org(db), _org(db)
    owner_a, owner_b = Member(db, org_a, MemberRole.OWNER), Member(db, org_b, MemberRole.OWNER)
    req_id = _request(client, owner_a).json()["id"]
    r = client.post(f"{API}/subscription-requests/{req_id}/withdraw", headers=owner_b.headers)
    assert r.status_code == 404
    state_b = client.get(f"{API}/subscription-requests", headers=owner_b.headers).json()
    assert state_b["current_request"] is None and state_b["history"] == []
    # Tenants never reach the platform queue.
    assert client.get(f"{API}/platform/subscription-requests", headers=owner_a.headers).status_code in (401, 403)


# --- platform decision ---------------------------------------------------------------------------


def test_only_administrator_with_step_up_decides(client, db):
    org = _org(db)
    owner = Member(db, org, MemberRole.OWNER)
    req_id = _request(client, owner).json()["id"]
    for role in (PlatformRole.PLATFORM_OPERATIONS, PlatformRole.PLATFORM_SUPPORT):
        staff = Staff(db, role)
        staff.step_up()
        assert staff.get("/subscription-requests").status_code == 200
        assert staff.get(f"/subscription-requests/{req_id}").status_code == 200
        assert staff.post(f"/subscription-requests/{req_id}/approve", {}).status_code == 403
        assert staff.post(f"/subscription-requests/{req_id}/reject", {"reason": "Not a fit for us now"}).status_code == 403
    fresh = Staff(db, PlatformRole.PLATFORM_ADMINISTRATOR)  # no step-up yet
    r = fresh.post(f"/subscription-requests/{req_id}/approve", {})
    assert r.status_code in (401, 403)
    db.expire_all()
    with tenant_context(org.id):
        assert db.get(SubscriptionRequest, req_id).status.value == "submitted"


def test_approval_activates_org_keeps_owner_and_grants_modules_and_seats(client, db, admin):
    org = _org(db, ends_in=timedelta(seconds=-1))
    owner = Member(db, org, MemberRole.OWNER)
    staff_before = db.scalar(select(PlatformStaff.id).where(PlatformStaff.email == owner.user.email))
    req_id = _request(client, owner, modules=["quotes", "reports"], seats=5).json()["id"]

    queue = admin.get("/subscription-requests").json()
    assert any(i["id"] == req_id and i["organization_status"] == "trial_expired" for i in queue["items"])

    with patch(SEND, return_value=True) as sent:
        r = admin.post(f"/subscription-requests/{req_id}/approve",
                       {"modules": ["quotes", "expenses"], "seats": 3, "billing_cycle": "monthly",
                        "reason": "Approved after sales call"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved" and body["approved_modules"] == ["quotes", "expenses"]
    assert body["approved_seats"] == 3 and body["approved_billing_cycle"] == "monthly"
    # Onboarding email to the Owner: a sign-in link, never a password or token.
    assert sent.call_count == 1
    args, kwargs = sent.call_args
    assert args[0] == owner.user.email
    text = args[2] + kwargs.get("html_body", "")
    assert "/login" in text and "password:" not in text.lower().replace("existing password:", "")
    assert "set up your organization's Admin account" in text
    assert "token" not in text.lower()

    db.expire_all()
    org = db.get(Organization, org.id)
    assert org.status == OrganizationStatus.ACTIVE and org.seat_limit == 3 and org.module_access == "entitled"
    with tenant_context(org.id):
        rows = db.scalars(select(OrganizationEntitlement.module_key)
                          .where(OrganizationEntitlement.organization_id == org.id)).all()
    assert sorted(rows) == ["expenses", "quotes"]
    # Owner stays the tenant Owner; no platform account is created for them.
    m = db.get(Membership, owner.membership.id)
    assert m.role == MemberRole.OWNER and m.status == MembershipStatus.ACTIVE
    assert db.scalar(select(PlatformStaff.id).where(PlatformStaff.email == owner.user.email)) == staff_before is None
    for action in (platform_audit.SUBSCRIPTION_REQUEST_APPROVED_WITH_CHANGES, platform_audit.ORGANIZATION_ONBOARDING_EMAIL):
        assert db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.organization_id == org.id,
                                                         PlatformAuditLog.action == action)).first() is not None

    # Entitlement on the API.
    assert client.get(f"{API}/customers", headers=owner.headers).status_code == 200  # base
    assert client.get(f"{API}/payments", headers=owner.headers).status_code == 200  # base
    assert client.get(f"{API}/quotes", headers=owner.headers).status_code == 200  # granted
    for path in ("/reports/dashboard", "/projects", "/payments/reconciliation/summary", "/dunning/cases", "/ai/history"):
        r = client.get(f"{API}{path}", headers=owner.headers)
        assert r.status_code == 403 and _code(r) == "FEATURE_NOT_ENTITLED", (path, r.text)
    me = client.get(f"{API}/auth/me", headers=owner.headers).json()["access"]
    assert me["status"] == "active" and set(me["modules"]) == set(registry().base_keys) | {"quotes", "expenses"}
    assert "reports" not in me["nav_items"] and "quotes" in me["nav_items"]

    # Seat limit 3: owner + 2 invitations, then refused.
    with patch("backend.app.services.organization_service.send_email", return_value=True):
        for _ in range(2):
            r = client.post(f"{API}/team/invitations", json={"email": f"x{uuid.uuid4().hex[:6]}@trial.test", "role": "viewer"},
                            headers=owner.headers)
            assert r.status_code == 201, r.text
        r = client.post(f"{API}/team/invitations", json={"email": f"x{uuid.uuid4().hex[:6]}@trial.test", "role": "viewer"},
                        headers=owner.headers)
    assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "SEAT_LIMIT_REACHED"

    # Decided requests cannot be decided again.
    assert admin.post(f"/subscription-requests/{req_id}/reject", {"reason": "Changed our mind here"}).status_code == 409


def test_approval_as_requested_is_audited_as_approved(client, db, admin):
    org = _org(db, ends_in=timedelta(seconds=-1))
    owner = Member(db, org, MemberRole.OWNER)
    req_id = _request(client, owner, modules=["quotes"], seats=4, billing_cycle="annual").json()["id"]
    with patch(SEND, return_value=True):
        r = admin.post(f"/subscription-requests/{req_id}/approve", {"reason": "Approved as requested"})
    assert r.status_code == 200 and r.json()["approved_modules"] == ["quotes"] and r.json()["approved_seats"] == 4
    actions = set(db.scalars(select(PlatformAuditLog.action).where(PlatformAuditLog.organization_id == org.id)).all())
    assert platform_audit.SUBSCRIPTION_REQUEST_APPROVED in actions
    assert platform_audit.SUBSCRIPTION_REQUEST_APPROVED_WITH_CHANGES not in actions


def test_approval_cannot_go_below_current_members(client, db, admin):
    org = _org(db)
    owner = Member(db, org, MemberRole.OWNER)
    Member(db, org, MemberRole.ADMIN)
    req_id = _request(client, owner, seats=2).json()["id"]
    r = admin.post(f"/subscription-requests/{req_id}/approve", {"seats": 1})
    assert r.status_code == 409


def test_rejection_keeps_trial_state_and_allows_a_new_request(client, db, admin):
    org = _org(db, ends_in=timedelta(seconds=-1))
    owner = Member(db, org, MemberRole.OWNER)
    req_id = _request(client, owner).json()["id"]
    assert admin.post(f"/subscription-requests/{req_id}/reject", {"reason": "short"}).status_code == 422
    with patch(SEND, return_value=True) as sent:
        r = admin.post(f"/subscription-requests/{req_id}/reject", {"reason": "Please choose annual billing"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert sent.call_count == 1
    db.expire_all()
    org = db.get(Organization, org.id)
    assert org.status == OrganizationStatus.ACTIVE and org.module_access == "trial"  # still in its (ended) trial phase
    assert client.get(f"{API}/customers", headers=owner.headers).status_code == 403
    assert _request(client, owner).status_code == 201


def test_entitlement_edit_is_administrator_only_and_respects_seats(client, db, admin):
    org = _org(db, status=OrganizationStatus.ACTIVE, module_access="entitled")
    owner = Member(db, org, MemberRole.OWNER)
    Member(db, org, MemberRole.ADMIN)
    ops = Staff(db, PlatformRole.PLATFORM_OPERATIONS)
    ops.step_up()
    path = f"/subscription-requests/organizations/{org.id}/entitlements"
    body = {"modules": ["reports"], "seat_limit": 5, "reason": "Upgrade agreed with customer"}
    assert ops.post(path, body).status_code == 403
    assert client.get(f"{API}/reports/dashboard", headers=owner.headers).status_code == 403
    r = admin.post(path, body)
    assert r.status_code == 200, r.text
    assert r.json()["modules"] == ["reports"] and r.json()["seat_limit"] == 5
    assert client.get(f"{API}/reports/dashboard", headers=owner.headers).status_code == 200
    r = admin.post(path, {**body, "seat_limit": 1})
    assert r.status_code == 409
    assert ops.get(path).json()["seats_used"] == 2


# --- backward compatibility ----------------------------------------------------------------------


def test_existing_organizations_keep_every_module(client, db, tenant, auth_headers):
    org = db.get(Organization, tenant.organization.id)
    assert org.module_access == "unrestricted" and org.seat_limit is None
    for path in ("/quotes", "/reports/dashboard", "/projects", "/expenses"):
        assert client.get(f"{API}{path}", headers=auth_headers).status_code != 403, path
    access = client.get(f"{API}/auth/me", headers=auth_headers).json()["access"]
    assert access["module_access"] == "unrestricted" and set(access["modules"]) == set(registry().all_keys)

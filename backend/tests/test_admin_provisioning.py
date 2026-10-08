"""A Platform Administrator provisions an organization's tenant Admin after its subscription is approved.

The Admin is a tenant user with one ADMIN membership (never platform staff), sets their own password
through the invitation link, sees only the approved modules, cannot reach another organization, and
can be suspended / reactivated independently of the organization. Every step is audited.
"""
import re
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from backend.app.core.tenant_context import tenant_context
from backend.app.models import Customer, Membership, MemberRole, MembershipStatus, Organization, OrganizationStatus, User
from backend.app.models.platform import PlatformAuditLog, PlatformRole, PlatformStaff
from backend.app.services import platform_audit
from backend.tests.test_platform_console import Staff
from backend.tests.test_trial_subscription_lifecycle import API, Member, _code, _org, _request

SEND = "backend.app.services.tenant_admin_provisioning.send_email"
APPROVAL_SEND = "backend.app.services.subscription_request_service.send_email"
PASSWORD = "Str0ngAdminPass!2026"


@pytest.fixture
def admin(db):
    staff = Staff(db, PlatformRole.PLATFORM_ADMINISTRATOR)
    staff.step_up()
    return staff


def _approved_org(client, db, admin, *, modules=("quotes",), seats=5):
    """Trial ended -> request -> approved: an organization ready for Admin provisioning."""
    org = _org(db, ends_in=timedelta(seconds=-1))
    owner = Member(db, org, MemberRole.OWNER)
    req_id = _request(client, owner, modules=list(modules), seats=seats).json()["id"]
    with patch(APPROVAL_SEND, return_value=True):
        assert admin.post(f"/subscription-requests/{req_id}/approve", {"reason": "Approved for QA"}).status_code == 200
    return org, owner


def _provision(admin, org_id, email, name="Acme Admin"):
    with patch(SEND, return_value=True) as sent:
        r = admin.post(f"/organizations/{org_id}/admins", {"full_name": name, "email": email})
    return r, sent


def _invite_token(sent) -> str:
    args, kwargs = sent.call_args
    return re.search(r"accept-invitation\?token=([A-Za-z0-9_\-]+)", args[2]).group(1)


def _accept(client, token, name="Acme Admin"):
    r = client.post(f"{API}/auth/accept-invitation", json={"token": token, "full_name": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _actions(db, org_id):
    return [a for (a,) in db.execute(select(PlatformAuditLog.action).where(PlatformAuditLog.organization_id == org_id))]


def test_provisioning_needs_an_approved_subscription(client, db, admin):
    trial = _org(db)  # active trial, no subscription yet
    r, sent = _provision(admin, trial.id, f"early-{uuid.uuid4().hex[:6]}@acme.test")
    assert r.status_code == 409 and "subscription" in r.json()["error"]["message"]
    assert sent.call_count == 0
    assert platform_audit.TENANT_ADMIN_PROVISIONING_INITIATED in _actions(db, trial.id)  # refused attempt audited


def test_only_administrator_with_step_up_provisions(client, db, admin):
    org, _ = _approved_org(client, db, admin)
    email = f"denied-{uuid.uuid4().hex[:6]}@acme.test"
    for role in (PlatformRole.PLATFORM_OPERATIONS, PlatformRole.PLATFORM_SUPPORT):
        staff = Staff(db, role)
        staff.step_up()
        assert staff.post(f"/organizations/{org.id}/admins", {"full_name": "Nope", "email": email}).status_code == 403
    fresh = Staff(db, PlatformRole.PLATFORM_ADMINISTRATOR)
    r = fresh.post(f"/organizations/{org.id}/admins", {"full_name": "Nope", "email": email})
    assert r.status_code == 403 and _code(r) == "STEP_UP_REQUIRED"
    assert db.scalar(select(User.id).where(User.email == email)) is None


def test_role_and_organization_cannot_be_chosen_in_the_body(client, db, admin):
    org, _ = _approved_org(client, db, admin)
    other = _org(db, status=OrganizationStatus.ACTIVE, module_access="entitled")
    for extra in ({"role": "owner"}, {"organization_id": other.id}, {"password": "Chosen-by-staff-1!"}):
        r = admin.post(f"/organizations/{org.id}/admins",
                       {"full_name": "Acme Admin", "email": f"x-{uuid.uuid4().hex[:6]}@acme.test", **extra})
        assert r.status_code == 422, extra


def test_full_provisioning_flow(client, db, admin):
    org, owner = _approved_org(client, db, admin, modules=("quotes",), seats=5)
    email = f"acme-admin-{uuid.uuid4().hex[:6]}@acme.test"
    staff_before = db.scalar(select(func.count(PlatformStaff.id)))
    r, sent = _provision(admin, org.id, email)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "admin" and body["status"] == "invited" and body["email_delivered"] is True
    assert body["organization_id"] == org.id
    assert "token" not in r.text.lower() and "password" not in r.text.lower()

    # A tenant user with exactly one ADMIN membership, in this organization only; never platform staff.
    db.expire_all()
    user = db.scalars(select(User).where(User.email == email)).one()
    assert user.hashed_password is None
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    assert [(m.organization_id, m.role, m.status) for m in memberships] == [(org.id, MemberRole.ADMIN, MembershipStatus.INVITED)]
    assert db.scalar(select(func.count(PlatformStaff.id))) == staff_before
    assert db.scalar(select(PlatformStaff.id).where(PlatformStaff.email == email)) is None
    # The signup Owner is untouched.
    assert db.get(Membership, owner.membership.id).role == MemberRole.OWNER

    # The invitation is a set-password link to the tenant app (no password in the email).
    args, kwargs = sent.call_args
    assert args[0] == email and "accept-invitation?token=" in args[2]
    headers = _accept(client, _invite_token(sent))
    db.expire_all()
    assert db.scalars(select(Membership).where(Membership.user_id == user.id)).one().status == MembershipStatus.ACTIVE

    # The Admin signs in to the tenant app with their own password.
    login = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    me = client.get(f"{API}/auth/me", headers=headers).json()
    assert me["membership"]["role"] == "admin" and me["organization"]["id"] == org.id
    assert set(me["access"]["modules"]) == {"customers", "products", "invoices", "payments", "quotes"}
    assert client.get(f"{API}/quotes", headers=headers).status_code == 200
    r = client.get(f"{API}/reports/dashboard", headers=headers)
    assert r.status_code == 403 and _code(r) == "FEATURE_NOT_ENTITLED"

    actions = _actions(db, org.id)
    for action in (platform_audit.TENANT_ADMIN_PROVISIONING_INITIATED, platform_audit.TENANT_ADMIN_PROVISIONED,
                   platform_audit.TENANT_ADMIN_INVITATION_SENT, platform_audit.TENANT_ADMIN_ACTIVATED):
        assert action in actions, action
    provisioned = db.scalars(select(PlatformAuditLog).where(
        PlatformAuditLog.organization_id == org.id, PlatformAuditLog.action == platform_audit.TENANT_ADMIN_PROVISIONED)).one()
    assert provisioned.platform_staff_id == admin.id  # the acting Administrator, from the session

    # Provisioning the same, now active, person again is refused.
    r, _ = _provision(admin, org.id, email)
    assert r.status_code == 409


def test_provisioning_respects_the_seat_limit(client, db, admin):
    org, _ = _approved_org(client, db, admin, seats=1)  # the Owner holds the only seat
    r, sent = _provision(admin, org.id, f"full-{uuid.uuid4().hex[:6]}@acme.test")
    assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "SEAT_LIMIT_REACHED"
    assert sent.call_count == 0


def test_admin_cannot_reach_another_organization(client, db, admin):
    org, _ = _approved_org(client, db, admin)
    other = _org(db, status=OrganizationStatus.ACTIVE, module_access="unrestricted")
    other_owner = Member(db, other, MemberRole.OWNER)
    created = client.post(f"{API}/customers", json={"display_name": "Other Org Customer", "email": "o@other.test",
                                                   "payment_terms_days": 15}, headers=other_owner.headers)
    assert created.status_code == 201, created.text
    r, sent = _provision(admin, org.id, f"iso-{uuid.uuid4().hex[:6]}@acme.test")
    headers = _accept(client, _invite_token(sent))
    assert client.get(f"{API}/customers/{created.json()['id']}", headers=headers).status_code == 404
    assert "Other Org Customer" not in client.get(f"{API}/customers", headers=headers).text
    switched = client.post(f"{API}/auth/switch-organization", json={"organization_id": other.id}, headers=headers)
    assert switched.status_code in (401, 403, 404)

    # organization_id in a body is ignored: the record lands in the Admin's own organization.
    mine = client.post(f"{API}/customers", json={"display_name": "Mine", "email": "m@acme.test", "payment_terms_days": 15,
                                                "organization_id": other.id}, headers=headers)
    assert mine.status_code in (201, 422)
    if mine.status_code == 201:
        with tenant_context(org.id):
            row = db.get(Customer, mine.json()["id"])
        assert row is not None and row.organization_id == org.id


def test_admin_and_organization_suspension(client, db, admin):
    org, _ = _approved_org(client, db, admin)
    email = f"susp-{uuid.uuid4().hex[:6]}@acme.test"
    r, sent = _provision(admin, org.id, email)
    headers = _accept(client, _invite_token(sent))
    user_id = r.json()["user_id"]
    assert client.get(f"{API}/quotes", headers=headers).status_code == 200

    # Organization suspended: existing policy - Admin keeps read-only access, every write is refused.
    s = admin.post(f"/organizations/{org.id}/suspend", {"reason": "Billing dispute review", "ticket_ref": "SUP-7"})
    assert s.status_code == 200
    w = client.post(f"{API}/customers", json={"display_name": "x", "email": "x@acme.test", "payment_terms_days": 15},
                    headers=headers)
    assert w.status_code == 403 and _code(w) == "ORGANIZATION_SUSPENDED"
    assert admin.post(f"/organizations/{org.id}/reactivate", {"reason": "Dispute resolved now"}).status_code == 200
    login = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    w = client.post(f"{API}/customers", json={"display_name": "After reactivation", "email": "y@acme.test",
                                             "payment_terms_days": 15}, headers=headers)
    assert w.status_code == 201, w.text

    # The Admin alone suspended: sessions revoked, cannot sign in; reactivation restores access.
    d = admin.post(f"/organizations/{org.id}/admins/{user_id}/deactivate", {"reason": "Left the company"})
    assert d.status_code == 200, d.text
    assert client.get(f"{API}/quotes", headers=headers).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code in (401, 403)
    a = admin.post(f"/organizations/{org.id}/admins/{user_id}/reactivate", {"reason": "Rejoined the company"})
    assert a.status_code == 200, a.text
    assert client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    actions = _actions(db, org.id)
    for action in (platform_audit.ORGANIZATION_SUSPENDED, platform_audit.ORGANIZATION_REACTIVATED,
                   platform_audit.TENANT_ADMIN_DEACTIVATED, platform_audit.TENANT_ADMIN_REACTIVATED):
        assert action in actions, action


def test_tenant_cannot_forge_audit_actor_or_organization(client, db, admin):
    org = _org(db, ends_in=timedelta(seconds=-1))
    owner = Member(db, org, MemberRole.OWNER)
    other = _org(db)
    for extra in ({"requested_by_user_id": str(uuid.uuid4())}, {"organization_id": other.id}):
        r = _request(client, owner, **extra)
        assert r.status_code == 422, extra
    assert client.post(f"{API}/audit-logs", json={"action": "FAKE"}, headers=owner.headers).status_code in (404, 405)
    r = client.get(f"{API}/platform/audit", headers=owner.headers)
    assert r.status_code in (401, 403)
    assert db.scalar(select(func.count(Organization.id)).where(Organization.id == other.id)) == 1

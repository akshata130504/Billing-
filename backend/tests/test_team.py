"""Organization settings and team management: invitations, roles, deactivation, guards."""
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from backend.app.core.exceptions import InvalidStateError
from backend.app.core.security import decode_access_token
from backend.app.models import AuditLog, Membership, MemberRole, MembershipStatus, RefreshToken, User
from backend.app.services import organization_service
from backend.app.services.auth_service import make_ctx

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd!"


def unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password=PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def invite(client, headers, email, role="viewer", **extra):
    return client.post(f"{API}/team/invitations", json={"email": email, "role": role, **extra}, headers=headers)


def token_of(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


def audit_rows(db, action: str, entity_id: str | None = None):
    db.expire_all()
    stmt = select(AuditLog).where(AuditLog.action == action)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    return list(db.scalars(stmt.order_by(AuditLog.created_at)).all())


def membership_of(db, org_id, user_id) -> Membership:
    db.expire_all()
    return db.scalars(select(Membership).where(Membership.organization_id == org_id, Membership.user_id == user_id)).one()


# --- organization ----------------------------------------------------------------------------


def test_get_organization_for_any_role(client, tenant):
    r = client.get(f"{API}/organization", headers=tenant.headers_for_role(MemberRole.VIEWER))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == tenant.organization.id and data["slug"] == tenant.organization.slug
    assert data["country"] == "IN" and data["default_currency"] == "INR"
    assert data["default_tax_rate_pct"] == "18.00" and data["discount_approval_threshold_pct"] == "20.00"
    assert data["invoice_next_number"] == 1 and data["invoice_prefix"] == "INV-"
    assert data["updated_at"].endswith("Z")
    assert client.get(f"{API}/organization").status_code == 401


def test_patch_organization_requires_admin(client, tenant):
    for role in (MemberRole.VIEWER, MemberRole.FINANCE):
        r = client.patch(f"{API}/organization", json={"name": "Nope"}, headers=tenant.headers_for_role(role))
        assert r.status_code == 403, role
        assert r.json()["error"]["code"] == "FORBIDDEN"
    r = client.patch(f"{API}/organization", json={"legal_name": "Admin Set Ltd"}, headers=tenant.headers_for_role(MemberRole.ADMIN))
    assert r.status_code == 200 and r.json()["legal_name"] == "Admin Set Ltd"


def test_patch_organization_updates_and_audits_changed_fields_only(client, db, tenant, auth_headers):
    original_name = tenant.organization.name
    body = {
        "name": "Renamed Org",
        "gstin": "29abcde1234f1z5",
        "pan": "abcde1234f",
        "country": "in",
        "default_currency": "inr",
        "default_tax_rate_pct": "12.5",
        "invoice_next_number": 100,
        "invoice_prefix": "RB-",
        "address_line1": "  1 Main Street ",
        "legal_name": "",
    }
    r = client.patch(f"{API}/organization", json=body, headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "Renamed Org"
    assert data["gstin"] == "29ABCDE1234F1Z5" and data["pan"] == "ABCDE1234F"
    assert data["country"] == "IN" and data["default_currency"] == "INR"
    assert data["default_tax_rate_pct"] == "12.50"
    assert data["invoice_next_number"] == 100 and data["invoice_prefix"] == "RB-"
    assert data["address_line1"] == "1 Main Street" and data["legal_name"] is None
    assert data["slug"] == tenant.organization.slug  # slug is immutable

    rows = audit_rows(db, "ORGANIZATION_UPDATED", tenant.organization.id)
    assert len(rows) == 1
    row = rows[0]
    # country/currency/legal_name were unchanged after normalisation and must not appear
    assert set(row.after_state) == {"name", "gstin", "pan", "default_tax_rate_pct", "invoice_next_number", "invoice_prefix", "address_line1"}
    assert row.before_state["name"] == original_name and row.after_state["name"] == "Renamed Org"
    assert row.before_state["invoice_next_number"] == 1 and row.after_state["invoice_next_number"] == 100
    assert row.after_state["default_tax_rate_pct"] == "12.50"
    assert row.actor_user_id == tenant.owner.id

    # a no-op patch does not write another audit row
    r = client.patch(f"{API}/organization", json={"name": "Renamed Org"}, headers=auth_headers)
    assert r.status_code == 200
    assert len(audit_rows(db, "ORGANIZATION_UPDATED", tenant.organization.id)) == 1


@pytest.mark.parametrize(
    "body,field",
    [
        ({"country": "india"}, "country"),
        ({"country": "1n"}, "country"),
        ({"default_currency": "rupees"}, "default_currency"),
        ({"gstin": "TOO-SHORT"}, "gstin"),
        ({"pan": "1234567890"}, "pan"),
        ({"default_tax_rate_pct": "150"}, "default_tax_rate_pct"),
        ({"discount_approval_threshold_pct": "-1"}, "discount_approval_threshold_pct"),
        ({"default_payment_terms_days": -5}, "default_payment_terms_days"),
        ({"invoice_prefix": ""}, "invoice_prefix"),
        ({"name": None}, "name"),
        ({"timezone": "Mars/Olympus_Mons"}, "timezone"),
        ({"email": "not-an-email"}, "email"),
    ],
)
def test_patch_organization_validation(client, auth_headers, body, field):
    r = client.patch(f"{API}/organization", json=body, headers=auth_headers)
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert field in err["details"]["fields"]


def test_patch_organization_rejects_unknown_and_readonly_fields(client, auth_headers):
    for body in ({"slug": "new-slug"}, {"id": "x"}, {"created_at": "2020-01-01T00:00:00Z"}, {"bogus": 1}):
        r = client.patch(f"{API}/organization", json=body, headers=auth_headers)
        assert r.status_code == 422, body
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_next_numbers_cannot_decrease(client, auth_headers):
    ok = client.patch(f"{API}/organization", json={"quote_next_number": 50, "customer_next_number": 7}, headers=auth_headers)
    assert ok.status_code == 200 and ok.json()["quote_next_number"] == 50
    same = client.patch(f"{API}/organization", json={"quote_next_number": 50}, headers=auth_headers)
    assert same.status_code == 200
    lower = client.patch(f"{API}/organization", json={"quote_next_number": 49, "customer_next_number": 8}, headers=auth_headers)
    assert lower.status_code == 422
    fields = lower.json()["error"]["details"]["fields"]
    assert "quote_next_number" in fields and "customer_next_number" not in fields
    # nothing was applied from the rejected patch
    assert client.get(f"{API}/organization", headers=auth_headers).json()["customer_next_number"] == 7


# --- team listing -----------------------------------------------------------------------------


def test_list_team(client, db, tenant):
    finance = tenant.add_member("fin", MemberRole.FINANCE)
    db.commit()
    r = client.get(f"{API}/team", headers=tenant.headers_for_role(MemberRole.VIEWER))
    assert r.status_code == 200, r.text
    members = r.json()
    by_email = {m["user"]["email"]: m for m in members}
    assert by_email[tenant.owner.email]["role"] == "owner"
    assert by_email[finance.email]["role"] == "finance" and by_email[finance.email]["status"] == "active"
    entry = by_email[finance.email]
    assert set(entry) == {"id", "user", "role", "status", "invited_by", "invite_expires_at", "accepted_at", "created_at"}
    assert set(entry["user"]) == {"id", "full_name", "email"}
    assert entry["invited_by"] is None
    assert "hashed_password" not in r.text
    assert client.get(f"{API}/team").status_code == 401


# --- invitations -------------------------------------------------------------------------------


def test_invite_new_user_and_accept(client, db, tenant, auth_headers):
    email = f"{unique('newbie')}@example.test"
    r = invite(client, auth_headers, email.upper(), role="finance")
    assert r.status_code == 201, r.text
    invited = r.json()
    assert invited["status"] == "invited" and invited["role"] == "finance"
    assert invited["user"]["email"] == email and invited["user"]["full_name"] == email.split("@")[0]
    assert invited["invited_by"]["id"] == tenant.owner.id
    assert invited["invite_expires_at"] and invited["accepted_at"] is None
    assert invited["invite_url"].startswith("http") and "accept-invitation?token=" in invited["invite_url"]
    token = token_of(invited["invite_url"])
    assert token not in r.text.replace(invited["invite_url"], "")  # raw token appears only inside the URL

    db.expire_all()
    user = db.scalars(select(User).where(User.email == email)).one()
    assert user.hashed_password is None
    membership = membership_of(db, tenant.organization.id, user.id)
    assert membership.invite_token_hash and membership.invite_token_hash != token
    assert audit_rows(db, "TEAM_MEMBER_INVITED", membership.id)

    # public preview
    preview = client.get(f"{API}/auth/invitations/{token}")
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        "email": email,
        "organization_name": tenant.organization.name,
        "role": "finance",
        "invited_by": tenant.owner.full_name,
        "expires_at": preview.json()["expires_at"],
        "user_exists": False,
    }
    assert client.get(f"{API}/auth/invitations/not-a-token").status_code == 404
    assert client.get(f"{API}/auth/invitations/not-a-token").json()["error"]["code"] == "ENTITY_NOT_FOUND"

    # a brand-new user must supply a name and a strong password
    missing = client.post(f"{API}/auth/accept-invitation", json={"token": token})
    assert missing.status_code == 422
    assert set(missing.json()["error"]["details"]["fields"]) == {"full_name", "password"}
    weak = client.post(f"{API}/auth/accept-invitation", json={"token": token, "full_name": "New Bie", "password": "weak"})
    assert weak.status_code == 422 and "password" in weak.json()["error"]["details"]["fields"]

    accepted = client.post(f"{API}/auth/accept-invitation", json={"token": token, "full_name": "New Bie", "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    tokens = accepted.json()
    claims = decode_access_token(tokens["access_token"])
    assert claims["org"] == tenant.organization.id and claims["role"] == "finance"

    me = client.get(f"{API}/auth/me", headers=bearer(tokens["access_token"])).json()
    assert me["user"]["full_name"] == "New Bie" and me["membership"]["role"] == "finance"
    assert me["membership"]["status"] == "active" and me["membership"]["joined_at"]

    # token is single use, invitee can log in with the chosen password
    assert client.get(f"{API}/auth/invitations/{token}").status_code == 404
    assert client.post(f"{API}/auth/accept-invitation", json={"token": token}).status_code == 404
    assert login(client, email).status_code == 200

    membership = membership_of(db, tenant.organization.id, user.id)
    assert membership.status == MembershipStatus.ACTIVE and membership.invite_token_hash is None and membership.accepted_at
    assert audit_rows(db, "INVITATION_ACCEPTED", membership.id)

    listed = {m["user"]["email"]: m for m in client.get(f"{API}/team", headers=auth_headers).json()}
    assert listed[email]["status"] == "active" and listed[email]["invited_by"]["email"] == tenant.owner.email


def test_invite_existing_user_only_needs_the_token(client, db, tenant, auth_headers):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    existing = other.owner  # already has a password in another organization

    r = invite(client, auth_headers, existing.email, role="admin", full_name="Ignored Name")
    assert r.status_code == 201, r.text
    token = token_of(r.json()["invite_url"])
    preview = client.get(f"{API}/auth/invitations/{token}").json()
    assert preview["user_exists"] is True and preview["role"] == "admin"

    accepted = client.post(f"{API}/auth/accept-invitation", json={"token": token})
    assert accepted.status_code == 200, accepted.text
    me = client.get(f"{API}/auth/me", headers=bearer(accepted.json()["access_token"])).json()
    assert me["organization"]["id"] == tenant.organization.id and me["membership"]["role"] == "admin"
    assert me["user"]["full_name"] == existing.full_name  # untouched
    assert {o["id"] for o in me["organizations"]} == {tenant.organization.id, other.organization.id}

    # login picks the newest membership and switch-organization gets back to the original
    logged = login(client, existing.email).json()
    assert decode_access_token(logged["access_token"])["org"] == tenant.organization.id
    switched = client.post(
        f"{API}/auth/switch-organization",
        json={"organization_id": other.organization.id},
        headers=bearer(logged["access_token"]),
    )
    assert switched.status_code == 200 and decode_access_token(switched.json()["access_token"])["org"] == other.organization.id


def test_reinvite_regenerates_token_and_updates_role(client, db, tenant, auth_headers):
    email = f"{unique('again')}@example.test"
    first = invite(client, auth_headers, email, role="viewer").json()
    second = invite(client, auth_headers, email, role="finance")
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first["id"] and second.json()["role"] == "finance"
    assert client.get(f"{API}/auth/invitations/{token_of(first['invite_url'])}").status_code == 404
    assert client.get(f"{API}/auth/invitations/{token_of(second.json()['invite_url'])}").status_code == 200
    assert len(client.get(f"{API}/team", headers=auth_headers).json()) == 2


def test_invite_active_member_conflicts(client, db, tenant, auth_headers):
    finance = tenant.add_member("dupmember", MemberRole.FINANCE)
    db.commit()
    r = invite(client, auth_headers, finance.email)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"
    r = invite(client, auth_headers, tenant.owner.email)
    assert r.status_code == 409


def test_invite_role_guards(client, db, tenant):
    finance_headers = tenant.headers_for_role(MemberRole.FINANCE)
    r = invite(client, finance_headers, f"{unique('x')}@example.test")
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert invite(client, tenant.headers_for_role(MemberRole.VIEWER), f"{unique('x')}@example.test").status_code == 403

    admin_headers = tenant.headers_for_role(MemberRole.ADMIN)
    assert invite(client, admin_headers, f"{unique('x')}@example.test", role="admin").status_code == 201
    denied = invite(client, admin_headers, f"{unique('x')}@example.test", role="owner")
    assert denied.status_code == 403
    assert invite(client, tenant.headers(), f"{unique('x')}@example.test", role="owner").status_code == 201


def test_invite_validation(client, auth_headers):
    r = invite(client, auth_headers, "bad-email")
    assert r.status_code == 422 and "email" in r.json()["error"]["details"]["fields"]
    r = invite(client, auth_headers, f"{unique('x')}@example.test", role="superuser")
    assert r.status_code == 422 and "role" in r.json()["error"]["details"]["fields"]


def test_expired_invitation_is_not_found(client, db, tenant, auth_headers):
    from datetime import datetime, timedelta, timezone

    email = f"{unique('late')}@example.test"
    invited = invite(client, auth_headers, email).json()
    token = token_of(invited["invite_url"])
    membership = db.get(Membership, invited["id"])
    membership.invite_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    assert client.get(f"{API}/auth/invitations/{token}").status_code == 404
    assert client.post(f"{API}/auth/accept-invitation", json={"token": token, "full_name": "Late", "password": PASSWORD}).status_code == 404


# --- role changes --------------------------------------------------------------------------------


def test_change_role_and_audit(client, db, tenant, auth_headers):
    member = tenant.add_member("promote", MemberRole.VIEWER)
    db.commit()
    membership = membership_of(db, tenant.organization.id, member.id)

    r = client.patch(f"{API}/team/{membership.id}", json={"role": "admin"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin" and r.json()["user"]["id"] == member.id
    rows = audit_rows(db, "TEAM_ROLE_CHANGED", membership.id)
    assert rows and rows[0].before_state == {"role": "viewer"} and rows[0].after_state == {"role": "admin"}

    # same role again is a no-op without a second audit row
    assert client.patch(f"{API}/team/{membership.id}", json={"role": "admin"}, headers=auth_headers).status_code == 200
    assert len(audit_rows(db, "TEAM_ROLE_CHANGED", membership.id)) == 1

    assert client.patch(f"{API}/team/{uuid.uuid4()}", json={"role": "admin"}, headers=auth_headers).status_code == 404
    assert client.patch(f"{API}/team/{membership.id}", json={"role": "boss"}, headers=auth_headers).status_code == 422


def test_role_change_guards(client, db, tenant, auth_headers):
    admin = tenant.add_member("adm", MemberRole.ADMIN)
    viewer = tenant.add_member("view", MemberRole.VIEWER)
    finance = tenant.add_member("finuser", MemberRole.FINANCE)
    db.commit()
    admin_headers = tenant.headers(admin, MemberRole.ADMIN)
    owner_membership = membership_of(db, tenant.organization.id, tenant.owner.id)
    admin_membership = membership_of(db, tenant.organization.id, admin.id)
    viewer_membership = membership_of(db, tenant.organization.id, viewer.id)
    finance_membership = membership_of(db, tenant.organization.id, finance.id)

    # cannot change your own role
    assert client.patch(f"{API}/team/{owner_membership.id}", json={"role": "admin"}, headers=auth_headers).status_code == 403
    assert client.patch(f"{API}/team/{admin_membership.id}", json={"role": "owner"}, headers=admin_headers).status_code == 403
    # admins may manage non-owner roles but never grant or revoke owner
    assert client.patch(f"{API}/team/{viewer_membership.id}", json={"role": "finance"}, headers=admin_headers).status_code == 200
    assert client.patch(f"{API}/team/{viewer_membership.id}", json={"role": "owner"}, headers=admin_headers).status_code == 403
    assert client.patch(f"{API}/team/{owner_membership.id}", json={"role": "viewer"}, headers=admin_headers).status_code == 403
    # finance/viewer cannot touch the team at all
    assert client.patch(f"{API}/team/{viewer_membership.id}", json={"role": "viewer"}, headers=tenant.headers(finance, MemberRole.FINANCE)).status_code == 403
    # owners can promote to owner and demote another owner while one remains
    assert client.patch(f"{API}/team/{finance_membership.id}", json={"role": "owner"}, headers=auth_headers).status_code == 200
    assert client.patch(f"{API}/team/{finance_membership.id}", json={"role": "finance"}, headers=auth_headers).status_code == 200
    # the last active owner cannot be demoted or removed by anyone (self is forbidden, others lack the role)
    assert client.delete(f"{API}/team/{owner_membership.id}", headers=auth_headers).status_code == 403
    assert client.delete(f"{API}/team/{owner_membership.id}", headers=admin_headers).status_code == 403


def test_last_owner_protection_in_service(db, tenant):
    """An owner whose own membership is not active still cannot remove the last active owner."""
    dormant = tenant.add_member("dormant-owner", MemberRole.OWNER)
    db.commit()
    dormant_membership = membership_of(db, tenant.organization.id, dormant.id)
    dormant_membership.status = MembershipStatus.INVITED
    db.commit()
    ctx = make_ctx(dormant, tenant.organization, dormant_membership, None, None)
    only_owner = membership_of(db, tenant.organization.id, tenant.owner.id)
    with pytest.raises(InvalidStateError):
        organization_service.deactivate_member(db, ctx, only_owner.id)
    with pytest.raises(InvalidStateError):
        organization_service.change_role(db, ctx, only_owner.id, MemberRole.ADMIN)
    db.rollback()
    assert membership_of(db, tenant.organization.id, tenant.owner.id).status == MembershipStatus.ACTIVE


# --- deactivation --------------------------------------------------------------------------------


def test_deactivate_member_revokes_sessions_and_audits(client, db, tenant, auth_headers):
    member = tenant.add_member("leaver", MemberRole.FINANCE)
    db.commit()
    session = login(client, member.email).json()
    assert client.get(f"{API}/auth/me", headers=bearer(session["access_token"])).status_code == 200
    membership = membership_of(db, tenant.organization.id, member.id)

    r = client.delete(f"{API}/team/{membership.id}", headers=auth_headers)
    assert r.status_code == 204, r.text

    db.expire_all()
    membership = membership_of(db, tenant.organization.id, member.id)
    assert membership.status == MembershipStatus.DEACTIVATED and membership.deactivated_at is not None
    live = db.scalars(select(RefreshToken).where(RefreshToken.user_id == member.id, RefreshToken.revoked_at.is_(None))).all()
    assert live == []
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": session["refresh_token"]}).status_code == 401
    assert client.get(f"{API}/auth/me", headers=bearer(session["access_token"])).status_code == 401
    assert login(client, member.email).status_code == 401  # no active membership left

    rows = audit_rows(db, "TEAM_MEMBER_DEACTIVATED", membership.id)
    assert rows and rows[0].before_state["status"] == "active" and rows[0].after_state["status"] == "deactivated"

    listed = {m["user"]["email"]: m for m in client.get(f"{API}/team", headers=auth_headers).json()}
    assert listed[member.email]["status"] == "deactivated"

    again = client.delete(f"{API}/team/{membership.id}", headers=auth_headers)
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVALID_STATE"
    assert client.delete(f"{API}/team/{uuid.uuid4()}", headers=auth_headers).status_code == 404


def test_deactivate_only_revokes_tokens_for_this_organization(client, db, tenant, auth_headers):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    shared = other.owner
    db.add(Membership(organization_id=tenant.organization.id, user_id=shared.id, role=MemberRole.VIEWER, status=MembershipStatus.ACTIVE))
    db.commit()

    # a session for the other organization must survive
    other_session = login(client, shared.email).json()  # picks the newest membership (tenant)
    switched = client.post(
        f"{API}/auth/switch-organization", json={"organization_id": other.organization.id}, headers=bearer(other_session["access_token"])
    ).json()

    membership = membership_of(db, tenant.organization.id, shared.id)
    assert client.delete(f"{API}/team/{membership.id}", headers=auth_headers).status_code == 204
    # the session for the other organization survives; the deactivated one is gone
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": switched["refresh_token"]}).status_code == 200
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": other_session["refresh_token"]}).status_code == 401


def test_deactivate_guards(client, db, tenant, auth_headers):
    admin = tenant.add_member("adm2", MemberRole.ADMIN)
    second_owner = tenant.add_member("owner2", MemberRole.OWNER)
    viewer = tenant.add_member("view2", MemberRole.VIEWER)
    db.commit()
    admin_headers = tenant.headers(admin, MemberRole.ADMIN)
    admin_membership = membership_of(db, tenant.organization.id, admin.id)
    owner2_membership = membership_of(db, tenant.organization.id, second_owner.id)
    viewer_membership = membership_of(db, tenant.organization.id, viewer.id)

    assert client.delete(f"{API}/team/{admin_membership.id}", headers=admin_headers).status_code == 403  # self
    assert client.delete(f"{API}/team/{owner2_membership.id}", headers=admin_headers).status_code == 403  # admin vs owner
    assert client.delete(f"{API}/team/{viewer_membership.id}", headers=tenant.headers_for_role(MemberRole.FINANCE)).status_code == 403
    assert client.delete(f"{API}/team/{viewer_membership.id}", headers=admin_headers).status_code == 204
    assert client.delete(f"{API}/team/{owner2_membership.id}", headers=auth_headers).status_code == 204  # owner removes other owner


def test_reinvite_deactivated_member_reactivates_on_accept(client, db, tenant, auth_headers):
    member = tenant.add_member("comeback", MemberRole.FINANCE)
    db.commit()
    membership = membership_of(db, tenant.organization.id, member.id)
    assert client.delete(f"{API}/team/{membership.id}", headers=auth_headers).status_code == 204

    r = invite(client, auth_headers, member.email, role="viewer")
    assert r.status_code == 201, r.text
    assert r.json()["id"] == membership.id and r.json()["status"] == "invited" and r.json()["role"] == "viewer"
    rows = audit_rows(db, "TEAM_MEMBER_INVITED", membership.id)
    assert rows[-1].before_state == {"status": "deactivated"}

    token = token_of(r.json()["invite_url"])
    assert client.get(f"{API}/auth/invitations/{token}").json()["user_exists"] is True
    accepted = client.post(f"{API}/auth/accept-invitation", json={"token": token})
    assert accepted.status_code == 200, accepted.text
    me = client.get(f"{API}/auth/me", headers=bearer(accepted.json()["access_token"])).json()
    assert me["membership"]["role"] == "viewer" and me["membership"]["status"] == "active"
    assert login(client, member.email).status_code == 200

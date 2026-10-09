"""Organization lifecycle access policy (docs/platform-administration-design.md section 8).

Tenant staff API:
- suspended: Owner and Admin read-only; Finance and Viewer refused; every write refused.
- pending deletion: Owner read-only; everyone else refused.
- rejected: business endpoints refused, /auth/me still works.
Customer-facing pages:
- suspended: public invoice viewable but no new Razorpay orders; quotes cannot be accepted or
  declined; customer portal read-only.
- pending deletion / deleted / rejected: customer portal and public invoice
  and quote links refused (invalid link).
Reactivation restores normal access; other organizations are never affected.
(Scheduler skipping and webhooks-still-recorded are covered in test_scheduler_org_lifecycle.py.)
"""
import uuid

import pytest

from backend.app.core.security import hash_password
from backend.app.core.tenant_context import system_context
from backend.app.models import MemberRole, Organization, OrganizationStatus
from backend.app.models.portal import CustomerPortalUser

API = "/api/v1"


def _set_status(db, org_id: str, status: OrganizationStatus, reason: str | None = None) -> None:
    with system_context():
        org = db.get(Organization, org_id)
        org.status = status
        org.status_reason = reason
        db.commit()


def _headers(tenant, db, role: MemberRole) -> dict:
    if role == MemberRole.OWNER:
        return tenant.headers()
    return tenant.headers_for_role(role)


def _customer_body() -> dict:
    return {"display_name": f"Acme {uuid.uuid4().hex[:6]}", "email": f"c-{uuid.uuid4().hex[:6]}@example.test"}


def _code(resp) -> str:
    return resp.json()["error"]["code"]


@pytest.mark.parametrize("role", [MemberRole.OWNER, MemberRole.ADMIN])
def test_suspended_owner_and_admin_are_read_only(client, db, tenant, role):
    headers = _headers(tenant, db, role)
    tenant.customer()
    _set_status(db, tenant.organization.id, OrganizationStatus.SUSPENDED, "Unpaid platform fees")

    assert client.get(f"{API}/customers", headers=headers).status_code == 200
    assert client.get(f"{API}/invoices", headers=headers).status_code == 200

    write = client.post(f"{API}/customers", headers=headers, json=_customer_body())
    assert write.status_code == 403
    assert _code(write) == "ORGANIZATION_SUSPENDED"
    assert "read-only" in write.json()["error"]["message"]


@pytest.mark.parametrize("role", [MemberRole.FINANCE, MemberRole.VIEWER])
def test_suspended_finance_and_viewer_are_refused(client, db, tenant, role):
    headers = _headers(tenant, db, role)
    _set_status(db, tenant.organization.id, OrganizationStatus.SUSPENDED)

    resp = client.get(f"{API}/customers", headers=headers)
    assert resp.status_code == 403
    assert _code(resp) == "ORGANIZATION_SUSPENDED"


def test_suspended_users_can_still_use_auth_me(client, db, tenant):
    viewer = _headers(tenant, db, MemberRole.VIEWER)
    _set_status(db, tenant.organization.id, OrganizationStatus.SUSPENDED)
    for headers in (tenant.headers(), viewer):
        me = client.get(f"{API}/auth/me", headers=headers)
        assert me.status_code == 200, me.text
        assert me.json()["organization"]["status"] == "suspended"


def test_pending_deletion_owner_read_only_everyone_else_refused(client, db, tenant):
    admin = _headers(tenant, db, MemberRole.ADMIN)
    _set_status(db, tenant.organization.id, OrganizationStatus.PENDING_DELETION)

    assert client.get(f"{API}/customers", headers=tenant.headers()).status_code == 200
    write = client.post(f"{API}/customers", headers=tenant.headers(), json=_customer_body())
    assert write.status_code == 403
    assert _code(write) == "ORGANIZATION_PENDING_DELETION"
    assert client.get(f"{API}/customers", headers=admin).status_code == 403


@pytest.mark.parametrize(
    "status,code",
    [
        (OrganizationStatus.REJECTED, "ORGANIZATION_REJECTED"),
        (OrganizationStatus.DELETED, "ORGANIZATION_DELETED"),
    ],
)
def test_non_operational_orgs_refuse_owner_reads_and_writes(client, db, tenant, status, code):
    _set_status(db, tenant.organization.id, status, "Incomplete KYC")
    read = client.get(f"{API}/customers", headers=tenant.headers())
    assert read.status_code == 403
    assert _code(read) == code
    assert client.post(f"{API}/customers", headers=tenant.headers(), json=_customer_body()).status_code == 403


def test_rejected_reason_is_shown_to_the_tenant(client, db, tenant):
    _set_status(db, tenant.organization.id, OrganizationStatus.REJECTED, "Incomplete KYC")
    resp = client.get(f"{API}/customers", headers=tenant.headers())
    assert "Incomplete KYC" in resp.json()["error"]["message"]
    me = client.get(f"{API}/auth/me", headers=tenant.headers())
    assert me.status_code == 200
    assert me.json()["organization"]["status"] == "rejected"


def test_reactivation_restores_writes(client, db, tenant):
    _set_status(db, tenant.organization.id, OrganizationStatus.SUSPENDED)
    assert client.post(f"{API}/customers", headers=tenant.headers(), json=_customer_body()).status_code == 403
    _set_status(db, tenant.organization.id, OrganizationStatus.ACTIVE)
    assert client.post(f"{API}/customers", headers=tenant.headers(), json=_customer_body()).status_code == 201


def test_other_active_organizations_are_unaffected(client, db, tenant):
    from backend.tests.conftest import Tenant

    with system_context():
        other = Tenant(db, uuid.uuid4().hex[:8])
    _set_status(db, tenant.organization.id, OrganizationStatus.SUSPENDED)
    assert client.post(f"{API}/customers", headers=other.headers(), json=_customer_body()).status_code == 201
    assert client.get(f"{API}/customers", headers=other.headers()).status_code == 200


# --- customer-facing pages --------------------------------------------------------------------------


def _sent_invoice_token(client, tenant) -> str:
    customer = tenant.customer()
    res = client.post(
        f"{API}/invoices",
        headers=tenant.headers(),
        json={"customer_id": customer.id, "items": [{"description": "Item", "quantity": "1", "unit_price": "500.00", "tax_rate_pct": "0"}]},
    )
    assert res.status_code == 201, res.text
    inv_id = res.json()["id"]
    sent = client.post(f"{API}/invoices/{inv_id}/send", headers=tenant.headers())
    assert sent.status_code == 200, sent.text
    from backend.app.models import Invoice

    with system_context():
        return tenant.db.get(Invoice, inv_id).public_token


def test_suspended_public_invoice_viewable_but_no_new_payment(client, db, tenant):
    token = _sent_invoice_token(client, tenant)
    _set_status(db, tenant.organization.id, OrganizationStatus.SUSPENDED)

    view = client.get(f"{API}/public/invoices/{token}")
    assert view.status_code == 200, view.text
    assert view.json()["razorpay"]["enabled"] is False
    assert view.json()["razorpay"]["unavailable_reason"]

    order = client.post(f"{API}/public/invoices/{token}/razorpay-order", json={})
    assert order.status_code == 403
    assert _code(order) == "ORGANIZATION_UNAVAILABLE"


def test_active_public_invoice_has_no_unavailable_reason(client, db, tenant):
    token = _sent_invoice_token(client, tenant)
    view = client.get(f"{API}/public/invoices/{token}")
    assert view.status_code == 200
    assert view.json()["razorpay"].get("unavailable_reason") is None


def test_suspended_quote_cannot_be_accepted_or_declined(client, db, tenant):
    customer = tenant.customer()
    created = client.post(
        f"{API}/quotes",
        headers=tenant.headers(),
        json={"customer_id": customer.id, "title": "Rollout", "items": [{"description": "Impl", "quantity": "1", "unit_price": "1000.00", "tax_rate_pct": "18"}]},
    )
    assert created.status_code == 201, created.text
    sent = client.post(f"{API}/quotes/{created.json()['id']}/send", headers=tenant.headers())
    assert sent.status_code == 200, sent.text
    token = sent.json()["public_url"].rsplit("/", 1)[1]
    _set_status(db, tenant.organization.id, OrganizationStatus.SUSPENDED)

    view = client.get(f"{API}/public/quotes/{token}")
    assert view.status_code == 200
    assert view.json()["actions_unavailable_reason"]
    accept = client.post(f"{API}/public/quotes/{token}/accept", json={"accepted_by_name": "Jane Buyer"})
    assert accept.status_code == 403
    assert _code(accept) == "ORGANIZATION_UNAVAILABLE"
    assert client.post(f"{API}/public/quotes/{token}/decline", json={}).status_code == 403

    _set_status(db, tenant.organization.id, OrganizationStatus.ACTIVE)
    assert client.get(f"{API}/public/quotes/{token}").json()["actions_unavailable_reason"] is None
    assert client.post(f"{API}/public/quotes/{token}/accept", json={"accepted_by_name": "Jane Buyer"}).status_code == 200


def _portal_token(client, db, tenant) -> str:
    email = f"portal-{uuid.uuid4().hex[:6]}@example.com"
    customer = tenant.customer(email=email)
    with system_context():
        db.add(
            CustomerPortalUser(
                organization_id=tenant.organization.id,
                customer_id=customer.id,
                email=email,
                password_hash=hash_password("SecurePassword123!"),
                display_name="Portal User",
                is_active=True,
            )
        )
        db.commit()
    login = client.post(
        f"{API}/portal/auth/login",
        json={"organization_id": tenant.organization.id, "email": email, "password": "SecurePassword123!"},
    )
    assert login.status_code == 200, login.text
    return login.json()["token"]


def test_suspended_portal_is_read_only(client, db, tenant):
    token = _portal_token(client, db, tenant)
    headers = {"X-Portal-Token": token}
    _set_status(db, tenant.organization.id, OrganizationStatus.SUSPENDED)

    dashboard = client.get(f"{API}/portal/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["read_only_reason"]
    assert client.get(f"{API}/portal/invoices", headers=headers).status_code == 200
    profile = client.patch(f"{API}/portal/profile", headers=headers, json={"display_name": "New Name"})
    assert profile.status_code == 403
    assert _code(profile) == "ORGANIZATION_UNAVAILABLE"


def test_pending_deletion_portal_is_refused(client, db, tenant):
    token = _portal_token(client, db, tenant)
    _set_status(db, tenant.organization.id, OrganizationStatus.PENDING_DELETION)
    resp = client.get(f"{API}/portal/dashboard", headers={"X-Portal-Token": token})
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "status",
    [
        OrganizationStatus.PENDING_DELETION,
        OrganizationStatus.DELETED,
        OrganizationStatus.PENDING_APPROVAL,
        OrganizationStatus.REJECTED,
    ],
)
def test_public_links_refused_when_not_active_or_suspended(client, db, tenant, status):
    invoice_token = _sent_invoice_token(client, tenant)
    customer = tenant.customer()
    created = client.post(
        f"{API}/quotes",
        headers=tenant.headers(),
        json={"customer_id": customer.id, "title": "Links", "items": [{"description": "Impl", "quantity": "1", "unit_price": "100.00", "tax_rate_pct": "0"}]},
    )
    assert created.status_code == 201, created.text
    sent = client.post(f"{API}/quotes/{created.json()['id']}/send", headers=tenant.headers())
    quote_token = sent.json()["public_url"].rsplit("/", 1)[1]
    _set_status(db, tenant.organization.id, status)

    assert client.get(f"{API}/public/invoices/{invoice_token}").status_code == 404
    assert client.get(f"{API}/public/invoices/{invoice_token}/pdf").status_code == 404
    assert client.get(f"{API}/public/quotes/{quote_token}").status_code == 404
    assert client.post(f"{API}/public/quotes/{quote_token}/accept", json={"accepted_by_name": "Jane"}).status_code in (403, 404)

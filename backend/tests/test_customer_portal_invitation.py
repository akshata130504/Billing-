"""Tests for the invitation-only Customer Portal activation and access control flow."""
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models import MemberRole
from backend.app.models.base import utcnow
from backend.app.models.portal import (
    CustomerPortalInvitation,
)
from backend.tests.conftest import Tenant



def _get_error_msg(res):
    try:
        data = res.json()
        if "detail" in data:
            return str(data["detail"]).lower()
        if "error" in data and isinstance(data["error"], dict):
            return str(data["error"].get("message", "")).lower()
        return str(data).lower()
    except Exception:
        return res.text.lower()


def test_public_signup_is_blocked(client: TestClient, db: Session):
    """Requirement 1: NO open/public customer self-signup. POST /portal/auth/signup must return 403."""
    tenant = Tenant(db, "signup-blocked")
    res = client.post(
        "/api/v1/portal/auth/signup",
        json={
            "organization_id": tenant.organization.id,
            "email": "intruder@example.com",
            "password": "Password123!",
            "display_name": "Intruder",
        },
    )
    assert res.status_code == 403
    data = res.json()
    assert "disabled" in data["detail"].lower()


def test_portal_invitation_permissions(client: TestClient, db: Session):
    """Requirement 3: Use existing RBAC. Viewer is rejected (403), Finance/Admin/Owner allowed."""
    tenant = Tenant(db, "portal-perm")
    customer = tenant.customer(email="client@example.com")

    # 1. Viewer cannot invite
    viewer_headers = tenant.headers_for_role(MemberRole.VIEWER)
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=viewer_headers,
        json={},
    )
    assert res.status_code == 403

    # 2. Finance can invite
    finance_headers = tenant.headers_for_role(MemberRole.FINANCE)
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=finance_headers,
        json={},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["customer_id"] == customer.id
    assert data["email"] == "client@example.com"
    assert data["status"] == "pending"
    # Email is not configured in tests: finance may invite but never receives the customer's
    # activation link; only admin+ get it to share by hand (BUG-06).
    assert data["email_delivered"] is False
    assert data["invite_url"] is None
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=tenant.headers_for_role(MemberRole.ADMIN),
        json={},
    )
    assert res.status_code == 200
    assert "token=" in res.json()["invite_url"]


def test_customer_portal_access_lifecycle_and_states(client: TestClient, db: Session):
    """Requirement 6 & 7: Verify Not Invited -> Invitation Pending -> Active -> Revoked transitions."""
    tenant = Tenant(db, "portal-states")
    customer = tenant.customer(email="portal.user@example.com")
    finance_headers = tenant.headers_for_role(MemberRole.FINANCE)
    viewer_headers = tenant.headers_for_role(MemberRole.VIEWER)

    # 1. Initially: Not Invited
    res = client.get(f"/api/v1/customers/{customer.id}/portal-access", headers=viewer_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "not_invited"

    # 2. Invite customer -> Invitation Pending
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=tenant.headers_for_role(MemberRole.ADMIN),  # the link is only returned to admin+
        json={},
    )
    assert res.status_code == 200
    invite_url = res.json()["invite_url"]
    raw_token = invite_url.split("token=")[1]

    res = client.get(f"/api/v1/customers/{customer.id}/portal-access", headers=viewer_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "invitation_pending"

    # 3. Customer activates account -> Active
    res = client.post(
        "/api/v1/portal/auth/activate",
        json={
            "token": raw_token,
            "password": "SecurePassword123!",
            "display_name": "Portal Customer Contact",
        },
    )
    assert res.status_code == 200
    session_token = res.json()["token"]
    assert session_token

    res = client.get(f"/api/v1/customers/{customer.id}/portal-access", headers=viewer_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "active"
    assert res.json()["user"]["email"] == "portal.user@example.com"

    # 4. Revoke portal access -> Revoked
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-revoke",
        headers=finance_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "revoked"

    # Active session is revoked:
    res = client.get(
        "/api/v1/portal/dashboard",
        headers={"X-Portal-Token": session_token},
    )
    assert res.status_code == 401

    # 5. Reactivate portal access -> Active
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-reactivate",
        headers=finance_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "active"


def test_token_validation_and_security(client: TestClient, db: Session):
    """Requirement 5: Token is single-use, time-limited, secure, and cannot be reused after acceptance."""
    tenant = Tenant(db, "token-sec")
    customer = tenant.customer(email="token.user@example.com")
    tenant.headers_for_role(MemberRole.FINANCE)

    # 1. Create invitation
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=tenant.headers_for_role(MemberRole.ADMIN),  # the link is only returned to admin+
        json={},
    )
    raw_token = res.json()["invite_url"].split("token=")[1]

    # 2. Validate valid token
    res = client.get(f"/api/v1/portal/auth/invitation?token={raw_token}")
    assert res.status_code == 200
    val_data = res.json()
    assert val_data["valid"] is True
    assert val_data["email"] == "token.user@example.com"
    assert val_data["customer_name"] == customer.display_name
    assert val_data["organization_name"] == tenant.organization.name

    # 3. Invalid token returns error
    res = client.get("/api/v1/portal/auth/invitation?token=invalid-token-12345")
    assert res.status_code in (400, 404)

    # 4. Activate account
    res = client.post(
        "/api/v1/portal/auth/activate",
        json={
            "token": raw_token,
            "password": "ValidPassw0rd!",
        },
    )
    assert res.status_code == 200

    # 5. Token cannot be reused (Single-use enforcement)
    res = client.get(f"/api/v1/portal/auth/invitation?token={raw_token}")
    assert res.status_code in (400, 422)
    assert "already been used" in _get_error_msg(res)

    res = client.post(
        "/api/v1/portal/auth/activate",
        json={
            "token": raw_token,
            "password": "AnotherPassw0rd123!",
        },
    )
    assert res.status_code in (400, 422)
    assert "already been used" in _get_error_msg(res)


def test_expired_and_revoked_token_rejection(client: TestClient, db: Session):
    """Expired or revoked tokens must be rejected."""
    tenant = Tenant(db, "expired-token")
    customer = tenant.customer(email="expired@example.com")
    finance_headers = tenant.headers_for_role(MemberRole.FINANCE)

    # 1. Test Revoked Token
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=tenant.headers_for_role(MemberRole.ADMIN),  # the link is only returned to admin+
        json={},
    )
    raw_token1 = res.json()["invite_url"].split("token=")[1]

    client.post(f"/api/v1/customers/{customer.id}/portal-revoke", headers=finance_headers)

    res = client.get(f"/api/v1/portal/auth/invitation?token={raw_token1}")
    assert res.status_code in (400, 422)
    assert "revoked" in _get_error_msg(res)

    # 2. Test Expired Token
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=tenant.headers_for_role(MemberRole.ADMIN),  # the link is only returned to admin+
        json={},
    )
    raw_token2 = res.json()["invite_url"].split("token=")[1]

    # Manually expire in DB
    db.query(CustomerPortalInvitation).filter(CustomerPortalInvitation.customer_id == customer.id).update(
        {"expires_at": utcnow() - timedelta(hours=1)}
    )
    db.commit()

    res = client.get(f"/api/v1/portal/auth/invitation?token={raw_token2}")
    assert res.status_code in (400, 422)
    assert "expired" in _get_error_msg(res)


def test_portal_login_without_org_uuid(client: TestClient, db: Session):
    """Requirement 4: Customers should not be forced to manually enter an Organization UUID."""
    tenant = Tenant(db, "login-no-org")
    customer = tenant.customer(email="customer.login@example.com")
    tenant.headers_for_role(MemberRole.FINANCE)

    # Invite and activate
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=tenant.headers_for_role(MemberRole.ADMIN),  # the link is only returned to admin+
        json={},
    )
    raw_token = res.json()["invite_url"].split("token=")[1]

    client.post(
        "/api/v1/portal/auth/activate",
        json={
            "token": raw_token,
            "password": "LoginPassword123!",
        },
    )

    # Login without specifying organization_id:
    res = client.post(
        "/api/v1/portal/auth/login",
        json={
            "email": "customer.login@example.com",
            "password": "LoginPassword123!",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["user"]["email"] == "customer.login@example.com"


def test_cross_tenant_isolation(client: TestClient, db: Session):
    """Requirement 11: Cross-tenant isolation must be strictly preserved."""
    tenant_a = Tenant(db, "tenant-a")
    tenant_b = Tenant(db, "tenant-b")
    customer_a = tenant_a.customer(email="cust-a@example.com")

    finance_b = tenant_b.headers_for_role(MemberRole.FINANCE)

    # Tenant B cannot invite Tenant A's customer
    res = client.post(
        f"/api/v1/customers/{customer_a.id}/portal-invite",
        headers=finance_b,
        json={},
    )
    assert res.status_code == 404

    # Tenant B cannot view Tenant A customer's portal access
    res = client.get(
        f"/api/v1/customers/{customer_a.id}/portal-access",
        headers=finance_b,
    )
    assert res.status_code == 404

    # Tenant B cannot revoke Tenant A customer's portal access
    res = client.post(
        f"/api/v1/customers/{customer_a.id}/portal-revoke",
        headers=finance_b,
    )
    assert res.status_code == 404


def test_customer_portal_profile_self_service(client: TestClient, db: Session):
    """B10: Customer can update safe contact details while sensitive fields remain protected."""
    tenant = Tenant(db, "portal-self-service")
    customer = tenant.customer(email="portal.user@example.com")
    customer.company_name = "Original Legal Entity Ltd"
    customer.gstin = "29ABCDE1234F1Z5"
    db.commit()

    tenant.headers_for_role(MemberRole.FINANCE)

    # 1. Invite and activate customer
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=tenant.headers_for_role(MemberRole.ADMIN),  # the link is only returned to admin+
        json={},
    )
    token = res.json()["invite_url"].split("token=")[1]
    act_res = client.post(
        "/api/v1/portal/auth/activate",
        json={"token": token, "password": "SecurePassword123!"},
    )
    portal_token = act_res.json()["token"]
    portal_headers = {"X-Portal-Token": portal_token}

    # 2. Update safe fields via PATCH /portal/profile
    patch_res = client.patch(
        "/api/v1/portal/profile",
        headers=portal_headers,
        json={
            "display_name": "Updated Contact Name",
            "phone": "+91 98765 43210",
            "billing_address_line1": "456 Tech Park, MG Road",
            "billing_city": "Bengaluru",
            "billing_state": "Karnataka",
            "billing_postal_code": "560001",
        },
    )
    assert patch_res.status_code == 200
    data = patch_res.json()["customer"]
    assert data["display_name"] == "Updated Contact Name"
    assert data["phone"] == "+91 98765 43210"
    assert data["billing_address_line1"] == "456 Tech Park, MG Road"
    assert data["billing_city"] == "Bengaluru"

    # 3. Verify sensitive legal entity and GSTIN are unchanged
    assert data["company_name"] == "Original Legal Entity Ltd"
    assert data["gstin"] == "29ABCDE1234F1Z5"

    # 4. Verify persistence via GET /portal/profile
    get_res = client.get("/api/v1/portal/profile", headers=portal_headers)
    assert get_res.status_code == 200
    persisted = get_res.json()["customer"]
    assert persisted["display_name"] == "Updated Contact Name"


def test_customer_portal_payment_methods_self_service(client: TestClient, db: Session):
    """B10: Customer can view, set default, and remove saved payment methods with customer isolation."""
    from backend.app.models.payments import CustomerPaymentMethod, CustomerPaymentMethodStatus

    tenant = Tenant(db, "portal-pm-test")
    customer = tenant.customer(email="pm.user@example.com")
    tenant.headers_for_role(MemberRole.FINANCE)

    # 1. Invite and activate
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=tenant.headers_for_role(MemberRole.ADMIN),  # the link is only returned to admin+
        json={},
    )
    token = res.json()["invite_url"].split("token=")[1]
    act_res = client.post(
        "/api/v1/portal/auth/activate",
        json={"token": token, "password": "SecurePassword123!"},
    )
    portal_headers = {"X-Portal-Token": act_res.json()["token"]}

    # 2. Seed 2 payment methods
    pm1 = CustomerPaymentMethod(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        type="card",
        card_brand="visa",
        last4="1111",
        gateway_token="tok_1111",
        is_default=True,
        status=CustomerPaymentMethodStatus.ACTIVE,
    )
    pm2 = CustomerPaymentMethod(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        type="card",
        card_brand="mastercard",
        last4="2222",
        gateway_token="tok_2222",
        is_default=False,
        status=CustomerPaymentMethodStatus.ACTIVE,
    )
    db.add_all([pm1, pm2])
    db.commit()

    # 3. List payment methods via GET /portal/payment-methods
    list_res = client.get("/api/v1/portal/payment-methods", headers=portal_headers)
    assert list_res.status_code == 200
    pms = list_res.json()
    assert len(pms) == 2

    # 4. Set pm2 as default via PATCH /portal/payment-methods/{id}/default
    def_res = client.patch(f"/api/v1/portal/payment-methods/{pm2.id}/default", headers=portal_headers)
    assert def_res.status_code == 200

    db.refresh(pm1)
    db.refresh(pm2)
    assert pm1.is_default is False
    assert pm2.is_default is True

    # 5. Remove pm1 via DELETE /portal/payment-methods/{id}
    del_res = client.delete(f"/api/v1/portal/payment-methods/{pm1.id}", headers=portal_headers)
    assert del_res.status_code == 200

    db.refresh(pm1)
    assert pm1.status == CustomerPaymentMethodStatus.REVOKED


def _activated_portal_headers(client: TestClient, tenant: Tenant, customer) -> dict:
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=tenant.headers_for_role(MemberRole.ADMIN),  # the link is only returned to admin+
        json={},
    )
    token = res.json()["invite_url"].split("token=")[1]
    act_res = client.post("/api/v1/portal/auth/activate", json={"token": token, "password": "SecurePassword123!"})
    return {"X-Portal-Token": act_res.json()["token"]}


def test_portal_never_exposes_draft_invoices(client: TestClient, db: Session):
    from backend.app.models.invoices import InvoiceStatus

    tenant = Tenant(db, "portal-drafts")
    customer = tenant.customer(email="drafts.user@example.com")
    issued = tenant.invoice(customer, amount="500.00", status=InvoiceStatus.SENT)
    draft = tenant.invoice(customer, amount="900.00", status=InvoiceStatus.DRAFT)
    void = tenant.invoice(customer, amount="700.00", status=InvoiceStatus.VOID)
    headers = _activated_portal_headers(client, tenant, customer)

    listed = {inv["id"] for inv in client.get("/api/v1/portal/invoices", headers=headers).json()}
    assert issued.id in listed and void.id in listed
    assert draft.id not in listed

    assert client.get(f"/api/v1/portal/invoices/{draft.id}", headers=headers).status_code == 404
    assert client.get(f"/api/v1/portal/invoices/{draft.id}/pdf", headers=headers).status_code == 404
    assert client.get(f"/api/v1/portal/invoices/{draft.id}/signed-url", headers=headers).status_code == 404

    from backend.app.services import customer_portal_service

    token = customer_portal_service.generate_signed_document_token(
        organization_id=tenant.organization.id, customer_id=customer.id, invoice_id=draft.id, expires_in_seconds=60
    )
    assert client.get(f"/api/v1/portal/invoices/signed-download?token={token}").status_code == 404

    dashboard = client.get("/api/v1/portal/dashboard", headers=headers).json()
    assert dashboard["open_invoices_count"] == 1
    assert float(dashboard["total_outstanding_amount"]) == 500.0
    assert draft.id not in {inv["id"] for inv in dashboard["recent_invoices"]}


def test_portal_trial_settings_are_enforced(client: TestClient, db: Session):
    from datetime import date

    from backend.app.models.subscriptions import Subscription, SubscriptionStatus
    from backend.app.services import customer_portal_service

    tenant = Tenant(db, "portal-trials")
    customer = tenant.customer(email="trial.user@example.com")
    _, plan = tenant.product_with_plan(trial_days=14)
    sub = Subscription(
        organization_id=tenant.organization.id,
        subscription_number=f"SUB-{uuid4_hex()}",
        customer_id=customer.id,
        plan_id=plan.id,
        status=SubscriptionStatus.TRIALING,
        start_date=date.today(),
        trial_end=date.today() + timedelta(days=14),
        current_period_start=date.today(),
        current_period_end=date.today() + timedelta(days=14),
    )
    db.add(sub)
    settings = customer_portal_service.get_or_create_portal_settings(db, tenant.organization.id)
    settings.trials_allow_customer_extension = False
    settings.trials_activate_immediately = False
    db.commit()
    headers = _activated_portal_headers(client, tenant, customer)

    ext = client.post(f"/api/v1/portal/subscriptions/{sub.id}/trial/extend?days=3", headers=headers)
    assert ext.status_code == 403
    conv = client.post(f"/api/v1/portal/subscriptions/{sub.id}/trial/convert", headers=headers)
    assert conv.status_code == 403

    settings.trials_allow_customer_extension = True
    settings.trials_max_extensions = 0
    db.commit()
    ext = client.post(f"/api/v1/portal/subscriptions/{sub.id}/trial/extend?days=3", headers=headers)
    assert ext.status_code == 403
    assert "Maximum" in ext.text


def test_portal_settings_ignore_unimplemented_mfa_flag(client: TestClient, db: Session):
    tenant = Tenant(db, "portal-mfa")
    res = client.patch("/api/v1/portal/settings", headers=tenant.headers(), json={"mfa_enabled": True, "portal_name": "Acme Portal"})
    assert res.status_code == 200
    assert res.json()["portal_name"] == "Acme Portal"
    assert res.json()["mfa_enabled"] is False


def test_portal_invitation_email_escapes_user_values(client: TestClient, db: Session, monkeypatch):
    from backend.app.services import customer_portal_service

    captured = {}

    def fake_send_email(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(customer_portal_service, "send_email", fake_send_email)
    customer_portal_service._send_portal_invitation_email(
        db, "org-x", "a@example.com", "https://app.example.com/portal/activate?token=t&x=1", "<b>Evil & Co</b>", "<script>"
    )
    assert "<script>" not in captured["html_body"]
    assert "&lt;b&gt;Evil &amp; Co&lt;/b&gt;" in captured["html_body"]
    assert "token=t&amp;x=1" in captured["html_body"]


def uuid4_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]

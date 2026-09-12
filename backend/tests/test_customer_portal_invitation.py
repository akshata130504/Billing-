"""Tests for the invitation-only Customer Portal activation and access control flow."""
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.security import hash_password
from backend.app.models import MemberRole
from backend.app.models.base import utcnow
from backend.app.models.customers import Customer
from backend.app.models.portal import (
    CustomerPortalInvitation,
    CustomerPortalSession,
    CustomerPortalSettings,
    CustomerPortalUser,
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
    assert "token=" in data["invite_url"]


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
        headers=finance_headers,
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
    finance_headers = tenant.headers_for_role(MemberRole.FINANCE)

    # 1. Create invitation
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=finance_headers,
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
        headers=finance_headers,
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
        headers=finance_headers,
        json={},
    )
    raw_token2 = res.json()["invite_url"].split("token=")[1]

    # Manually expire in DB
    inv = db.scalars(
        CustomerPortalInvitation.__table__.select().where(
            CustomerPortalInvitation.customer_id == customer.id,
            CustomerPortalInvitation.accepted_at.is_(None),
            CustomerPortalInvitation.revoked_at.is_(None),
        )
    ).first()
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
    finance_headers = tenant.headers_for_role(MemberRole.FINANCE)

    # Invite and activate
    res = client.post(
        f"/api/v1/customers/{customer.id}/portal-invite",
        headers=finance_headers,
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

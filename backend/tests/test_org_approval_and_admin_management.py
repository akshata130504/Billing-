"""Tests for Organization Approval Lifecycle, Super Admin Organization Control,
Tenant Admin Management, Owner Protection, and Financial Data Boundaries.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.app.core.security import create_access_token
from backend.app.models import (
    Customer,
    Membership,
    MemberRole,
    MembershipStatus,
    Organization,
    OrganizationStatus,
    PendingSignup,
    RefreshToken,
    User,
)
from backend.app.models.platform import PlatformAuditLog, PlatformRole
from backend.app.services import platform_audit
from backend.tests.test_platform_console import Staff

API = "/api/v1"
PASSWORD = "Password123!"


def _create_tenant_user(db, org: Organization, email: str, role: MemberRole, name: str = "Test User") -> tuple[User, Membership]:
    user = User(
        email=email,
        full_name=name,
        hashed_password="fake-hash-for-tests",
        is_active=True,
    )
    db.add(user)
    db.flush()
    membership = Membership(
        organization_id=org.id,
        user_id=user.id,
        role=role,
        status=MembershipStatus.ACTIVE,
    )
    db.add(membership)
    db.commit()
    db.refresh(user)
    db.refresh(membership)
    return user, membership


def _token(user: User, org: Organization, mem: Membership) -> str:
    return create_access_token(user.id, org.id, mem.role.value)


def test_signup_creates_active_trial_org(client, db):
    """Signup needs no Super Admin approval: the organization is ACTIVE and its trial starts at once."""
    email = f"owner-{uuid.uuid4().hex[:6]}@example.com"
    org_name = f"Startup {uuid.uuid4().hex[:6]}"
    captured_otp = "123456"

    with patch("backend.app.services.auth_service.send_email", return_value=True), \
         patch("backend.app.services.auth_service.generate_otp", return_value=captured_otp):
        r1 = client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": org_name,
                "full_name": "New Founder",
                "email": email,
                "password": PASSWORD,
            },
        )
        assert r1.status_code == 200, r1.text

        r2 = client.post(
            f"{API}/auth/signup/verify-otp",
            json={"email": email, "otp": captured_otp, "password": PASSWORD},
        )
        assert r2.status_code == 201, r2.text
        data = r2.json()
        assert data["me"]["organization"]["status"] == "active"
        assert data["me"]["access"]["status"] == "trial"
        # Signed in straight into the trial: business endpoints work with the returned token.
        token = data["access_token"]
        assert client.get(f"{API}/customers", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    org = db.scalars(select(Organization).where(Organization.name == org_name)).first()
    assert org is not None
    assert org.status == OrganizationStatus.ACTIVE
    assert org.module_access == "trial"
    started = org.trial_started_at if org.trial_started_at.tzinfo else org.trial_started_at.replace(tzinfo=timezone.utc)
    ends = org.trial_ends_at if org.trial_ends_at.tzinfo else org.trial_ends_at.replace(tzinfo=timezone.utc)
    assert (ends - started).total_seconds() == 3 * 86400
    owner = db.scalars(select(Membership).where(Membership.organization_id == org.id)).one()
    assert owner.role == MemberRole.OWNER and owner.status == MembershipStatus.ACTIVE
    trial_row = db.scalars(select(PlatformAuditLog).where(
        PlatformAuditLog.action == platform_audit.ORGANIZATION_TRIAL_STARTED, PlatformAuditLog.organization_id == org.id)).first()
    assert trial_row is not None and trial_row.details["trial_days"] == 3

    # Check audit log
    audit_row = db.scalars(
        select(PlatformAuditLog).where(
            PlatformAuditLog.action == platform_audit.ORGANIZATION_CREATED,
            PlatformAuditLog.organization_id == org.id,
        )
    ).first()
    assert audit_row is not None
    assert audit_row.details["owner_email"] == email


def test_pending_org_blocks_tenant_endpoints_and_allows_auth_me(client, db):
    """Pending organization blocks normal tenant business operations but allows /auth/me."""
    org = Organization(
        name=f"Pending Org {uuid.uuid4().hex[:6]}",
        slug=f"pending-{uuid.uuid4().hex[:6]}",
        status=OrganizationStatus.PENDING_APPROVAL,
    )
    db.add(org)
    db.flush()
    user, membership = _create_tenant_user(db, org, f"owner-{uuid.uuid4().hex[:6]}@test.com", MemberRole.OWNER)

    token = _token(user, org, membership)
    headers = {"Authorization": f"Bearer {token}"}

    # /auth/me should succeed and return status='pending_approval'
    r_me = client.get(f"{API}/auth/me", headers=headers)
    assert r_me.status_code == 200, r_me.text
    assert r_me.json()["organization"]["status"] == "pending_approval"

    # Business operations (customers, invoices) should return 403 Forbidden
    r_cust = client.get(f"{API}/customers", headers=headers)
    assert r_cust.status_code == 403
    assert "pending approval" in r_cust.text.lower()

    r_inv = client.get(f"{API}/invoices", headers=headers)
    assert r_inv.status_code == 403
    assert "pending approval" in r_inv.text.lower()


def test_super_admin_approves_org(client, db):
    """Super Admin approves pending organization, transitioning it to ACTIVE."""
    admin = Staff(db, PlatformRole.PLATFORM_ADMINISTRATOR)
    admin.step_up()

    org = Organization(
        name=f"To Approve {uuid.uuid4().hex[:6]}",
        slug=f"approve-{uuid.uuid4().hex[:6]}",
        status=OrganizationStatus.PENDING_APPROVAL,
    )
    db.add(org)
    db.flush()
    user, membership = _create_tenant_user(db, org, f"owner-{uuid.uuid4().hex[:6]}@test.com", MemberRole.OWNER)

    # Approve
    r = admin.post(f"/organizations/{org.id}/approve", {"reason": "Verified legitimate company documentation"})
    assert r.status_code == 200, r.text
    assert r.json()["organization"]["status"] == "active"

    db.refresh(org)
    assert org.status == OrganizationStatus.ACTIVE

    # Verify audit
    log = db.scalars(
        select(PlatformAuditLog).where(
            PlatformAuditLog.action == platform_audit.ORGANIZATION_APPROVED,
            PlatformAuditLog.organization_id == org.id,
        )
    ).first()
    assert log is not None
    assert log.result == "success"

    # Tenant user can now access business endpoints
    token = _token(user, org, membership)
    r_cust = client.get(f"{API}/customers", headers={"Authorization": f"Bearer {token}"})
    assert r_cust.status_code == 200


def test_super_admin_rejects_org_with_mandatory_reason(client, db):
    """Rejection requires a mandatory reason of at least 10 chars, transitions to REJECTED."""
    admin = Staff(db, PlatformRole.PLATFORM_ADMINISTRATOR)
    admin.step_up()

    org = Organization(
        name=f"To Reject {uuid.uuid4().hex[:6]}",
        slug=f"reject-{uuid.uuid4().hex[:6]}",
        status=OrganizationStatus.PENDING_APPROVAL,
    )
    db.add(org)
    db.flush()
    user, membership = _create_tenant_user(db, org, f"owner-{uuid.uuid4().hex[:6]}@test.com", MemberRole.OWNER)

    # Attempt rejection with short reason -> rejected by validation
    r_short = admin.post(f"/organizations/{org.id}/reject", {"reason": "bad"})
    assert r_short.status_code in (422, 409)

    # Rejection with valid explanation
    explanation = "Invalid GSTIN and incomplete company documentation provided."
    r = admin.post(f"/organizations/{org.id}/reject", {"reason": explanation})
    assert r.status_code == 200, r.text
    assert r.json()["organization"]["status"] == "rejected"

    db.refresh(org)
    assert org.status == OrganizationStatus.REJECTED
    assert org.status_reason == explanation

    # Tenant user is blocked and receives the rejection reason
    token = _token(user, org, membership)
    r_cust = client.get(f"{API}/customers", headers={"Authorization": f"Bearer {token}"})
    assert r_cust.status_code == 403
    assert "rejected" in r_cust.text.lower()
    assert explanation in r_cust.text


def test_non_admin_cannot_approve_or_reject(db):
    """Operations and Support platform roles cannot approve or reject organizations."""
    ops = Staff(db, PlatformRole.PLATFORM_OPERATIONS)
    support = Staff(db, PlatformRole.PLATFORM_SUPPORT)

    org = Organization(
        name=f"Test {uuid.uuid4().hex[:6]}",
        slug=f"test-{uuid.uuid4().hex[:6]}",
        status=OrganizationStatus.PENDING_APPROVAL,
    )
    db.add(org)
    db.commit()

    # Both have completed step-up, so a 403 can only come from the role check.
    for staff in (ops, support):
        staff.step_up()
        r_approve = staff.post(f"/organizations/{org.id}/approve", {"reason": "Approving without the role"})
        assert r_approve.status_code == 403, r_approve.text
        r_reject = staff.post(f"/organizations/{org.id}/reject", {"reason": "Rejecting without the role"})
        assert r_reject.status_code == 403, r_reject.text

    db.expire_all()
    assert db.get(Organization, org.id).status == OrganizationStatus.PENDING_APPROVAL


def test_tenant_admin_management_and_owner_protection(db):
    """Super Admin can manage tenant Admins (deactivate, reactivate, revoke sessions) but NOT the Owner."""
    admin_staff = Staff(db, PlatformRole.PLATFORM_ADMINISTRATOR)
    admin_staff.step_up()

    org = Organization(
        name=f"Corp {uuid.uuid4().hex[:6]}",
        slug=f"corp-{uuid.uuid4().hex[:6]}",
        status=OrganizationStatus.ACTIVE,
    )
    db.add(org)
    db.flush()

    owner_user, owner_mem = _create_tenant_user(db, org, f"owner-{uuid.uuid4().hex[:6]}@corp.test", MemberRole.OWNER, "Alice Owner")
    admin_user, admin_mem = _create_tenant_user(db, org, f"admin-{uuid.uuid4().hex[:6]}@corp.test", MemberRole.ADMIN, "Bob Admin")

    now = datetime.now(timezone.utc)
    token_row = RefreshToken(
        id=uuid.uuid4().hex,
        user_id=admin_user.id,
        organization_id=org.id,
        token_hash="fake-hash",
        expires_at=now.replace(year=now.year + 1),
    )
    db.add(token_row)
    db.commit()

    # List admins
    r_list = admin_staff.get(f"/organizations/{org.id}/admins")
    assert r_list.status_code == 200, r_list.text
    items = r_list.json()
    assert len(items) == 2
    roles = {i["role"] for i in items}
    assert "owner" in roles and "admin" in roles

    # OWNER PROTECTION: Attempting to deactivate Owner must fail with 403
    r_own = admin_staff.post(
        f"/organizations/{org.id}/admins/{owner_user.id}/deactivate",
        {"reason": "Attempting to deactivate owner"},
    )
    assert r_own.status_code == 403
    assert "Owner cannot be deactivated" in r_own.text

    # Deactivate tenant Admin
    r_deact = admin_staff.post(
        f"/organizations/{org.id}/admins/{admin_user.id}/deactivate",
        {"reason": "Admin departure from customer team"},
    )
    assert r_deact.status_code == 200, r_deact.text
    db.refresh(admin_mem)
    assert admin_mem.status == MembershipStatus.DEACTIVATED

    # Verify audit
    deact_log = db.scalars(
        select(PlatformAuditLog).where(
            PlatformAuditLog.action == platform_audit.TENANT_ADMIN_DEACTIVATED,
            PlatformAuditLog.target_id == admin_user.id,
        )
    ).first()
    assert deact_log is not None

    # Reactivate tenant Admin
    r_react = admin_staff.post(
        f"/organizations/{org.id}/admins/{admin_user.id}/reactivate",
        {"reason": "Reinstated admin privileges per customer request"},
    )
    assert r_react.status_code == 200, r_react.text
    db.refresh(admin_mem)
    assert admin_mem.status == MembershipStatus.ACTIVE

    # Revoke sessions for tenant Admin
    r_rev = admin_staff.post(
        f"/organizations/{org.id}/admins/{admin_user.id}/revoke-sessions",
        {"reason": "Security rotation after compromised laptop"},
    )
    assert r_rev.status_code == 200, r_rev.text


def test_tenant_isolation_boundary(client, db):
    """Admin A in Organization A can NEVER access Organization B data."""
    org_a = Organization(name="Org A", slug=f"org-a-{uuid.uuid4().hex[:6]}", status=OrganizationStatus.ACTIVE)
    org_b = Organization(name="Org B", slug=f"org-b-{uuid.uuid4().hex[:6]}", status=OrganizationStatus.ACTIVE)
    db.add_all([org_a, org_b])
    db.flush()

    user_a, mem_a = _create_tenant_user(db, org_a, f"admin-a-{uuid.uuid4().hex[:6]}@a.test", MemberRole.ADMIN)
    user_b, mem_b = _create_tenant_user(db, org_b, f"admin-b-{uuid.uuid4().hex[:6]}@b.test", MemberRole.ADMIN)

    cust_b = Customer(
        organization_id=org_b.id,
        customer_number="CUS-9999",
        display_name="Customer in Org B",
        email=f"cust-{uuid.uuid4().hex[:6]}@b.test",
    )
    db.add(cust_b)
    db.commit()

    token_a = _token(user_a, org_a, mem_a)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Admin A attempts to fetch Customer in Org B -> 404 (not found in tenant context)
    r = client.get(f"{API}/customers/{cust_b.id}", headers=headers_a)
    assert r.status_code == 404

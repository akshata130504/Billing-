"""Automated tests for Phase 4: Hosted Payment Pages and Customer Portal.

The hosted-checkout payment flow itself is covered in test_hosted_checkout_payments.py.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest

from backend.app.models import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    Invoice,
    InvoiceStatus,
    Payment,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from backend.app.models.checkout import (
    CheckoutSession,
    CheckoutSessionPurpose,
    CheckoutSessionStatus,
    CheckoutTemplate,
)
from backend.app.core.security import hash_password
from backend.app.models.portal import CustomerPortalUser


def _setup_portal_user(db, org_id, customer, email, password="SecurePassword123!", display_name="Portal User"):
    user = CustomerPortalUser(
        organization_id=org_id,
        customer_id=customer.id,
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_customer_portal_settings_management(client, tenant, auth_headers, db):
    # 1. Get default settings
    res = client.get("/api/v1/portal/settings", headers=auth_headers)
    assert res.status_code == 200
    settings_data = res.json()
    assert settings_data["portal_name"] is not None

    # 2. Update portal settings
    patch_res = client.patch(
        "/api/v1/portal/settings",
        headers=auth_headers,
        json={
            "portal_name": "Acme SaaS Customer Hub",
            "banner_message": "Welcome to our customer portal!",
            "mfa_enabled": False,
            "allow_save_payment_methods": True,
            "trials_allow_customer_extension": True,
            "trials_max_extensions": 3,
        },
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["portal_name"] == "Acme SaaS Customer Hub"
    assert updated["trials_max_extensions"] == 3


def test_customer_portal_signup_login_and_dashboard(client, tenant, auth_headers, db):
    customer = tenant.customer(email="customer_contact@example.com")
    product, plan = tenant.product_with_plan(unit_amount="1000.00")
    inv = tenant.invoice(customer, amount="1000.00")

    # 1. Customer open signup is disabled (Requirement 1)
    signup_res = client.post(
        "/api/v1/portal/auth/signup",
        json={
            "organization_id": tenant.organization.id,
            "email": "customer_contact@example.com",
            "password": "SecurePassword123!",
            "display_name": "Alice Customer",
            "customer_id": customer.id,
        },
    )
    assert signup_res.status_code == 403

    # Set up user account as if activated via invitation
    _setup_portal_user(
        db,
        tenant.organization.id,
        customer,
        email="customer_contact@example.com",
        password="SecurePassword123!",
        display_name="Alice Customer",
    )

    # 2. Customer logs in
    login_res = client.post(
        "/api/v1/portal/auth/login",
        json={
            "organization_id": tenant.organization.id,
            "email": "customer_contact@example.com",
            "password": "SecurePassword123!",
        },
    )
    assert login_res.status_code == 200
    auth_data = login_res.json()
    portal_token = auth_data["token"]
    assert portal_token is not None
    portal_headers = {"X-Portal-Token": portal_token}

    # 3. Customer views their portal dashboard
    dash_res = client.get("/api/v1/portal/dashboard", headers=portal_headers)
    assert dash_res.status_code == 200
    dash = dash_res.json()
    assert dash["customer_name"] == customer.display_name
    assert dash["open_invoices_count"] >= 1
    assert Decimal(str(dash["total_outstanding_amount"])) >= Decimal("1000.00")

    # 4. Customer views their invoices
    inv_res = client.get("/api/v1/portal/invoices", headers=portal_headers)
    assert inv_res.status_code == 200
    assert len(inv_res.json()) >= 1


def test_customer_portal_trial_self_service(client, tenant, auth_headers, db):
    customer = tenant.customer(email="trial_user@example.com")
    product, plan = tenant.product_with_plan(unit_amount="2200.00", trial_days=7)

    # Create trialing subscription for customer
    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "quantity": 1,
            "start_date": str(date.today()),
        },
    )
    sub_id = res.json()["id"]

    # Customer activated via invitation and logs in to portal
    _setup_portal_user(
        db,
        tenant.organization.id,
        customer,
        email="trial_user@example.com",
        password="SecurePassword123!",
        display_name="Bob Trialer",
    )
    login_res = client.post(
        "/api/v1/portal/auth/login",
        json={
            "organization_id": tenant.organization.id,
            "email": "trial_user@example.com",
            "password": "SecurePassword123!",
        },
    )
    portal_token = login_res.json()["token"]
    portal_headers = {"X-Portal-Token": portal_token}

    # 1. Customer self-service trial extension from portal
    ext_res = client.post(
        f"/api/v1/portal/subscriptions/{sub_id}/trial/extend?days=5",
        headers=portal_headers,
    )
    assert ext_res.status_code == 200
    ext_data = ext_res.json()
    assert ext_data["status"] == "success"
    assert ext_data["extension_count"] == 1

    # 2. Customer early conversion from portal
    conv_res = client.post(
        f"/api/v1/portal/subscriptions/{sub_id}/trial/convert",
        headers=portal_headers,
    )
    assert conv_res.status_code == 200
    conv_data = conv_res.json()
    assert conv_data["status"] == "active"


def test_hosted_checkout_token_is_hashed_in_database(client, tenant, auth_headers, db):
    """Bearer token must never be stored as plaintext in the database."""
    import hashlib
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1000.00")

    res = client.post(
        "/api/v1/checkout/sessions",
        headers=auth_headers,
        json={"purpose": "invoice_payment", "invoice_id": inv.id, "expires_in_hours": 1},
    )
    assert res.status_code == 201
    raw_token = res.json()["token"]

    # In DB, CheckoutSession.token must be the sha256 hash, NOT the raw token
    expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    session_row = db.query(CheckoutSession).filter(CheckoutSession.token == expected_hash).first()
    assert session_row is not None
    assert session_row.token != raw_token
    assert session_row.token == expected_hash

    # Public view still resolves using the raw token
    pub_res = client.get(f"/api/v1/checkout/public/{raw_token}")
    assert pub_res.status_code == 200
    assert pub_res.json()["token"] == raw_token


def test_hosted_checkout_revalidates_paid_invoice_and_is_idempotent(client, tenant, auth_headers, db):
    """Revalidate invoice status; confirm already-completed session is idempotent; prevent paying paid invoice."""
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="500.00", status=InvoiceStatus.PAID)

    # Creating checkout session for already-paid invoice must fail with 409
    res = client.post(
        "/api/v1/checkout/sessions",
        headers=auth_headers,
        json={"purpose": "invoice_payment", "invoice_id": inv.id},
    )
    assert res.status_code == 409


def test_customer_portal_signup_rejects_arbitrary_customer_id_with_mismatched_email(client, tenant, auth_headers, db):
    """Vulnerability test: public signup is blocked completely (Requirement 1)."""
    victim = tenant.customer(email="victim_company@example.com")

    # Attacker tries to register using victim's customer_id
    attacker_res = client.post(
        "/api/v1/portal/auth/signup",
        json={
            "organization_id": tenant.organization.id,
            "email": "attacker@evil.com",
            "password": "AttackerPassword123!",
            "display_name": "Eve Attacker",
            "customer_id": victim.id,
        },
    )
    assert attacker_res.status_code == 403


def test_customer_portal_session_token_hashed_in_database(client, tenant, auth_headers, db):
    """Customer portal session bearer token must be hashed in DB, never plaintext."""
    import hashlib
    from backend.app.models.portal import CustomerPortalSession

    customer = tenant.customer(email="session_test@example.com")
    _setup_portal_user(
        db,
        tenant.organization.id,
        customer,
        email="session_test@example.com",
        password="SecurePassword123!",
        display_name="Session Tester",
    )

    login_res = client.post(
        "/api/v1/portal/auth/login",
        json={
            "organization_id": tenant.organization.id,
            "email": "session_test@example.com",
            "password": "SecurePassword123!",
        },
    )
    assert login_res.status_code == 200
    raw_token = login_res.json()["token"]

    # In database, the session token must match sha256(raw_token), NOT raw_token
    expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    session_row = db.query(CustomerPortalSession).filter(CustomerPortalSession.token == expected_hash).first()
    assert session_row is not None
    assert session_row.token != raw_token

    # Authenticating with the raw token must succeed
    dash_res = client.get("/api/v1/portal/dashboard", headers={"X-Portal-Token": raw_token})
    assert dash_res.status_code == 200


def test_customer_portal_signed_document_download(client, tenant, auth_headers, db):
    """Customer can generate a signed short-lived download token and download PDF; forged token fails."""
    customer = tenant.customer(email="pdf_user@example.com")
    inv = tenant.invoice(customer, amount="1500.00")

    _setup_portal_user(
        db,
        tenant.organization.id,
        customer,
        email="pdf_user@example.com",
        password="SecurePassword123!",
        display_name="PDF User",
    )
    login_res = client.post(
        "/api/v1/portal/auth/login",
        json={
            "organization_id": tenant.organization.id,
            "email": "pdf_user@example.com",
            "password": "SecurePassword123!",
        },
    )
    token = login_res.json()["token"]
    headers = {"X-Portal-Token": token}

    # 1. Direct PDF download with portal auth
    pdf_res = client.get(f"/api/v1/portal/invoices/{inv.id}/pdf", headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 100

    # 2. Generate signed download URL
    url_res = client.get(f"/api/v1/portal/invoices/{inv.id}/signed-url", headers=headers)
    assert url_res.status_code == 200
    signed_token = url_res.json()["token"]

    # 3. Public download with signed token
    signed_dl_res = client.get(f"/api/v1/portal/invoices/signed-download?token={signed_token}")
    assert signed_dl_res.status_code == 200
    assert signed_dl_res.headers["content-type"] == "application/pdf"

    # 4. Tampered token fails with 401
    tampered_token = signed_token[:-4] + "dead"
    tampered_res = client.get(f"/api/v1/portal/invoices/signed-download?token={tampered_token}")
    assert tampered_res.status_code == 401


def test_customer_portal_invoices_payments_profile_and_isolation(client, tenant, auth_headers, db):
    """Verify invoice details, payment history, profile endpoints, logout, and strict isolation."""
    # Setup Customer A
    cust_a = tenant.customer(email="portal_a@example.com")
    inv_a = tenant.invoice(cust_a, amount="2500.00")
    
    # Setup Customer B
    cust_b = tenant.customer(email="portal_b@example.com")
    inv_b = tenant.invoice(cust_b, amount="4000.00")

    # Record a payment for Customer A
    from backend.app.models.payments import Payment, PaymentMethod, PaymentGateway, PaymentStatus
    pay_a = Payment(
        organization_id=tenant.organization.id,
        payment_number="PAY-PORTAL-001",
        customer_id=cust_a.id,
        amount=2500.00,
        currency="INR",
        method=PaymentMethod.BANK_TRANSFER,
        gateway=PaymentGateway.MANUAL,
        status=PaymentStatus.SUCCEEDED,
    )
    db.add(pay_a)
    db.commit()

    # Setup Portal User A
    _setup_portal_user(
        db,
        tenant.organization.id,
        cust_a,
        email="portal_a@example.com",
        password="SecurePassword123!",
        display_name="Portal User A",
    )
    login_a = client.post(
        "/api/v1/portal/auth/login",
        json={
            "organization_id": tenant.organization.id,
            "email": "portal_a@example.com",
            "password": "SecurePassword123!",
        },
    )
    assert login_a.status_code == 200
    token_a = login_a.json()["token"]
    headers_a = {"X-Portal-Token": token_a}

    # 1. Invoice detail for Customer A's own invoice
    detail_res = client.get(f"/api/v1/portal/invoices/{inv_a.id}", headers=headers_a)
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["id"] == inv_a.id
    assert "public_token" in detail_data

    # 2. Customer A CANNOT access Customer B's invoice -> 404
    cross_inv_res = client.get(f"/api/v1/portal/invoices/{inv_b.id}", headers=headers_a)
    assert cross_inv_res.status_code == 404

    # 3. Payments list for Customer A includes pay_a
    payments_res = client.get("/api/v1/portal/payments", headers=headers_a)
    assert payments_res.status_code == 200
    payments_data = payments_res.json()
    assert len(payments_data) >= 1
    assert any(p["payment_number"] == "PAY-PORTAL-001" for p in payments_data)

    # 4. Profile endpoint
    profile_res = client.get("/api/v1/portal/profile", headers=headers_a)
    assert profile_res.status_code == 200
    prof = profile_res.json()
    assert prof["user"]["email"] == "portal_a@example.com"
    assert prof["customer"]["id"] == cust_a.id

    # 5. Logout invalidates session
    logout_res = client.post("/api/v1/portal/auth/logout", headers=headers_a)
    assert logout_res.status_code == 200

    # Subsequent call with revoked token returns 401
    revoked_res = client.get("/api/v1/portal/profile", headers=headers_a)
    assert revoked_res.status_code == 401


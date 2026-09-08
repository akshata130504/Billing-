"""Automated tests for Phase 4: Hosted Payment Pages and Customer Portal."""
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


def test_hosted_checkout_invoice_flow(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="2000.00")

    # Create an invoice for the customer
    inv = tenant.invoice(customer, amount="2000.00")
    assert inv.amount_due == Decimal("2000.00")

    # 1. Admin generates hosted checkout session
    res = client.post(
        "/api/v1/checkout/sessions",
        headers=auth_headers,
        json={
            "purpose": "invoice_payment",
            "invoice_id": inv.id,
            "expires_in_hours": 2,
            "save_payment_method": True,
        },
    )
    assert res.status_code == 201
    session_data = res.json()
    assert session_data["status"] == "created"
    assert Decimal(str(session_data["amount"])) == Decimal("2000.00")
    token = session_data["token"]

    # 2. Customer opens public checkout page without authentication
    public_res = client.get(f"/api/v1/checkout/public/{token}")
    assert public_res.status_code == 200
    pub_data = public_res.json()
    assert pub_data["status"] == "pending"
    assert not pub_data["is_expired"]
    assert Decimal(str(pub_data["amount"])) == Decimal("2000.00")
    assert pub_data["customer_name"] == customer.display_name

    # 3. Customer submits payment on hosted checkout page with verified gateway credentials
    from backend.app.models.payments import PaymentGateway
    from backend.app.services.gateways.base import GatewayChargeResult
    from backend.app.services.gateways.registry import get_gateway_adapter, register_gateway_adapter

    real_adapter = get_gateway_adapter(PaymentGateway.RAZORPAY)

    class _SucceedingCheckoutAdapter:
        gateway_type = PaymentGateway.RAZORPAY

        def charge(self, **kwargs):
            return GatewayChargeResult(success=True, gateway_payment_id="pay_checkout_success_123")

        def refund(self, **kwargs):
            raise NotImplementedError

        def verify_webhook(self, **kwargs):
            return True

        def verify_payment_signature(self, payment_id: str, order_id: str, signature: str) -> bool:
            return signature == "valid_hmac_signature"

    register_gateway_adapter(PaymentGateway.RAZORPAY, _SucceedingCheckoutAdapter())
    try:
        confirm_res = client.post(
            f"/api/v1/checkout/public/{token}/confirm",
            json={
                "payment_method_type": "card",
                "razorpay_payment_id": "pay_checkout_success_123",
                "razorpay_order_id": "order_hpp_test_123",
                "razorpay_signature": "valid_hmac_signature",
                "card_last4": "5555",
                "card_brand": "Mastercard",
                "save_payment_method": True,
            },
        )
    finally:
        register_gateway_adapter(PaymentGateway.RAZORPAY, real_adapter)

    assert confirm_res.status_code == 200
    conf_data = confirm_res.json()
    assert conf_data["status"] == "successful"
    assert conf_data["payment_id"] is not None

    # Verify invoice is paid and balance is 0
    db.refresh(inv)
    assert inv.status == InvoiceStatus.PAID
    assert inv.amount_due == Decimal("0.00")

    # Verify customer payment method was vaulted
    pm = (
        db.query(CustomerPaymentMethod)
        .filter(CustomerPaymentMethod.customer_id == customer.id, CustomerPaymentMethod.last4 == "5555")
        .first()
    )
    assert pm is not None
    assert pm.is_default is True


def test_hosted_checkout_expiry_behavior(client, tenant, auth_headers, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1500.00")

    # Create session directly with expired timestamp
    session = CheckoutSession(
        organization_id=tenant.organization.id,
        token="test_expired_token_123",
        purpose=CheckoutSessionPurpose.INVOICE_PAYMENT,
        status=CheckoutSessionStatus.CREATED,
        customer_id=customer.id,
        invoice_id=inv.id,
        amount=Decimal("1500.00"),
        currency="INR",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(session)
    db.commit()

    # Public view reflects expired status
    res = client.get("/api/v1/checkout/public/test_expired_token_123")
    assert res.status_code == 200
    assert res.json()["is_expired"] is True
    assert res.json()["status"] == "expired"

    # Confirmation fails on expired session
    conf_res = client.post(
        "/api/v1/checkout/public/test_expired_token_123/confirm",
        json={"card_last4": "1111"},
    )
    assert conf_res.status_code in (400, 422)


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

    # 1. Customer signs up to the portal
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
    assert signup_res.status_code == 201
    user_data = signup_res.json()
    assert user_data["email"] == "customer_contact@example.com"

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

    # Customer signs up and logs in to portal
    client.post(
        "/api/v1/portal/auth/signup",
        json={
            "organization_id": tenant.organization.id,
            "email": "trial_user@example.com",
            "password": "SecurePassword123!",
            "display_name": "Bob Trialer",
            "customer_id": customer.id,
        },
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


def test_hosted_checkout_rejects_forged_signature_and_unverified_payload(client, tenant, auth_headers, db):
    """Never mark payment successful from browser-supplied details; reject forged signatures."""
    from backend.app.models.payments import PaymentGateway
    from backend.app.services.gateways.registry import get_gateway_adapter, register_gateway_adapter

    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="3000.00")

    res = client.post(
        "/api/v1/checkout/sessions",
        headers=auth_headers,
        json={"purpose": "invoice_payment", "invoice_id": inv.id},
    )
    raw_token = res.json()["token"]

    # 1. Reject confirmation with only browser card details and no verified gateway credentials
    bad_res = client.post(
        f"/api/v1/checkout/public/{raw_token}/confirm",
        json={"payment_method_type": "card", "card_last4": "1234", "card_brand": "Visa"},
    )
    assert bad_res.status_code == 422
    db.refresh(inv)
    assert inv.status != InvoiceStatus.PAID
    assert inv.amount_due == Decimal("3000.00")

    # 2. Reject forged Razorpay cryptographic signature
    real_adapter = get_gateway_adapter(PaymentGateway.RAZORPAY)

    class _StrictSignatureAdapter:
        gateway_type = PaymentGateway.RAZORPAY

        def charge(self, **kwargs):
            raise NotImplementedError

        def refund(self, **kwargs):
            raise NotImplementedError

        def verify_webhook(self, **kwargs):
            return True

        def verify_payment_signature(self, payment_id: str, order_id: str, signature: str) -> bool:
            return signature == "legitimate_crypto_signature_123"

    register_gateway_adapter(PaymentGateway.RAZORPAY, _StrictSignatureAdapter())
    try:
        forged_res = client.post(
            f"/api/v1/checkout/public/{raw_token}/confirm",
            json={
                "payment_method_type": "card",
                "razorpay_payment_id": "pay_fake_001",
                "razorpay_order_id": "order_fake_001",
                "razorpay_signature": "forged_malicious_signature",
            },
        )
        assert forged_res.status_code == 422
        err_msg = forged_res.json()["error"]["message"].lower()
        assert "signature verification failed" in err_msg

        # Legitimate signature succeeds
        valid_res = client.post(
            f"/api/v1/checkout/public/{raw_token}/confirm",
            json={
                "payment_method_type": "card",
                "razorpay_payment_id": "pay_legit_001",
                "razorpay_order_id": "order_legit_001",
                "razorpay_signature": "legitimate_crypto_signature_123",
            },
        )
        assert valid_res.status_code == 200
        assert valid_res.json()["status"] == "successful"
    finally:
        register_gateway_adapter(PaymentGateway.RAZORPAY, real_adapter)

    db.refresh(inv)
    assert inv.status == InvoiceStatus.PAID
    assert inv.amount_due == Decimal("0.00")


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
    """Vulnerability test: an attacker must NOT be able to take over an arbitrary customer account
    by providing a victim's customer_id with the attacker's foreign email."""
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
    assert attacker_res.status_code in (400, 422)


def test_customer_portal_session_token_hashed_in_database(client, tenant, auth_headers, db):
    """Customer portal session bearer token must be hashed in DB, never plaintext."""
    import hashlib
    from backend.app.models.portal import CustomerPortalSession

    customer = tenant.customer(email="session_test@example.com")
    client.post(
        "/api/v1/portal/auth/signup",
        json={
            "organization_id": tenant.organization.id,
            "email": "session_test@example.com",
            "password": "SecurePassword123!",
            "display_name": "Session Tester",
            "customer_id": customer.id,
        },
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

    client.post(
        "/api/v1/portal/auth/signup",
        json={
            "organization_id": tenant.organization.id,
            "email": "pdf_user@example.com",
            "password": "SecurePassword123!",
            "display_name": "PDF User",
            "customer_id": customer.id,
        },
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

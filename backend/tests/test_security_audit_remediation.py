"""Comprehensive security tests proving defense-in-depth controls across OWASP ASVS 5.0,
OWASP Top 10:2025, OWASP API Security Top 10, Multi-Tenant SaaS isolation,
Financial/Billing integrity, SSRF prevention, and payment verification.
"""
from datetime import date, datetime, timedelta, timezone
import hashlib
from decimal import Decimal
import logging
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.exceptions import EntityNotFoundError, ValidationAppError
from backend.app.core.network_security import assert_safe_url, is_safe_ip, is_safe_url
from backend.app.main import app
from backend.app.models.checkout import CheckoutSession, CheckoutSessionPurpose, CheckoutSessionStatus
from backend.app.models.identity import Organization, User, Membership, MemberRole, MembershipStatus
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.payments import Payment, PaymentMethod, PaymentStatus
from backend.app.schemas.checkout import CheckoutConfirmIn
from backend.app.schemas.common_refs import LineItemIn
from backend.app.services import checkout_service, invoice_service, payment_service
from backend.app.services.checkout_service import _is_safe_redirect_url


# ============================================================================
# PHASE 17 & 6: SSRF Protection Unit Tests
# ============================================================================

def test_ssrf_blocks_private_and_loopback_ips():
    assert is_safe_ip("127.0.0.1") is False
    assert is_safe_ip("127.0.0.2") is False
    assert is_safe_ip("10.0.0.1") is False
    assert is_safe_ip("172.16.0.1") is False
    assert is_safe_ip("192.168.1.1") is False
    assert is_safe_ip("169.254.169.254") is False  # Cloud metadata
    assert is_safe_ip("0.0.0.0") is False
    assert is_safe_ip("::1") is False


def test_ssrf_blocks_cloud_metadata_and_internal_hostnames():
    assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False
    assert is_safe_url("http://metadata.google.internal/computeMetadata/v1/") is False
    assert is_safe_url("http://localhost:8000/api/v1/health") is False
    assert is_safe_url("http://127.0.0.1:5432") is False
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("gopher://127.0.0.1:6379") is False
    assert is_safe_url("ftp://example.com/file") is False
    assert is_safe_url("//evil.com/phish") is False
    assert is_safe_url("/\\evil.com/phish") is False


def test_assert_safe_url_raises_validation_app_error():
    with pytest.raises(ValidationAppError) as exc_info:
        assert_safe_url("http://169.254.169.254/latest/meta-data/")
    assert "prohibited" in str(exc_info.value).lower() or "private" in str(exc_info.value).lower()


# ============================================================================
# PHASE 14 & 18: Open Redirect Prevention
# ============================================================================

def test_open_redirect_blocks_protocol_relative_and_malicious_schemes():
    assert _is_safe_redirect_url("//attacker.com/steal-token") is False
    assert _is_safe_redirect_url("/\\attacker.com/steal-token") is False
    assert _is_safe_redirect_url("javascript:alert(1)") is False
    assert _is_safe_redirect_url("data:text/html,<script>alert(1)</script>") is False
    assert _is_safe_redirect_url("https://example.com/thank-you") is True
    assert _is_safe_redirect_url("/invoices/complete") is True


# ============================================================================
# PHASE 18: Security Headers Verification
# ============================================================================

def test_security_headers_present(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "strict-origin-when-cross-origin" in resp.headers.get("Referrer-Policy", "")
    assert "Content-Security-Policy" in resp.headers
    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp


# ============================================================================
# PHASE 22: Sensitive Data Logging Redaction
# ============================================================================

def test_sensitive_data_filter_redacts_tokens_and_passwords():
    from backend.app.core.logging import SensitiveDataFilter

    filt = SensitiveDataFilter()
    record = logging.LogRecord("test", logging.INFO, "test.py", 10, "User logged in with password: SecretPassword123! and token: abc", (), None)
    filt.filter(record)
    assert "SecretPassword123!" not in record.msg
    assert "[redacted]" in record.msg

    bearer_record = logging.LogRecord("test", logging.INFO, "test.py", 11, "Request with Authorization Bearer eyJhbGciOiJIUzI1NiJ9abcdefgh1234567890", (), None)
    filt.filter(bearer_record)
    assert "eyJhbGciOiJIUzI1NiJ9" not in bearer_record.msg
    assert "Bearer [redacted]" in bearer_record.msg


# ============================================================================
# PHASE 11 & 6: Line Item Numeric Overflow Protection
# ============================================================================

def test_line_item_overflow_validation():
    # Valid quantities and prices succeed
    item = LineItemIn(description="Consulting", quantity=Decimal("10"), unit_price=Decimal("150.00"))
    assert item.quantity == Decimal("10")

    # Quantities exceeding max database precision fail validation gracefully (422) instead of 500 DB crash
    with pytest.raises(Exception):
        LineItemIn(description="Overflow", quantity=Decimal("1000000000000000000000000"), unit_price=Decimal("100.00"))

    with pytest.raises(Exception):
        LineItemIn(description="Overflow", quantity=Decimal("1"), unit_price=Decimal("1000000000000000000000000"))


# ============================================================================
# PHASE 3: Password Reset Token Suppression in Production
# ============================================================================

def test_forgot_password_does_not_leak_reset_link_in_production(db, monkeypatch):
    from backend.app.services import auth_service

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SMTP_HOST", "")  # Email disabled

    # Create dummy user
    user = User(email="sec_audit_user@example.com", full_name="Audit User", is_active=True)
    db.add(user)
    db.commit()

    # forgot_password returns only the generic message: the link is never part of the result.
    message = auth_service.forgot_password(db, user.email, "127.0.0.1", "test-agent")
    assert isinstance(message, str) and "reset-password" not in message
    assert "If an account exists" in message


# ============================================================================
# PHASE 4 & 5: Cross-Tenant User Avatar BOLA Protection
# ============================================================================

def test_cross_tenant_user_avatar_access_rejected(db):
    from backend.app.api.v1.endpoints import users as user_endpoints
    from backend.app.api.deps import CurrentContext

    # Org 1 with User 1
    org1 = Organization(name="Tenant Alpha", slug="tenant-alpha")
    db.add(org1)
    db.flush()
    user1 = User(email="user1@alpha.com", full_name="User Alpha", is_active=True)
    db.add(user1)
    db.flush()
    m1 = Membership(organization_id=org1.id, user_id=user1.id, role=MemberRole.VIEWER, status=MembershipStatus.ACTIVE)
    db.add(m1)

    # Org 2 with User 2
    org2 = Organization(name="Tenant Beta", slug="tenant-beta")
    db.add(org2)
    db.flush()
    user2 = User(email="user2@beta.com", full_name="User Beta", is_active=True, avatar_url="/uploads/avatars/beta.png")
    db.add(user2)
    db.flush()
    m2 = Membership(organization_id=org2.id, user_id=user2.id, role=MemberRole.VIEWER, status=MembershipStatus.ACTIVE)
    db.add(m2)
    db.commit()

    ctx1 = CurrentContext(user=user1, organization=org1, membership=m1, ip_address="127.0.0.1", user_agent="test")

    # Calling get_user_avatar with user2's ID from user1's context must raise EntityNotFoundError
    with pytest.raises(EntityNotFoundError):
        user_endpoints.get_user_avatar(user_id=user2.id, ctx=ctx1, db=db)


# ============================================================================
# PHASE 12: Payment Order & Invoice Association Guard
# ============================================================================

def test_verify_razorpay_payment_rejects_mismatched_invoice(db):
    from backend.app.api.v1.endpoints import public_invoices
    from backend.app.schemas.public import RazorpayVerifyIn
    from backend.app.models.customers import Customer

    org = Organization(name="Test Org", slug="test-org-inv")
    db.add(org)
    db.flush()
    cust = Customer(organization_id=org.id, customer_number="CUST-1", display_name="Test Customer")
    db.add(cust)
    db.flush()

    # Invoice A
    inv_a = Invoice(
        organization_id=org.id,
        invoice_number="INV-A",
        customer_id=cust.id,
        status=InvoiceStatus.SENT,
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        total=Decimal("100.00"),
        amount_paid=Decimal("0.00"),
        amount_due=Decimal("100.00"),
        public_token="token_a_12345",
    )
    # Invoice B
    inv_b = Invoice(
        organization_id=org.id,
        invoice_number="INV-B",
        customer_id=cust.id,
        status=InvoiceStatus.SENT,
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        total=Decimal("50000.00"),
        amount_paid=Decimal("0.00"),
        amount_due=Decimal("50000.00"),
        public_token="token_b_67890",
    )
    db.add_all([inv_a, inv_b])
    db.flush()

    # Payment order was created for Invoice A
    payment = Payment(
        organization_id=org.id,
        payment_number="PAY-1",
        customer_id=cust.id,
        amount=Decimal("100.00"),
        currency="INR",
        method=PaymentMethod.RAZORPAY,
        status=PaymentStatus.PENDING,
        gateway_order_id="order_A_9999",
        gateway_payload={"notes": {"invoice_id": inv_a.id}},
    )
    db.add(payment)
    db.commit()

    # Attempting to verify order_A against Invoice B must be rejected with ValidationAppError
    from starlette.requests import Request
    scope = {
        "type": "http",
        "method": "POST",
        "path": f"/api/v1/public-invoices/{inv_b.public_token}/razorpay-verify",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345),
    }
    dummy_req = Request(scope)

    body = RazorpayVerifyIn(
        razorpay_order_id="order_A_9999",
        razorpay_payment_id="pay_A_1111",
        razorpay_signature="sig_A_mock",
    )
    with pytest.raises(ValidationAppError) as exc_info:
        public_invoices.verify_razorpay_payment(dummy_req, inv_b.public_token, body, db=db)
    assert "does not belong to this invoice" in str(exc_info.value).lower()


# ============================================================================
# PHASE 12: Checkout Session Order ID Mismatch Guard
# ============================================================================

def test_confirm_checkout_payment_rejects_tampered_order_id(db):
    from backend.app.models.customers import Customer
    org = Organization(name="Test Org", slug="test-org-chk")
    db.add(org)
    db.flush()

    cust = Customer(organization_id=org.id, customer_number="CUST-CHK", display_name="Test Customer")
    db.add(cust)
    db.flush()

    inv = Invoice(
        organization_id=org.id,
        invoice_number="INV-CHK",
        customer_id=cust.id,
        status=InvoiceStatus.SENT,
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        total=Decimal("500.00"),
        amount_paid=Decimal("0.00"),
        amount_due=Decimal("500.00"),
        public_token="token_chk_123",
    )
    db.add(inv)
    db.flush()

    session = CheckoutSession(
        organization_id=org.id,
        # Only the SHA-256 of the bearer token is stored (and matched).
        token=hashlib.sha256(b"test_hash_tok").hexdigest(),
        customer_id=cust.id,
        invoice_id=inv.id,
        purpose=CheckoutSessionPurpose.INVOICE_PAYMENT,
        status=CheckoutSessionStatus.CREATED,
        amount=Decimal("500.00"),
        currency="INR",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        metadata_snapshot={"gateway_order_id": "order_legit_123"},
    )
    db.add(session)
    db.commit()

    # Submit with an order ID that differs from session's expected order ID
    confirm_in = CheckoutConfirmIn(
        gateway="razorpay",
        razorpay_payment_id="pay_999",
        razorpay_order_id="order_tampered_888",
        razorpay_signature="sig_mock",
    )

    with pytest.raises(ValidationAppError) as exc_info:
        checkout_service.confirm_checkout_payment(db, "test_hash_tok", confirm_in)
    assert "order id does not match" in str(exc_info.value).lower()


# ============================================================================
# PHASE 13: Webhook Payment Amount and Currency Verification
# ============================================================================

def test_webhook_payment_captured_rejects_amount_mismatch(db):
    from backend.app.api.v1.endpoints import webhooks
    from backend.app.models import WebhookEvent

    org = Organization(name="Test Org", slug="test-org-wh")
    db.add(org)
    db.flush()

    payment = Payment(
        organization_id=org.id,
        payment_number="PAY-WH-1",
        amount=Decimal("1000.00"),
        currency="INR",
        method=PaymentMethod.RAZORPAY,
        status=PaymentStatus.PENDING,
        gateway_order_id="order_wh_123",
    )
    db.add(payment)
    db.commit()

    event = WebhookEvent(provider="razorpay", event_id="evt_1", event_type="payment.captured")
    # Entity claims payment was captured for 100 paise (Rs 1.00) instead of expected Rs 1000.00
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_wh_captured",
                    "order_id": "order_wh_123",
                    "amount": 100,  # Rs 1.00
                    "currency": "INR",
                }
            }
        },
    }

    with pytest.raises(ValueError) as exc_info:
        webhooks._handle_payment_captured(db, event, payload)
    assert "amount mismatch" in str(exc_info.value).lower()

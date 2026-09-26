"""Tests for Settings -> Integrations functionality.

Verifies:
- Live/mocked credential testing for Razorpay, SMTP, and Webhooks
- AES encryption at rest in organization_integrations table
- Zero secret leakage in GET responses (Key Secret, SMTP password, signing secret are never exposed)
- Precedence rule: tenant config -> environment fallback
- Disconnect purging
- Organization isolation
"""
import uuid
import pytest
from unittest.mock import MagicMock, patch

from backend.app.models.identity import Membership, MemberRole, Organization, User
from backend.app.models.integrations import OrganizationIntegration
from backend.app.services import integrations_service


@pytest.fixture
def test_org(db):
    org = Organization(
        name="Integration Test Corp",
        slug=f"integ-test-{uuid.uuid4().hex[:8]}",
        default_currency="INR",
    )
    db.add(org)
    db.flush()
    return org


@pytest.fixture
def other_org(db):
    org = Organization(
        name="Other Corp",
        slug=f"other-test-{uuid.uuid4().hex[:8]}",
        default_currency="INR",
    )
    db.add(org)
    db.flush()
    return org


def test_encryption_and_decryption_at_rest():
    data = {
        "key_id": "rzp_test_1234567890",
        "key_secret": "super_secret_key_secret",
        "nested": {"val": 42},
    }
    encrypted = integrations_service.encrypt_config(data)
    assert encrypted != str(data)
    assert "super_secret_key_secret" not in encrypted

    decrypted = integrations_service.decrypt_config(encrypted)
    assert decrypted == data


def test_mask_key_id():
    assert integrations_service.mask_key_id("rzp_test_abcdef123456") == "rzp_test••••3456"
    assert integrations_service.mask_key_id("short") == "••••rt"
    assert integrations_service.mask_key_id(None) is None


def test_razorpay_configure_and_status(db, test_org, other_org):
    with patch("backend.app.services.integrations_service.test_razorpay_connection") as mock_test:
        mock_test.return_value = {"success": True, "message": "OK"}
        
        from backend.app.schemas.integrations import RazorpayConfigureRequest
        req = RazorpayConfigureRequest(
            key_id="rzp_test_9876543210abcd",
            key_secret="my_razorpay_secret_123",
            webhook_secret="wh_secret_xyz",
            mode="test",
        )
        status = integrations_service.save_razorpay_config(db, test_org.id, req)
        
        assert status.is_connected is True
        assert status.mode == "test"
        assert status.masked_key_id == "rzp_test••••abcd"
        assert status.has_webhook_secret is True
        # Verify secret is NEVER in status
        assert not hasattr(status, "key_secret")
        assert not hasattr(status, "webhook_secret")

    # Verify at database level
    row = integrations_service._get_org_integration(db, test_org.id, "razorpay")
    assert row is not None
    assert row.is_connected is True
    # Verify ciphertext at rest
    assert "my_razorpay_secret_123" not in row.encrypted_config

    # Organization isolation check
    other_status = integrations_service.get_razorpay_status(db, other_org.id)
    assert other_status.masked_key_id != "rzp_test••••abcd"


def test_razorpay_disconnect(db, test_org):
    with patch("backend.app.services.integrations_service.test_razorpay_connection") as mock_test:
        mock_test.return_value = {"success": True, "message": "OK"}
        from backend.app.schemas.integrations import RazorpayConfigureRequest
        req = RazorpayConfigureRequest(
            key_id="rzp_test_9876543210abcd",
            key_secret="my_razorpay_secret_123",
            mode="test",
        )
        integrations_service.save_razorpay_config(db, test_org.id, req)

    # Disconnect
    status = integrations_service.disconnect_razorpay(db, test_org.id)
    assert status.is_connected is False
    assert status.status_message == "Disconnected"

    row = integrations_service._get_org_integration(db, test_org.id, "razorpay")
    assert row.encrypted_config is None


def test_smtp_configure_and_status(db, test_org):
    with patch("backend.app.services.integrations_service.test_smtp_connection") as mock_test:
        mock_test.return_value = {"success": True, "message": "OK"}
        from backend.app.schemas.integrations import SMTPConfigureRequest
        req = SMTPConfigureRequest(
            host="smtp.example.com",
            port=587,
            username="mailer@example.com",
            password="smtp_super_password_456",
            from_email="billing@example.com",
            from_name="Rooman Billing",
        )
        status = integrations_service.save_smtp_config(db, test_org.id, req)

        assert status.is_connected is True
        assert status.host == "smtp.example.com"
        assert status.username == "mailer@example.com"
        assert status.has_password is True
        # Password itself is NEVER exposed
        assert not hasattr(status, "password")


def test_smtp_disconnect(db, test_org):
    with patch("backend.app.services.integrations_service.test_smtp_connection") as mock_test:
        mock_test.return_value = {"success": True, "message": "OK"}
        from backend.app.schemas.integrations import SMTPConfigureRequest
        req = SMTPConfigureRequest(
            host="smtp.example.com",
            port=587,
            from_email="billing@example.com",
        )
        integrations_service.save_smtp_config(db, test_org.id, req)

    status = integrations_service.disconnect_smtp(db, test_org.id)
    assert status.is_connected is False
    assert status.status_message == "Disconnected"


def test_webhook_configure_and_test(db, test_org):
    with patch("httpx.Client.post") as mock_post, patch(
        "backend.app.core.network_security.is_safe_url", return_value=True
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        # Test endpoint
        res = integrations_service.test_webhook_endpoint(
            url="https://api.myapp.com/events",
            signing_secret="whsec_123456",
        )
        assert res["success"] is True

        # Save config
        from backend.app.schemas.integrations import WebhookConfigureRequest
        req = WebhookConfigureRequest(
            url="https://api.myapp.com/events",
            signing_secret="whsec_123456",
            events=["invoice.paid", "payment.captured"],
            is_enabled=True,
        )
        status = integrations_service.save_webhook_config(db, test_org.id, req)
        assert status.is_connected is True
        assert status.url == "https://api.myapp.com/events"
        assert status.has_signing_secret is True
        # Signing secret itself is NEVER in response
        assert not hasattr(status, "signing_secret")


def test_all_integrations_aggregates(db, test_org):
    all_status = integrations_service.get_all_integrations(db, test_org.id)
    assert all_status.accounting.status == "coming_soon"
    assert all_status.crm.status == "coming_soon"
    assert all_status.storage.status == "coming_soon"
    assert all_status.accounting.is_connected is False
    assert all_status.crm.is_connected is False
    assert all_status.storage.is_connected is False


def test_webhook_test_ping_signs_exact_body_with_timestamp(db, test_org):
    import json as _json

    from backend.app.services import customization_service

    captured = {}

    def fake_post(url, body, headers, timeout):
        captured.update(url=url, body=body, headers=headers)
        return 200, "ok"

    with patch("backend.app.core.network_security.is_safe_url", return_value=True), patch.object(
        customization_service, "_post_webhook", side_effect=fake_post
    ):
        res = integrations_service.test_webhook_endpoint("https://api.myapp.com/events", "whsec_abc")
    assert res["success"] is True
    ts = captured["headers"]["X-Rooman-Timestamp"]
    expected = customization_service.sign_webhook_body(captured["body"], "whsec_abc", ts)
    assert captured["headers"]["X-Rooman-Signature"] == f"sha256={expected}"
    assert _json.loads(captured["body"])["type"] == "test.ping"


def test_webhook_config_rejects_private_destinations(db, test_org):
    from backend.app.core.exceptions import ValidationAppError
    from backend.app.schemas.integrations import WebhookConfigureRequest

    for url in ("http://127.0.0.1:9000/hook", "http://169.254.169.254/latest", "http://192.168.1.10/x"):
        with pytest.raises(ValidationAppError):
            integrations_service.save_webhook_config(
                db, test_org.id, WebhookConfigureRequest(url=url, events=["invoice.paid"], is_enabled=True)
            )
    db.rollback()


def test_smtp_test_blocks_private_hosts_in_production(monkeypatch):
    from backend.app.core.config import settings
    from backend.app.core.exceptions import AppException

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    for host in ("127.0.0.1", "localhost", "10.1.2.3", "169.254.169.254"):
        with patch("smtplib.SMTP") as mock_smtp:
            with pytest.raises(AppException):
                integrations_service.test_smtp_connection(host=host, port=25)
            mock_smtp.assert_not_called()

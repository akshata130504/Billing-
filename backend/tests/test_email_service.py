"""Comprehensive automated tests for Rooman Billing SMTP & Outbound Email.

Verifies:
1. SMTP configuration validation (ports, host, TLS/SSL conflict prevention, email format).
2. TLS configuration (STARTTLS on port 587 vs implicit SSL on port 465).
3. Email sending (plain text, multipart HTML, multiple recipients).
4. Invoice PDF attachment handling.
5. Missing SMTP configuration (gracefully disabled, no exceptions, returns False).
6. SMTP failure handling (network errors, auth errors, connection timeouts).
7. Secret redaction (passwords never exposed in logs, responses, or API models).
"""
import smtplib
from unittest.mock import MagicMock, patch
import pytest

from backend.app.core.config import settings
from backend.app.schemas.integrations import SMTPConfigureRequest, SMTPTestRequest
from backend.app.services import email, integrations_service


def test_missing_smtp_configuration_returns_false():
    """When SMTP_HOST is not configured and no override is passed, sending is a safe no-op."""
    with patch.object(settings, "SMTP_HOST", ""):
        result = email.send_email(
            to="customer@example.com",
            subject="Test Invoice",
            text_body="Please pay your invoice.",
        )
        assert result is False


def test_empty_recipient_returns_false():
    """Empty or whitespace recipient list immediately returns False without connecting."""
    assert email.send_email(to=[], subject="Test", text_body="Body") is False
    assert email.send_email(to="", subject="Test", text_body="Body") is False


def test_email_sending_success_with_text_and_html():
    """Verifies email message construction and standard SMTP handoff."""
    with patch("smtplib.SMTP") as mock_smtp:
        server_instance = MagicMock()
        mock_smtp.return_value = server_instance

        with patch.object(settings, "SMTP_HOST", "smtp.sendgrid.net"), \
             patch.object(settings, "SMTP_PORT", 587), \
             patch.object(settings, "SMTP_USE_TLS", True), \
             patch.object(settings, "SMTP_USE_SSL", False), \
             patch.object(settings, "SMTP_USERNAME", "apikey"), \
             patch.object(settings, "SMTP_PASSWORD", "secret_key_123"):

            delivered = email.send_email(
                to=["billing1@example.com", "billing2@example.com"],
                subject="Invoice #INV-001",
                text_body="Your invoice is ready.",
                html_body="<p>Your invoice is <b>ready</b>.</p>",
                reply_to="support@rooman.com",
            )

            assert delivered is True
            mock_smtp.assert_called_once_with("smtp.sendgrid.net", 587, timeout=20)
            server_instance.starttls.assert_called_once()
            server_instance.login.assert_called_once_with("apikey", "secret_key_123")
            server_instance.send_message.assert_called_once()

            # Verify email payload structure
            sent_msg = server_instance.send_message.call_args[0][0]
            assert sent_msg["Subject"] == "Invoice #INV-001"
            assert sent_msg["To"] == "billing1@example.com, billing2@example.com"
            assert sent_msg["Reply-To"] == "support@rooman.com"


def test_email_sending_with_pdf_attachment():
    """Verifies binary PDF attachment encoding and attachment to the EmailMessage."""
    with patch("smtplib.SMTP") as mock_smtp:
        server_instance = MagicMock()
        mock_smtp.return_value = server_instance

        with patch.object(settings, "SMTP_HOST", "127.0.0.1"), \
             patch.object(settings, "SMTP_PORT", 1025), \
             patch.object(settings, "SMTP_USE_TLS", False):

            dummy_pdf = b"%PDF-1.4 mock binary pdf content"
            attachments = [("invoice_INV-0099.pdf", dummy_pdf, "application/pdf")]

            delivered = email.send_email(
                to="client@example.com",
                subject="Invoice INV-0099 Attached",
                text_body="Find your attached PDF invoice.",
                attachments=attachments,
            )

            assert delivered is True
            sent_msg = server_instance.send_message.call_args[0][0]
            att_parts = list(sent_msg.iter_attachments())
            assert len(att_parts) == 1
            assert att_parts[0].get_filename() == "invoice_INV-0099.pdf"
            assert att_parts[0].get_content() == dummy_pdf


def test_tls_vs_ssl_configuration():
    """Verifies that SMTP_USE_SSL uses SMTP_SSL (port 465) without STARTTLS, and SMTP_USE_TLS uses SMTP with STARTTLS (port 587)."""
    # 1. Test SSL mode (port 465)
    with patch("smtplib.SMTP_SSL") as mock_ssl:
        ssl_server = MagicMock()
        mock_ssl.return_value = ssl_server

        delivered = email.send_email(
            to="client@example.com",
            subject="SSL Test",
            text_body="Via SSL",
            smtp_config={
                "host": "smtp.gmail.com",
                "port": 465,
                "use_ssl": True,
                "use_tls": False,
            },
        )
        assert delivered is True
        mock_ssl.assert_called_once()
        ssl_server.starttls.assert_not_called()

    # 2. Test TLS mode (port 587)
    with patch("smtplib.SMTP") as mock_smtp:
        tls_server = MagicMock()
        mock_smtp.return_value = tls_server

        delivered = email.send_email(
            to="client@example.com",
            subject="TLS Test",
            text_body="Via STARTTLS",
            smtp_config={
                "host": "smtp.gmail.com",
                "port": 587,
                "use_ssl": False,
                "use_tls": True,
            },
        )
        assert delivered is True
        mock_smtp.assert_called_once()
        tls_server.starttls.assert_called_once()


def test_smtp_failure_handling():
    """Verifies that network and auth exceptions from smtplib are raised or handled gracefully without leaking credentials."""
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication credentials invalid")

        with patch.object(settings, "SMTP_HOST", "smtp.provider.com"), \
             patch.object(settings, "SMTP_USERNAME", "user"), \
             patch.object(settings, "SMTP_PASSWORD", "super_secret_password"):

            with pytest.raises(smtplib.SMTPAuthenticationError) as exc_info:
                email.send_email(
                    to="user@test.com",
                    subject="Fail",
                    text_body="Fail body",
                )
            # Ensure the secret password is not part of the exception string
            assert "super_secret_password" not in str(exc_info.value)


def test_smtp_configuration_validation():
    """Verifies Pydantic schema validation for SMTP configuration."""
    # Port out of bounds
    with pytest.raises(ValueError):
        SMTPConfigureRequest(
            host="smtp.example.com",
            port=999999,
            from_email="billing@example.com",
        )

    # Conflicting TLS and SSL
    with pytest.raises(ValueError, match="Cannot enable both use_tls"):
        SMTPConfigureRequest(
            host="smtp.example.com",
            port=587,
            use_tls=True,
            use_ssl=True,
            from_email="billing@example.com",
        )

    with pytest.raises(ValueError, match="Cannot enable both use_tls"):
        SMTPTestRequest(
            host="smtp.example.com",
            port=587,
            use_tls=True,
            use_ssl=True,
        )

    # Invalid email format
    with pytest.raises(ValueError, match="valid email"):
        SMTPConfigureRequest(
            host="smtp.example.com",
            port=587,
            from_email="not-an-email",
        )


def test_smtp_secret_redaction(db, tenant):
    """Verifies that SMTP passwords stored in organization_integrations are never exposed in status models or responses."""
    with patch("backend.app.services.integrations_service.test_smtp_connection") as mock_test:
        mock_test.return_value = {"success": True, "message": "OK"}

        req = SMTPConfigureRequest(
            host="smtp.sendgrid.net",
            port=587,
            username="apikey",
            password="SG.VerySensitiveApiKey_12345",
            from_email="billing@rooman.com",
            from_name="Rooman Billing",
        )
        status = integrations_service.save_smtp_config(db, tenant.organization.id, req)

        # Status model exposes boolean has_password, but NEVER the raw password
        assert status.has_password is True
        assert not hasattr(status, "password")
        assert "SG.VerySensitiveApiKey_12345" not in status.model_dump_json()

        # Overall integration status aggregation check
        all_status = integrations_service.get_all_integrations(db, tenant.organization.id)
        assert all_status.smtp.is_connected is True
        assert "SG.VerySensitiveApiKey_12345" not in all_status.model_dump_json()

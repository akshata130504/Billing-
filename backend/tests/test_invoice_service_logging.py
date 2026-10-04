"""Best-effort lookups in invoice_service must log (not silently swallow) failures
while keeping their fallback behaviour."""
from __future__ import annotations

import logging

from backend.app.core.tenant_context import tenant_context
from backend.app.models.invoices import InvoiceStatus
from backend.app.services import invoice_service


def test_email_invoice_logs_tenant_smtp_lookup_failure_and_uses_platform_smtp(tenant, db, monkeypatch, caplog):
    customer = tenant.customer()
    invoice = tenant.invoice(customer, amount="500.00", status=InvoiceStatus.SENT)

    def broken_lookup(*args, **kwargs):
        raise RuntimeError("integrations table unavailable")

    monkeypatch.setattr(
        "backend.app.services.integrations_service.get_active_smtp_credentials", broken_lookup
    )
    sent = {}

    def fake_send_email(recipient, subject, body, **kwargs):
        sent["recipient"] = recipient
        sent["smtp_config"] = kwargs.get("smtp_config")
        return True

    monkeypatch.setattr(invoice_service, "send_email", fake_send_email)

    with caplog.at_level(logging.WARNING, logger="rooman_billing"), tenant_context(tenant.organization.id):
        assert invoice_service.email_invoice(db, invoice, attach_pdf=False) is True

    # Fallback unchanged: no tenant SMTP config, so the platform SMTP settings are used.
    assert sent["recipient"] == customer.email
    assert sent["smtp_config"] is None
    records = [r for r in caplog.records if "Tenant SMTP lookup failed" in r.getMessage()]
    assert records, caplog.text
    assert records[0].levelno == logging.WARNING
    assert "platform SMTP" in records[0].getMessage()
    assert records[0].exc_info is not None


def test_serialize_invoice_logs_pending_approval_lookup_failure(tenant, db, monkeypatch, caplog):
    from backend.app.models import governance

    customer = tenant.customer()
    invoice = tenant.invoice(customer, amount="750.00", status=InvoiceStatus.SENT)
    # Make the optional pending-approval query blow up inside its try block.
    monkeypatch.setattr(governance, "ApprovalStatus", object())

    with caplog.at_level(logging.WARNING, logger="rooman_billing"), tenant_context(tenant.organization.id):
        data = invoice_service.serialize_invoice(invoice)

    assert data["approval_request_id"] is None
    assert data["is_pending_approval"] is False
    records = [r for r in caplog.records if "Pending-approval lookup failed" in r.getMessage()]
    assert records, caplog.text
    assert records[0].exc_info is not None

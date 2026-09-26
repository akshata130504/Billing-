"""Characterization tests for Invoice lifecycle and public access."""
from datetime import date, timedelta
from decimal import Decimal
import uuid
import pytest

from backend.app.models import AuditLog, Invoice, InvoiceStatus

BASE = "/api/v1/invoices"
PUBLIC = "/api/v1/public/invoices"


def _invoice_items():
    return [
        {"description": "Design Consultation", "quantity": "2", "unit_price": "2500.00", "tax_rate_pct": "18"},
        {"description": "Hosting", "quantity": "1", "unit_price": "1000.00", "tax_rate_pct": "18"},
    ]


def _create_draft_invoice(client, auth_headers, customer, **overrides):
    body = {
        "customer_id": customer.id,
        "issue_date": date.today().isoformat(),
        "due_date": (date.today() + timedelta(days=15)).isoformat(),
        "items": _invoice_items(),
        "discount_pct": "10",
        "notes": "Payment due within 15 days",
    }
    body.update(overrides)
    resp = client.post(BASE, json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_draft_invoice_calculates_totals(client, tenant, auth_headers):
    customer = tenant.customer()
    inv = _create_draft_invoice(client, auth_headers, customer)

    assert inv["status"] == "draft"
    assert inv["invoice_number"].startswith("INV-")
    assert inv["customer"]["id"] == customer.id
    # subtotal: (2 * 2500) + 1000 = 6000.00
    # discount: 10% = 600.00
    # taxable: 5400.00, tax 18% = 972.00
    # total: 6372.00
    assert inv["subtotal"] == "6000.00"
    assert inv["discount_amount"] == "600.00"
    assert inv["tax_amount"] == "972.00"
    assert inv["total"] == "6372.00"
    assert inv["amount_paid"] == "0.00"
    assert inv["amount_due"] == "6372.00"
    assert inv["public_url"] is not None


def test_send_and_access_public_invoice(client, tenant, auth_headers):
    customer = tenant.customer()
    inv = _create_draft_invoice(client, auth_headers, customer)
    inv_id = inv["id"]

    # Send invoice
    send_resp = client.post(f"{BASE}/{inv_id}/send", headers=auth_headers)
    assert send_resp.status_code == 200, send_resp.text
    sent_inv = send_resp.json()
    assert sent_inv["status"] == "sent"
    assert sent_inv["public_url"] is not None
    # No SMTP configured for this org (test default) - nothing to warn about.
    assert sent_inv["email_delivery_failed"] is False

    # Public token access (without auth)
    public_token = sent_inv["public_url"].split("/")[-1]
    pub_resp = client.get(f"{PUBLIC}/{public_token}")
    assert pub_resp.status_code == 200
    pub_data = pub_resp.json()
    assert pub_data["invoice_number"] == sent_inv["invoice_number"]
    assert pub_data["total"] == sent_inv["total"]


def test_send_invoice_flags_email_delivery_failure_when_smtp_configured(client, tenant, auth_headers, db):
    """The invoice still transitions to SENT even if the email itself fails, but the
    response must say so instead of implying delivery succeeded (see email_delivery_failed)."""
    from unittest.mock import patch
    from backend.app.schemas.integrations import SMTPConfigureRequest
    from backend.app.services import integrations_service

    with patch.object(integrations_service, "test_smtp_connection", return_value={"success": True, "message": "OK"}):
        integrations_service.save_smtp_config(
            db,
            tenant.organization.id,
            SMTPConfigureRequest(
                host="smtp.example.com",
                port=587,
                username="apikey",
                password="secret",
                from_email="billing@example.com",
            ),
        )

    customer = tenant.customer()
    inv = _create_draft_invoice(client, auth_headers, customer)

    with patch("backend.app.services.invoice_service.send_email", side_effect=OSError("connection refused")):
        send_resp = client.post(f"{BASE}/{inv['id']}/send", headers=auth_headers)

    assert send_resp.status_code == 200, send_resp.text
    sent_inv = send_resp.json()
    assert sent_inv["status"] == "sent"
    assert sent_inv["email_delivery_failed"] is True


def test_send_invoice_email_delivery_ok_when_smtp_configured_and_succeeds(client, tenant, auth_headers, db):
    from unittest.mock import patch
    from backend.app.schemas.integrations import SMTPConfigureRequest
    from backend.app.services import integrations_service

    with patch.object(integrations_service, "test_smtp_connection", return_value={"success": True, "message": "OK"}):
        integrations_service.save_smtp_config(
            db,
            tenant.organization.id,
            SMTPConfigureRequest(
                host="smtp.example.com",
                port=587,
                username="apikey",
                password="secret",
                from_email="billing@example.com",
            ),
        )

    customer = tenant.customer()
    inv = _create_draft_invoice(client, auth_headers, customer)

    with patch("backend.app.services.invoice_service.send_email", return_value=True):
        send_resp = client.post(f"{BASE}/{inv['id']}/send", headers=auth_headers)

    assert send_resp.status_code == 200, send_resp.text
    sent_inv = send_resp.json()
    assert sent_inv["status"] == "sent"
    assert sent_inv["email_delivery_failed"] is False


def test_record_offline_payment_and_pay_in_full(client, tenant, auth_headers):
    customer = tenant.customer()
    inv = _create_draft_invoice(client, auth_headers, customer)
    inv_id = inv["id"]

    # Send first
    client.post(f"{BASE}/{inv_id}/send", headers=auth_headers)

    # Record full payment
    pay_resp = client.post(
        f"{BASE}/{inv_id}/record-payment",
        json={
            "amount": inv["total"],
            "method": "bank_transfer",
            "reference": "WIRE-998877",
        },
        headers=auth_headers,
    )
    assert pay_resp.status_code == 201, pay_resp.text


    # Verify invoice is now paid
    inv_resp = client.get(f"{BASE}/{inv_id}", headers=auth_headers)
    assert inv_resp.status_code == 200
    updated_inv = inv_resp.json()
    assert updated_inv["status"] == "paid"
    assert updated_inv["amount_paid"] == inv["total"]
    assert updated_inv["amount_due"] == "0.00"


def test_void_invoice(client, tenant, auth_headers):
    customer = tenant.customer()
    inv = _create_draft_invoice(client, auth_headers, customer)
    inv_id = inv["id"]

    client.post(f"{BASE}/{inv_id}/send", headers=auth_headers)

    void_resp = client.post(
        f"{BASE}/{inv_id}/void",
        json={"reason": "Customer cancelled order"},
        headers=auth_headers,
    )
    assert void_resp.status_code == 200
    assert void_resp.json()["status"] == "void"


def test_download_invoice_pdf(client, tenant, auth_headers):
    customer = tenant.customer()
    inv = _create_draft_invoice(client, auth_headers, customer)
    inv_id = inv["id"]

    pdf_resp = client.get(f"{BASE}/{inv_id}/pdf", headers=auth_headers)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF")


def test_invoice_validation_errors(client, tenant, auth_headers):
    customer = tenant.customer()
    # Empty items
    resp = client.post(
        BASE,
        json={"customer_id": customer.id, "items": []},
        headers=auth_headers,
    )
    assert resp.status_code == 422

    # Non-existent customer
    resp = client.post(
        BASE,
        json={"customer_id": str(uuid.uuid4()), "items": _invoice_items()},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_invoices_summary_kpis(client, tenant, auth_headers):
    customer = tenant.customer()
    sum_resp = client.get(f"{BASE}/summary", headers=auth_headers)
    assert sum_resp.status_code == 200
    initial_summary = sum_resp.json()
    initial_total = initial_summary["total_invoices"]

    # Create a draft invoice
    inv = _create_draft_invoice(client, auth_headers, customer)
    sum_resp2 = client.get(f"{BASE}/summary", headers=auth_headers)
    assert sum_resp2.status_code == 200
    data = sum_resp2.json()
    assert data["total_invoices"] == initial_total + 1
    assert data["draft_count"] >= 1

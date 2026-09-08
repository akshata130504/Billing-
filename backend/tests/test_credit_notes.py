"""Tests for Credit Notes and Credit Applications (Phase 1)."""
from decimal import Decimal
import pytest

from backend.app.models.credits import CreditNoteStatus
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.services.credit_service import (
    apply_credit_note_to_invoice,
    create_credit_note,
    get_credit_note,
    list_credit_notes,
    void_credit_note,
)
from backend.app.core.exceptions import ConflictAppError, ValidationAppError


def test_credit_note_lifecycle_and_api(client, tenant, auth_headers, db):
    customer = tenant.customer()

    # 1. Create a credit note via API
    payload = {
        "customer_id": customer.id,
        "reason": "Service goodwill credit",
        "currency": "INR",
        "lines": [
            {"description": "Downtime compensation", "amount": 250.00},
            {"description": "Promo discount adjustment", "amount": 150.00},
        ],
    }
    resp = client.post("/api/v1/credit-notes", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    cn_data = resp.json()
    assert cn_data["credit_note_number"].startswith("CN-")
    assert cn_data["total"] == "400.00"
    assert cn_data["balance_remaining"] == "400.00"
    assert cn_data["status"] == CreditNoteStatus.ISSUED.value
    assert len(cn_data["lines"]) == 2
    cn_id = cn_data["id"]

    # 2. Get credit note by ID
    get_resp = client.get(f"/api/v1/credit-notes/{cn_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == cn_id

    # 3. List credit notes
    list_resp = client.get("/api/v1/credit-notes", headers=auth_headers)
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(item["id"] == cn_id for item in items)

    # 4. Create an open invoice for the same customer
    inv_resp = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": customer.id,
            "issue_date": "2026-09-01",
            "due_date": "2026-09-15",
            "items": [{"description": "Cloud Service", "quantity": "1", "unit_price": "500.00", "tax_rate_pct": "0"}],
        },
        headers=auth_headers,
    )
    assert inv_resp.status_code == 201
    inv_id = inv_resp.json()["id"]

    # Send invoice to open status
    send_resp = client.post(f"/api/v1/invoices/{inv_id}/send", headers=auth_headers)
    assert send_resp.status_code == 200

    # 5. Apply partial credit to invoice ($150 of $400)
    apply_resp = client.post(
        f"/api/v1/credit-notes/{cn_id}/apply",
        json={"invoice_id": inv_id, "amount": 150.00},
        headers=auth_headers,
    )
    assert apply_resp.status_code == 200
    updated_cn = apply_resp.json()
    assert updated_cn["balance_remaining"] == "250.00"
    assert len(updated_cn["applications"]) == 1
    assert updated_cn["applications"][0]["amount"] == "150.00"

    # Verify invoice remaining balance is decreased
    inv_get = client.get(f"/api/v1/invoices/{inv_id}", headers=auth_headers)
    assert inv_get.json()["amount_paid"] == "150.00"
    assert inv_get.json()["amount_due"] == "350.00"

    # 6. Cannot void already applied credit note
    void_resp = client.post(f"/api/v1/credit-notes/{cn_id}/void", headers=auth_headers)
    assert void_resp.status_code == 409

    # 7. Create a fresh unapplied credit note and void it
    payload2 = {
        "customer_id": customer.id,
        "reason": "Accidental issuance",
        "currency": "INR",
        "lines": [{"description": "Correction", "amount": 50.00}],
    }
    cn2_resp = client.post("/api/v1/credit-notes", json=payload2, headers=auth_headers)
    cn2_id = cn2_resp.json()["id"]

    void2_resp = client.post(f"/api/v1/credit-notes/{cn2_id}/void", headers=auth_headers)
    assert void2_resp.status_code == 200
    assert void2_resp.json()["status"] == CreditNoteStatus.VOID.value
    assert void2_resp.json()["balance_remaining"] == "0.00"

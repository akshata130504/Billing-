"""Characterization tests for Payment management, allocations, and refunds."""
from datetime import date
from decimal import Decimal
import uuid
import pytest

from backend.app.models import MemberRole

BASE = "/api/v1/payments"
INVOICES = "/api/v1/invoices"


def _create_sent_invoice(client, auth_headers, customer, amount="5000.00"):
    resp = client.post(
        INVOICES,
        json={
            "customer_id": customer.id,
            "items": [{"description": "Item", "quantity": "1", "unit_price": amount, "tax_rate_pct": "0"}],
            "discount_pct": "0",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    inv_id = resp.json()["id"]
    client.post(f"{INVOICES}/{inv_id}/send", headers=auth_headers)
    return inv_id, amount


def test_create_payment_with_allocation(client, tenant, auth_headers):
    customer = tenant.customer()
    inv_id, amount = _create_sent_invoice(client, auth_headers, customer, "2000.00")

    pay_resp = client.post(
        BASE,
        json={
            "customer_id": customer.id,
            "amount": "2000.00",
            "method": "bank_transfer",
            "reference": "TXN-12345",
            "allocations": [{"invoice_id": inv_id, "amount": "2000.00"}],
        },
        headers=auth_headers,
    )
    assert pay_resp.status_code == 201, pay_resp.text
    pay_data = pay_resp.json()
    assert pay_data["payment_number"].startswith("PAY-")
    assert pay_data["amount"] == "2000.00"
    assert pay_data["amount_allocated"] == "2000.00"
    assert pay_data["amount_unallocated"] == "0.00"
    assert pay_data["status"] == "succeeded"

    # Verify invoice status changed to paid
    inv_resp = client.get(f"{INVOICES}/{inv_id}", headers=auth_headers)
    assert inv_resp.status_code == 200
    assert inv_resp.json()["status"] == "paid"


def test_update_allocations(client, tenant, auth_headers):
    customer = tenant.customer()
    inv1_id, _ = _create_sent_invoice(client, auth_headers, customer, "1500.00")
    inv2_id, _ = _create_sent_invoice(client, auth_headers, customer, "1500.00")

    # Record unallocated payment
    pay_resp = client.post(
        BASE,
        json={
            "customer_id": customer.id,
            "amount": "2500.00",
            "method": "cheque",
            "reference": "CHQ-7788",
        },
        headers=auth_headers,
    )
    assert pay_resp.status_code == 201
    pay_id = pay_resp.json()["id"]
    assert pay_resp.json()["amount_unallocated"] == "2500.00"

    # Allocate across inv1 and inv2
    alloc_resp = client.put(
        f"{BASE}/{pay_id}/allocations",
        json={
            "allocations": [
                {"invoice_id": inv1_id, "amount": "1500.00"},
                {"invoice_id": inv2_id, "amount": "1000.00"},
            ]
        },
        headers=auth_headers,
    )
    assert alloc_resp.status_code == 200, alloc_resp.text
    alloc_data = alloc_resp.json()
    assert alloc_data["amount_allocated"] == "2500.00"
    assert alloc_data["amount_unallocated"] == "0.00"


def test_refund_payment(client, tenant, auth_headers):
    customer = tenant.customer()
    pay_resp = client.post(
        BASE,
        json={
            "customer_id": customer.id,
            "amount": "3000.00",
            "method": "bank_transfer",
            "reference": "TXN-REFUND-ME",
        },
        headers=auth_headers,
    )
    assert pay_resp.status_code == 201
    pay_id = pay_resp.json()["id"]

    # Owner has ADMIN role permissions to refund
    refund_resp = client.post(
        f"{BASE}/{pay_id}/refund",
        json={"amount": "1000.00", "reason": "Customer overpaid"},
        headers=auth_headers,
    )
    assert refund_resp.status_code == 200, refund_resp.text
    refund_data = refund_resp.json()
    assert refund_data["amount_refunded"] == "1000.00"
    assert len(refund_data["refunds"]) == 1


def test_reconciliation_summary(client, tenant, auth_headers):
    summary_resp = client.get(f"{BASE}/reconciliation/summary", headers=auth_headers)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert "matched" in summary
    assert "unmatched" in summary
    assert "total" in summary



def test_allocation_validation_prevent_over_allocation(client, tenant, auth_headers):
    customer = tenant.customer()
    inv_id, _ = _create_sent_invoice(client, auth_headers, customer, "1000.00")

    # Payment is 500, but try to allocate 1000
    resp = client.post(
        BASE,
        json={
            "customer_id": customer.id,
            "amount": "500.00",
            "method": "cash",
            "allocations": [{"invoice_id": inv_id, "amount": "1000.00"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422

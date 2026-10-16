"""Tests for customer payment methods vault and payment attempts tracking (Phase 1)."""
from decimal import Decimal

from backend.app.models.payments import (
    CustomerPaymentMethodStatus,
    PaymentAttemptStatus,
)


def test_customer_payment_methods_api(client, tenant, auth_headers):
    customer = tenant.customer()

    # 1. Add first payment method (should default to is_default=True)
    resp = client.post(
        f"/api/v1/customers/{customer.id}/payment-methods",
        json={
            "gateway": "razorpay",
            "gateway_token": "tok_visa_4242",
            "gateway_customer_id": "cust_rzp_123",
            "type": "card",
            "card_brand": "visa",
            "last4": "4242",
            "exp_month": 12,
            "exp_year": 2028,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    pm1 = resp.json()
    assert pm1["last4"] == "4242"
    assert pm1["is_default"] is True
    assert pm1["status"] == CustomerPaymentMethodStatus.ACTIVE.value
    pm1_id = pm1["id"]

    # 2. Add second payment method (not default)
    resp2 = client.post(
        f"/api/v1/customers/{customer.id}/payment-methods",
        json={
            "gateway": "razorpay",
            "gateway_token": "tok_mc_5555",
            "type": "card",
            "card_brand": "mastercard",
            "last4": "5555",
            "exp_month": 6,
            "exp_year": 2029,
            "is_default": False,
        },
        headers=auth_headers,
    )
    assert resp2.status_code == 201
    pm2 = resp2.json()
    assert pm2["is_default"] is False
    pm2_id = pm2["id"]

    # 3. List methods
    list_resp = client.get(f"/api/v1/customers/{customer.id}/payment-methods", headers=auth_headers)
    assert list_resp.status_code == 200
    pms = list_resp.json()
    assert len(pms) == 2

    # 4. Set pm2 as default
    set_def_resp = client.post(
        f"/api/v1/customers/{customer.id}/payment-methods/{pm2_id}/set-default",
        headers=auth_headers,
    )
    assert set_def_resp.status_code == 200
    assert set_def_resp.json()["is_default"] is True

    # Check pm1 is no longer default
    list_resp2 = client.get(f"/api/v1/customers/{customer.id}/payment-methods", headers=auth_headers)
    pms2 = {p["id"]: p for p in list_resp2.json()}
    assert pms2[pm2_id]["is_default"] is True
    assert pms2[pm1_id]["is_default"] is False

    # 5. Revoke pm1
    del_resp = client.delete(
        f"/api/v1/customers/{customer.id}/payment-methods/{pm1_id}",
        headers=auth_headers,
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == CustomerPaymentMethodStatus.REVOKED.value


def test_payment_attempts_lifecycle(client, tenant, auth_headers, db):
    customer = tenant.customer()
    # Create and send invoice
    inv_resp = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": customer.id,
            "issue_date": "2026-09-01",
            "due_date": "2026-09-15",
            "items": [{"description": "SaaS Plan", "quantity": "1", "unit_price": "1200.00", "tax_rate_pct": "0"}],
        },
        headers=auth_headers,
    )
    assert inv_resp.status_code == 201
    inv_id = inv_resp.json()["id"]
    client.post(f"/api/v1/invoices/{inv_id}/send", headers=auth_headers)

    from backend.app.services.payment_method_service import (
        record_payment_attempt,
        update_payment_attempt,
    )

    # Record first attempt (failed)
    att1 = record_payment_attempt(
        db,
        organization_id=tenant.organization.id,
        invoice_id=inv_id,
        amount=Decimal("1200.00"),
    )
    assert att1.attempt_number == 1
    assert att1.status == PaymentAttemptStatus.CREATED

    update_payment_attempt(
        db,
        organization_id=tenant.organization.id,
        attempt_id=att1.id,
        status=PaymentAttemptStatus.FAILED,
        failure_reason="Insufficient funds",
        failure_category="card_error",
    )
    db.commit()

    # Record second attempt (succeeded)
    att2 = record_payment_attempt(
        db,
        organization_id=tenant.organization.id,
        invoice_id=inv_id,
        amount=Decimal("1200.00"),
    )
    assert att2.attempt_number == 2
    update_payment_attempt(
        db,
        organization_id=tenant.organization.id,
        attempt_id=att2.id,
        status=PaymentAttemptStatus.SUCCEEDED,
    )
    db.commit()

    # Query via API
    resp = client.get(f"/api/v1/invoices/{inv_id}/payment-attempts", headers=auth_headers)
    assert resp.status_code == 200
    attempts = resp.json()
    assert len(attempts) == 2
    assert attempts[0]["attempt_number"] == 1
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["failure_reason"] == "Insufficient funds"
    assert attempts[1]["attempt_number"] == 2
    assert attempts[1]["status"] == "succeeded"

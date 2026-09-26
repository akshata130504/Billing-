"""Operational alert hooks on webhook / gateway-payment / dunning failures.

send_alert is monkeypatched to capture calls; each test also renders the captured
alert through the real formatter to prove the delivered text carries no secrets,
tokens or card data and only masked identifiers."""
import hashlib
import hmac
import json
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.api.v1.endpoints import webhooks as webhooks_endpoint
from backend.app.core import alerts
from backend.app.core.config import settings
from backend.app.models.invoices import InvoiceStatus
from backend.app.models.payments import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    Payment,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.services import dunning_service

BASE = "/api/v1/webhooks/razorpay"
SECRET = "alert_hook_webhook_secret_value"
CARD = "4111 1111 1111 1111"


@pytest.fixture()
def captured(monkeypatch):
    calls = []

    def fake_send_alert(event, summary, details=None, severity="error", *, dedup_key=None):
        calls.append({"event": event, "summary": summary, "details": dict(details or {}), "severity": severity, "dedup_key": dedup_key})
        return True

    monkeypatch.setattr(alerts, "send_alert", fake_send_alert)
    monkeypatch.setattr(webhooks_endpoint, "send_alert", fake_send_alert)
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    return calls


def _rendered(call) -> str:
    return alerts._format(call["event"], call["summary"], call["details"], call["severity"], 0)


def _post(client, payload, event_id, *, valid=True):
    raw = json.dumps(payload).encode()
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest() if valid else "bad-signature"
    return client.post(
        BASE,
        content=raw,
        headers={"Content-Type": "application/json", "X-Razorpay-Event-Id": event_id, "X-Razorpay-Signature": sig},
    )


def _pending_payment(db, tenant, invoice):
    payment = Payment(
        organization_id=tenant.organization.id,
        payment_number=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        customer_id=invoice.customer_id,
        amount=invoice.amount_due,
        currency="INR",
        method=PaymentMethod.RAZORPAY,
        gateway=PaymentGateway.RAZORPAY,
        status=PaymentStatus.PENDING,
        gateway_order_id=f"order_{uuid.uuid4().hex[:14]}",
        gateway_payload={"notes": {"invoice_id": invoice.id, "organization_id": tenant.organization.id}},
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def test_signature_failure_burst_raises_one_critical_alert(client, captured):
    for _ in range(webhooks_endpoint.SIGNATURE_FAILURE_ALERT_THRESHOLD):
        assert _post(client, {"event": "payment.captured"}, f"evt_{uuid.uuid4().hex}", valid=False).status_code == 400
    burst = [c for c in captured if c["event"] == "payment.webhook_signature_failures"]
    assert burst, captured
    assert burst[-1]["severity"] == "critical"
    assert burst[-1]["details"]["count"] >= webhooks_endpoint.SIGNATURE_FAILURE_ALERT_THRESHOLD
    text = _rendered(burst[-1])
    assert SECRET not in text and "bad-signature" not in text


def test_permanent_webhook_processing_failure_alerts_with_masked_event_id(client, tenant, db, captured):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1000.00")
    payment = _pending_payment(db, tenant, inv)
    event_id = f"evt_{uuid.uuid4().hex}"
    payload = {
        "event": "payment.captured",
        "created_at": int(time.time()),
        "payload": {"payment": {"entity": {"id": f"pay_{uuid.uuid4().hex[:14]}", "order_id": payment.gateway_order_id,
                                           "amount": 1, "currency": "INR"}}},  # amount mismatch -> permanent
    }
    assert _post(client, payload, event_id).status_code == 200
    failed = [c for c in captured if c["event"] == "payment.webhook_failed"]
    assert len(failed) == 1
    details = failed[0]["details"]
    assert details["retryable"] is False and details["event_type"] == "payment.captured"
    assert details["event_id"] != event_id and event_id not in _rendered(failed[0])
    assert details["event_id"].startswith(event_id[:4])


def test_payment_failed_webhook_alerts_without_card_data(client, tenant, db, captured):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="700.00")
    payment = _pending_payment(db, tenant, inv)
    payload = {
        "event": "payment.failed",
        "payload": {"payment": {"entity": {
            "id": f"pay_{uuid.uuid4().hex[:14]}",
            "order_id": payment.gateway_order_id,
            "method": "card",
            "card": {"number": CARD},
            "error_description": f"Card {CARD} declined",
        }}},
    }
    assert _post(client, payload, f"evt_{uuid.uuid4().hex}").status_code == 200
    failed = [c for c in captured if c["event"] == "payment.failed"]
    assert len(failed) == 1
    details = failed[0]["details"]
    assert details["payment_number"] == payment.payment_number
    assert details["gateway_order"] != payment.gateway_order_id
    assert payment.gateway_order_id not in json.dumps(details)
    text = _rendered(failed[0])
    assert CARD not in text and CARD.replace(" ", "") not in text
    assert payment.gateway_order_id not in text


def test_dunning_charge_failure_alerts_with_masked_customer(tenant, db, captured):
    from backend.app.services.gateways.base import GatewayChargeResult
    from backend.app.services.gateways.registry import get_gateway_adapter, register_gateway_adapter

    customer = tenant.customer(email=f"billing-{uuid.uuid4().hex[:6]}@customer.example")
    _, plan = tenant.product_with_plan(unit_amount="1500.00")
    sub = Subscription(
        organization_id=tenant.organization.id,
        subscription_number=f"SUB-{uuid.uuid4().hex[:6].upper()}",
        customer_id=customer.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        quantity=1,
        start_date=date.today(),
        current_period_start=date.today(),
        current_period_end=date.today() + timedelta(days=30),
    )
    db.add(sub)
    db.commit()
    inv = tenant.invoice(customer, amount="1500.00", status=InvoiceStatus.SENT)
    case = dunning_service.trigger_dunning_for_failed_payment(
        db=db, organization_id=tenant.organization.id, invoice_id=inv.id, customer_id=customer.id,
        subscription_id=sub.id, reason="card_declined", payment_method_type="card",
    )
    db.commit()
    token = f"tok_secret_{uuid.uuid4().hex[:10]}"
    db.add(CustomerPaymentMethod(
        organization_id=tenant.organization.id, customer_id=customer.id, type="card",
        status=CustomerPaymentMethodStatus.ACTIVE, gateway="razorpay", gateway_token=token,
        last4="1111", card_brand="visa", exp_month=12, exp_year=2030, is_default=True,
    ))
    case.next_retry_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    class _Declining:
        gateway_type = PaymentGateway.RAZORPAY

        def charge(self, **kwargs):
            return GatewayChargeResult(success=False, error_message=f"Card {CARD} declined", error_category="card_declined")

        def refund(self, **kwargs):
            raise NotImplementedError

        def verify_webhook(self, **kwargs):
            return True

    real = get_gateway_adapter(PaymentGateway.RAZORPAY)
    register_gateway_adapter(PaymentGateway.RAZORPAY, _Declining())
    try:
        dunning_service.execute_dunning_retries(db, tenant.organization.id)
        db.commit()
    finally:
        register_gateway_adapter(PaymentGateway.RAZORPAY, real)

    failed = [c for c in captured if c["event"] == "payment.charge_failed"]
    assert len(failed) == 1, captured
    details = failed[0]["details"]
    assert details["invoice_number"] == inv.invoice_number
    assert details["error_category"] == "card_declined"
    assert details["customer"] and details["customer"] != customer.email
    text = _rendered(failed[0])
    assert customer.email not in text
    assert token not in text
    assert CARD not in text and CARD.replace(" ", "") not in text


def test_mask_identifier():
    assert webhooks_endpoint.mask_identifier("evt_1234567890abcdef") == "evt_…cdef"
    assert webhooks_endpoint.mask_identifier("short") == "…rt"
    assert webhooks_endpoint.mask_identifier(None) == ""

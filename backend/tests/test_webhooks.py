"""Characterization tests for inbound webhooks and event deduplication."""
from datetime import date, timedelta
import hashlib
import hmac
import json
import uuid
import pytest

from backend.app.core.config import settings
from backend.app.models import InvoiceStatus, WebhookEvent
from backend.app.models.dunning import DunningCase
from backend.app.models.payments import Payment, PaymentGateway, PaymentMethod, PaymentStatus
from backend.app.models.subscriptions import Subscription, SubscriptionStatus

BASE = "/api/v1/webhooks/razorpay"


SECRET = "test_webhook_secret_key_12345"


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _pending_razorpay_payment(db, tenant, invoice, order_id=None) -> Payment:
    """A Payment row exactly as POST /public/invoices/{token}/razorpay-order creates it."""
    payment = Payment(
        organization_id=tenant.organization.id,
        payment_number=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        customer_id=invoice.customer_id,
        amount=invoice.amount_due,
        currency=invoice.currency or "INR",
        method=PaymentMethod.RAZORPAY,
        gateway=PaymentGateway.RAZORPAY,
        status=PaymentStatus.PENDING,
        gateway_order_id=order_id or f"order_{uuid.uuid4().hex[:14]}",
        gateway_payload={"notes": {"invoice_id": invoice.id, "organization_id": tenant.organization.id}},
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def _renewal_subscription(db, tenant, customer, plan) -> Subscription:
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
    db.refresh(sub)
    return sub


def _payment_failed_payload(order_id: str, event_id: str, method: str = "card") -> tuple[bytes, dict]:
    payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{uuid.uuid4().hex[:14]}",
                    "order_id": order_id,
                    "method": method,
                    "error_description": "The card was declined by the issuing bank.",
                    "error_reason": "card_declined",
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Event-Id": event_id,
        "X-Razorpay-Signature": _sign(raw_body),
    }
    return raw_body, headers


def test_webhook_unhandled_event_type_acknowledged(client, monkeypatch, db):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    event_id = f"evt_{uuid.uuid4().hex}"
    payload = {
        "event": "unknown.event.type",
        "payload": {},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = _sign(raw_body)

    resp = client.post(
        BASE,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Event-Id": event_id,
            "X-Razorpay-Signature": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"received": True}

    # Verify event recorded with ignored status
    evt = db.query(WebhookEvent).filter_by(event_id=event_id).first()
    assert evt is not None
    assert evt.error == "ignored: unhandled event type"


def test_webhook_duplicate_event_idempotent(client, monkeypatch, db):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    event_id = f"evt_{uuid.uuid4().hex}"
    payload = {
        "event": "invoice.paid",
        "payload": {},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = _sign(raw_body)

    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Event-Id": event_id,
        "X-Razorpay-Signature": sig,
    }

    # First delivery
    resp1 = client.post(BASE, content=raw_body, headers=headers)
    assert resp1.status_code == 200
    assert resp1.json() == {"received": True}

    # Second delivery with same event_id
    resp2 = client.post(BASE, content=raw_body, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json() == {"received": True}

    # Stored once
    assert db.query(WebhookEvent).filter_by(event_id=event_id).count() == 1



def test_webhook_signature_verification_enforced(client, monkeypatch, db):
    secret = "webhook_secret_key_12345"
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", secret)

    event_id = f"evt_{uuid.uuid4().hex}"
    payload = {"event": "payment.authorized", "payload": {}}
    raw_body = json.dumps(payload).encode("utf-8")

    # 1. Without valid signature header -> 400
    resp = client.post(
        BASE,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Event-Id": event_id,
            "X-Razorpay-Signature": "invalid_signature",
        },
    )
    assert resp.status_code == 400

    # 2. With valid signature -> 200
    computed_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    valid_event_id = f"evt_{uuid.uuid4().hex}"
    resp_valid = client.post(
        BASE,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Event-Id": valid_event_id,
            "X-Razorpay-Signature": computed_sig,
        },
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json() == {"received": True}


def test_payment_failed_webhook_opens_dunning_case_for_subscription_renewal(client, monkeypatch, tenant, db):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="3500.00")
    sub = _renewal_subscription(db, tenant, customer, plan)

    inv = tenant.invoice(customer, amount="3500.00", status=InvoiceStatus.SENT)
    inv.subscription_id = sub.id
    db.commit()

    payment = _pending_razorpay_payment(db, tenant, inv)
    raw_body, headers = _payment_failed_payload(payment.gateway_order_id, f"evt_{uuid.uuid4().hex}")

    resp = client.post(BASE, content=raw_body, headers=headers)
    assert resp.status_code == 200

    db.refresh(payment)
    assert payment.status == PaymentStatus.FAILED

    cases = db.query(DunningCase).filter_by(invoice_id=inv.id).all()
    assert len(cases) == 1
    case = cases[0]
    assert case.subscription_id == sub.id
    assert case.customer_id == customer.id
    assert len(case.communications) == 1  # existing "payment failed" follow-up notification fired

    db.refresh(sub)
    assert sub.status == SubscriptionStatus.PAST_DUE  # existing dunning behavior, unchanged


def test_payment_failed_webhook_redelivery_does_not_duplicate_case(client, monkeypatch, tenant, db):
    """Same event_id delivered twice - the existing webhook-level idempotency (unique event_id) applies."""
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1200.00")
    sub = _renewal_subscription(db, tenant, customer, plan)

    inv = tenant.invoice(customer, amount="1200.00", status=InvoiceStatus.SENT)
    inv.subscription_id = sub.id
    db.commit()

    payment = _pending_razorpay_payment(db, tenant, inv)
    event_id = f"evt_{uuid.uuid4().hex}"
    raw_body, headers = _payment_failed_payload(payment.gateway_order_id, event_id)

    resp1 = client.post(BASE, content=raw_body, headers=headers)
    assert resp1.status_code == 200
    resp2 = client.post(BASE, content=raw_body, headers=headers)
    assert resp2.status_code == 200

    assert db.query(DunningCase).filter_by(invoice_id=inv.id).count() == 1


def test_payment_failed_webhook_second_distinct_event_does_not_duplicate_case(client, monkeypatch, tenant, db):
    """Two distinct failed-payment events for the same invoice (e.g. customer retried checkout
    twice) must still result in exactly one active Dunning case - trigger_dunning_for_failed_payment's
    existing-case guard (unchanged) is what prevents the duplicate here, not the webhook layer."""
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1800.00")
    sub = _renewal_subscription(db, tenant, customer, plan)

    inv = tenant.invoice(customer, amount="1800.00", status=InvoiceStatus.SENT)
    inv.subscription_id = sub.id
    db.commit()

    payment = _pending_razorpay_payment(db, tenant, inv)

    raw_body_1, headers_1 = _payment_failed_payload(payment.gateway_order_id, f"evt_{uuid.uuid4().hex}")
    resp1 = client.post(BASE, content=raw_body_1, headers=headers_1)
    assert resp1.status_code == 200

    # A second, distinct webhook event for the same order/invoice (different event_id).
    raw_body_2, headers_2 = _payment_failed_payload(payment.gateway_order_id, f"evt_{uuid.uuid4().hex}")
    resp2 = client.post(BASE, content=raw_body_2, headers=headers_2)
    assert resp2.status_code == 200

    assert db.query(WebhookEvent).filter_by(event_type="payment.failed").count() >= 2
    assert db.query(DunningCase).filter_by(invoice_id=inv.id).count() == 1


def test_payment_failed_webhook_ignores_one_time_invoice(client, monkeypatch, tenant, db):
    """A one-off invoice (no subscription_id) failing online must NOT create a Dunning case."""
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="900.00", status=InvoiceStatus.SENT)
    assert inv.subscription_id is None

    payment = _pending_razorpay_payment(db, tenant, inv)
    raw_body, headers = _payment_failed_payload(payment.gateway_order_id, f"evt_{uuid.uuid4().hex}")

    resp = client.post(BASE, content=raw_body, headers=headers)
    assert resp.status_code == 200

    db.refresh(payment)
    assert payment.status == PaymentStatus.FAILED
    assert db.query(DunningCase).filter_by(invoice_id=inv.id).count() == 0


def test_payment_failed_webhook_created_case_supports_retry_now(client, monkeypatch, tenant, db):
    """The existing retry-now flow works unchanged on a case opened by the new webhook trigger."""
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="2500.00")
    sub = _renewal_subscription(db, tenant, customer, plan)

    inv = tenant.invoice(customer, amount="2500.00", status=InvoiceStatus.SENT)
    inv.subscription_id = sub.id
    db.commit()

    payment = _pending_razorpay_payment(db, tenant, inv)
    raw_body, headers = _payment_failed_payload(payment.gateway_order_id, f"evt_{uuid.uuid4().hex}")
    resp = client.post(BASE, content=raw_body, headers=headers)
    assert resp.status_code == 200

    case = db.query(DunningCase).filter_by(invoice_id=inv.id).one()

    retry_resp = client.post(f"/api/v1/dunning/cases/{case.id}/retry-now", headers=tenant.headers())
    assert retry_resp.status_code == 200
    body = retry_resp.json()
    assert body["attempt_count"] == 1
    assert len(body["attempts"]) >= 1

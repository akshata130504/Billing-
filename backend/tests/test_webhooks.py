"""Characterization tests for inbound webhooks and event deduplication."""
import hashlib
import hmac
import json
import uuid
import pytest

from backend.app.core.config import settings
from backend.app.models import WebhookEvent

BASE = "/api/v1/webhooks/razorpay"


SECRET = "test_webhook_secret_key_12345"


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


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

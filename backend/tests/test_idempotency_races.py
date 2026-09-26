"""Idempotency race losers: duplicate webhooks and duplicate Idempotency-Key requests
must never surface as HTTP 500 and must still write exactly one financial record.

The unit tests (any database) drive the replay / still-processing / lost-insert
paths directly; the threaded tests (PostgreSQL only) fire real concurrent requests,
following tests/test_postgres_concurrency.py.
"""
import hashlib
import hmac
import json
import threading
import time
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, engine
from backend.app.core.exceptions import ConflictError
from backend.app.main import app
from backend.app.models import Invoice, InvoiceStatus, WebhookEvent
from backend.app.models.events import IdempotencyRecord, utcnow
from backend.app.models.payments import Payment, PaymentAllocation, PaymentGateway, PaymentMethod, PaymentStatus
from backend.app.services import idempotency_service, payment_service

postgres_only = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="real concurrent unique-violation races need PostgreSQL (set TEST_DATABASE_URL)",
)
WEBHOOK_SECRET = "idem_race_webhook_secret"


# ------------------------------------------------------------------ unit: replay paths
def _record(db, org_id, key, *, status="processing", params=None, body=None, code=None, expires_in_hours=1):
    rec = IdempotencyRecord(
        organization_id=org_id,
        idempotency_key=key,
        request_path="/payments",
        request_method="POST",
        params_hash=idempotency_service._normalize_params_hash(params),
        status=status,
        status_code=code,
        response_body=body,
        expires_at=utcnow() + timedelta(hours=expires_in_hours),
    )
    db.add(rec)
    db.commit()
    return rec


def test_completed_key_replays_stored_status_and_body(db, tenant):
    org = tenant.organization.id
    params = {"body": {"amount": "10.00"}}
    _record(db, org, "k-done", status="completed", params=params, body={"id": "pay-1"}, code=201)
    calls = []
    code, body = idempotency_service.run_idempotent(
        db, organization_id=org, key="k-done", request_path="/payments", request_method="POST",
        params=params, handler=lambda: calls.append(1) or {"id": "other"}, status_code=201,
    )
    assert (code, body) == (201, {"id": "pay-1"})
    assert calls == []


def test_in_flight_key_waits_then_409_with_clear_message(db, tenant):
    org = tenant.organization.id
    params = {"body": {"amount": "10.00"}}
    _record(db, org, "k-busy", params=params)
    started = time.monotonic()
    with pytest.raises(ConflictError) as err:
        idempotency_service.run_idempotent(
            db, organization_id=org, key="k-busy", request_path="/payments", request_method="POST",
            params=params, handler=lambda: {"id": "x"}, status_code=201, wait_seconds=0.3,
        )
    assert time.monotonic() - started >= 0.25
    assert err.value.message == idempotency_service.STILL_PROCESSING_MESSAGE
    assert err.value.status_code == 409


def test_in_flight_key_replays_once_original_completes(db, tenant, monkeypatch):
    """The duplicate polls; when the original finishes it gets the same response."""
    org = tenant.organization.id
    params = {"body": {"amount": "10.00"}}
    rec = _record(db, org, "k-finishing", params=params)
    polls = {"n": 0}
    real_sleep = time.sleep

    def finishing_sleep(seconds):
        polls["n"] += 1
        if polls["n"] == 2:
            with SessionLocal() as other:
                idempotency_service.complete_idempotency(other, record_id=rec.id, status_code=201, response_body={"id": "pay-9"})
        real_sleep(0.01)

    monkeypatch.setattr(idempotency_service.time, "sleep", finishing_sleep)
    code, body = idempotency_service.run_idempotent(
        db, organization_id=org, key="k-finishing", request_path="/payments", request_method="POST",
        params=params, handler=lambda: pytest.fail("handler must not run twice"), status_code=201, wait_seconds=5,
    )
    assert (code, body) == (201, {"id": "pay-9"})


def test_lost_insert_race_is_caught_and_replayed(db, tenant, monkeypatch):
    """Simulates the loser: its first read saw no record, so it INSERTs and hits the
    unique constraint. That must be swallowed (savepoint) and the winner replayed."""
    org = tenant.organization.id
    params = {"body": {"amount": "5.00"}}
    _record(db, org, "k-race", status="completed", params=params, body={"id": "winner"}, code=201)
    real_load = idempotency_service._load
    seen = {"n": 0}

    def stale_first_read(session, organization_id, key):
        seen["n"] += 1
        return None if seen["n"] == 1 else real_load(session, organization_id, key)

    monkeypatch.setattr(idempotency_service, "_load", stale_first_read)
    code, body = idempotency_service.run_idempotent(
        db, organization_id=org, key="k-race", request_path="/payments", request_method="POST",
        params=params, handler=lambda: pytest.fail("loser must not execute"), status_code=201,
    )
    assert (code, body) == (201, {"id": "winner"})
    assert seen["n"] >= 2
    assert db.scalar(select(func.count()).select_from(IdempotencyRecord).where(
        IdempotencyRecord.organization_id == org, IdempotencyRecord.idempotency_key == "k-race")) == 1


def test_mismatched_params_and_expired_key(db, tenant):
    org = tenant.organization.id
    _record(db, org, "k-mismatch", status="completed", params={"a": 1}, body={}, code=201)
    with pytest.raises(ConflictError):
        idempotency_service.run_idempotent(
            db, organization_id=org, key="k-mismatch", request_path="/payments", request_method="POST",
            params={"a": 2}, handler=lambda: {}, status_code=201,
        )
    _record(db, org, "k-expired", status="completed", params={"a": 1}, body={"old": True}, code=201, expires_in_hours=-1)
    code, body = idempotency_service.run_idempotent(
        db, organization_id=org, key="k-expired", request_path="/payments", request_method="POST",
        params={"a": 1}, handler=lambda: {"new": True}, status_code=201,
    )
    assert body == {"new": True}


def test_failed_handler_releases_key(db, tenant):
    org = tenant.organization.id

    def boom():
        raise RuntimeError("gateway down")

    with pytest.raises(RuntimeError):
        idempotency_service.run_idempotent(
            db, organization_id=org, key="k-fail", request_path="/payments", request_method="POST",
            params={}, handler=boom, status_code=201,
        )
    code, body = idempotency_service.run_idempotent(
        db, organization_id=org, key="k-fail", request_path="/payments", request_method="POST",
        params={}, handler=lambda: {"ok": 1}, status_code=201,
    )
    assert body == {"ok": 1}


def test_sequential_duplicate_webhook_is_acknowledged_as_duplicate(client, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    raw = json.dumps({"event": "some.unhandled", "payload": {}}).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex}",
        "X-Razorpay-Signature": hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest(),
    }
    assert client.post("/api/v1/webhooks/razorpay", content=raw, headers=headers).json() == {"received": True}
    dup = client.post("/api/v1/webhooks/razorpay", content=raw, headers=headers)
    assert dup.status_code == 200 and dup.json() == {"received": True, "status": "duplicate"}


# ------------------------------------------------------------------ PostgreSQL threaded races
def _run_concurrently(fn, n):
    barrier = threading.Barrier(n)
    results, errors = [None] * n, [None] * n

    def worker(i):
        try:
            barrier.wait(timeout=10)
            results[i] = fn(i)
        except BaseException as exc:  # noqa: BLE001
            errors[i] = exc

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
        assert not t.is_alive(), "worker thread hung"
    return results, errors


def _client():
    return TestClient(app, raise_server_exceptions=False)


def _pending_gateway_payment(db, tenant, invoice):
    p = Payment(
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
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _allocations(invoice_id):
    with SessionLocal() as s:
        return s.scalars(select(PaymentAllocation).where(PaymentAllocation.invoice_id == invoice_id)).all()


@postgres_only
def test_concurrent_duplicate_webhook_losers_get_200_duplicate(tenant, db, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    inv = tenant.invoice(tenant.customer(), amount="1500.00")
    payment = _pending_gateway_payment(db, tenant, inv)
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    body = json.dumps({
        "event": "payment.captured",
        "created_at": int(time.time()),
        "payload": {"payment": {"entity": {"id": f"pay_{uuid.uuid4().hex[:14]}", "order_id": payment.gateway_order_id,
                                           "amount": 150000, "currency": "INR", "status": "captured"}}},
    }).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest(),
        "X-Razorpay-Event-Id": event_id,
    }

    def deliver(_i):
        r = _client().post("/api/v1/webhooks/razorpay", content=body, headers=headers)
        return r.status_code, r.json()

    results, errors = _run_concurrently(deliver, 4)
    assert errors == [None] * 4, errors
    codes = [c for c, _ in results]
    assert codes == [200] * 4, results
    bodies = [b for _, b in results]
    assert bodies.count({"received": True}) == 1, bodies
    assert bodies.count({"received": True, "status": "duplicate"}) == 3, bodies
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(WebhookEvent).where(WebhookEvent.event_id == event_id)) == 1
        assert s.get(Payment, payment.id).status == PaymentStatus.SUCCEEDED
        assert s.get(Invoice, inv.id).status == InvoiceStatus.PAID
    assert len(_allocations(inv.id)) == 1


@postgres_only
def test_concurrent_same_idempotency_key_payment_replays_winner(tenant, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="900.00")
    headers = {**tenant.headers(), "Idempotency-Key": f"idem-{uuid.uuid4().hex}"}
    body = {"customer_id": customer.id, "amount": "900.00", "method": "bank_transfer",
            "allocations": [{"invoice_id": inv.id, "amount": "900.00"}]}

    def post(_i):
        r = _client().post("/api/v1/payments", headers=headers, json=body)
        return r.status_code, r.json()

    results, errors = _run_concurrently(post, 4)
    assert errors == [None] * 4, errors
    codes = [c for c, _ in results]
    assert 500 not in codes and set(codes) <= {201, 409}, results
    ok = [b for c, b in results if c == 201]
    assert ok and len({b["id"] for b in ok}) == 1, results  # every 201 is the SAME payment
    assert all(b == ok[0] for b in ok)  # identical replayed body
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Payment).where(Payment.customer_id == customer.id)) == 1
        assert Decimal(s.get(Invoice, inv.id).amount_paid) == Decimal("900.00")
    assert len(_allocations(inv.id)) == 1


@postgres_only
def test_concurrent_same_idempotency_key_record_payment_replays_winner(tenant, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="650.00")
    headers = {**tenant.headers(), "Idempotency-Key": f"idem-{uuid.uuid4().hex}"}
    body = {"amount": "650.00", "method": "upi", "reference": "UTR-RACE-1"}

    def post(_i):
        r = _client().post(f"/api/v1/invoices/{inv.id}/record-payment", headers=headers, json=body)
        return r.status_code, r.json()

    results, errors = _run_concurrently(post, 4)
    assert errors == [None] * 4, errors
    codes = [c for c, _ in results]
    assert 500 not in codes and set(codes) <= {201, 409}, results
    ok = [b for c, b in results if c == 201]
    assert ok and all(b == ok[0] for b in ok), results
    assert len(_allocations(inv.id)) == 1
    with SessionLocal() as s:
        assert s.get(Invoice, inv.id).status == InvoiceStatus.PAID


@postgres_only
def test_concurrent_key_while_original_still_running_is_409_not_500(tenant, db, monkeypatch):
    """A slow original + a short wait: the losers deterministically get 409 with the
    'still processing' message, the original 201, and one payment is recorded."""
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="400.00")
    monkeypatch.setattr(idempotency_service, "IDEMPOTENCY_WAIT_SECONDS", 0.2)
    real_create = payment_service.create_payment

    def slow_create(*args, **kwargs):
        time.sleep(1.5)
        return real_create(*args, **kwargs)

    monkeypatch.setattr(payment_service, "create_payment", slow_create)
    headers = {**tenant.headers(), "Idempotency-Key": f"idem-{uuid.uuid4().hex}"}
    body = {"customer_id": customer.id, "amount": "400.00", "method": "bank_transfer",
            "allocations": [{"invoice_id": inv.id, "amount": "400.00"}]}

    def post(_i):
        r = _client().post("/api/v1/payments", headers=headers, json=body)
        return r.status_code, r.json()

    results, errors = _run_concurrently(post, 3)
    assert errors == [None] * 3, errors
    codes = sorted(c for c, _ in results)
    assert codes == [201, 409, 409], results
    for code, payload in results:
        if code == 409:
            assert payload["error"]["message"] == idempotency_service.STILL_PROCESSING_MESSAGE
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Payment).where(Payment.customer_id == customer.id)) == 1
    # a retry after the original completed replays it
    replay = _client().post("/api/v1/payments", headers=headers, json=body)
    assert replay.status_code == 201
    assert replay.json()["id"] == next(p for c, p in results if c == 201)["id"]

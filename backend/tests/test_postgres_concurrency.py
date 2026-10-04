"""Real-concurrency tests (PostgreSQL only).

Each test commits its fixture data, then runs the SAME financial operation from 2+
threads at once - every thread with its own SessionLocal() session (or its own
TestClient, so async endpoints get their own event loop), released together by a
threading.Barrier - and asserts the money moved exactly once.

SQLite serialises writers and ignores SELECT ... FOR UPDATE, so these tests are
skipped there; run them with TEST_DATABASE_URL pointing at a PostgreSQL database.
The schema is built with Base.metadata.create_all, i.e. WITHOUT the migration-only
partial unique index uq_invoices_subscription_period: the invoice tests therefore
prove the row-lock protection on its own.
"""
import hashlib
import hmac
import json
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, engine
from backend.app.main import app
from backend.app.models import Invoice, InvoiceStatus, WebhookEvent
from backend.app.models.credits import CreditApplication, CreditNote
from backend.app.models.dunning import DunningCase, DunningCaseStatus
from backend.app.models.payments import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    Payment,
    PaymentAllocation,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.services import dunning_service, payment_service, razorpay_gateway, scheduler, subscription_service

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="real row-lock / advisory-lock concurrency needs PostgreSQL (set TEST_DATABASE_URL)",
)

WEBHOOK_SECRET = "concurrency_webhook_secret"
KEY_SECRET = "rzp_conc_key_secret"


# --- harness ------------------------------------------------------------------------------------------------------


def run_concurrently(fn, n=2, timeout=60):
    """Run fn(i) in n threads released together; returns (results, errors) per thread."""
    barrier = threading.Barrier(n)
    results = [None] * n
    errors = [None] * n

    def worker(i):
        try:
            barrier.wait(timeout=10)
            results[i] = fn(i)
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            errors[i] = exc

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout)
        assert not t.is_alive(), "worker thread hung (deadlock?)"
    return results, errors


def in_session(work):
    """Run work(session) in a fresh session and commit; roll back and re-raise on failure."""
    s = SessionLocal()
    try:
        out = work(s)
        s.commit()
        return out
    except BaseException:
        s.rollback()
        raise
    finally:
        s.close()


def fresh():
    return SessionLocal()


def thread_client():
    # No context manager: each request gets its own portal / event loop, so even
    # `async def` endpoints doing sync DB work really run in parallel.
    return TestClient(app, raise_server_exceptions=False)


def _due_subscription(db, tenant, customer, plan, *, status=SubscriptionStatus.ACTIVE, days_ago=30):
    today = date.today()
    start = today - timedelta(days=days_ago)
    sub = Subscription(
        organization_id=tenant.organization.id,
        subscription_number=f"SUB-{uuid.uuid4().hex[:8].upper()}",
        customer_id=customer.id,
        plan_id=plan.id,
        status=status,
        quantity=1,
        start_date=start,
        current_period_start=start,
        current_period_end=today,
        next_billing_date=today,
        currency="INR",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def _invoice_count(sub_id, period_start=None):
    with fresh() as s:
        stmt = select(func.count()).select_from(Invoice).where(
            Invoice.subscription_id == sub_id, Invoice.status != InvoiceStatus.VOID
        )
        if period_start is not None:
            stmt = stmt.where(Invoice.period_start == period_start)
        return s.scalar(stmt)


def _pending_gateway_payment(db, tenant, invoice, order_id=None):
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


def _assert_invoice_settled_once(invoice_id, amount):
    with fresh() as s:
        inv = s.get(Invoice, invoice_id)
        allocs = s.scalars(select(PaymentAllocation).where(PaymentAllocation.invoice_id == invoice_id)).all()
        assert len(allocs) == 1, f"expected one allocation, got {len(allocs)}"
        assert sum(Decimal(a.amount) for a in allocs) == Decimal(amount)
        assert Decimal(inv.amount_paid) == Decimal(amount)
        assert Decimal(inv.amount_due) == Decimal("0.00")
        assert inv.status == InvoiceStatus.PAID


# --- 1. renewal ---------------------------------------------------------------------------------------------------


def test_concurrent_renewal_bills_period_once(tenant, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    sub = _due_subscription(db, tenant, customer, plan)
    old_end = sub.current_period_end
    expected_end = subscription_service.period_end_for(old_end, plan, subscription_service.anchor_day(sub))

    def renew(_i):
        def work(s):
            loaded = scheduler._load_subscription(s, sub.id)
            return subscription_service.renew_subscription(s, loaded, only_if_due=True, today=date.today())
        return in_session(work)

    results, errors = run_concurrently(renew, n=3)
    assert errors == [None] * 3, errors
    assert sorted(results) == ["renewed", "skipped", "skipped"]
    assert _invoice_count(sub.id) == 1
    with fresh() as s:
        stored = s.get(Subscription, sub.id)
        assert stored.current_period_start == old_end
        assert stored.current_period_end == expected_end
        assert stored.next_billing_date == expected_end


# --- 2. invoice generation for the same period -------------------------------------------------------------------


def test_concurrent_generate_period_invoice_issues_one(tenant, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="700.00")
    sub = _due_subscription(db, tenant, customer, plan)

    def generate(_i):
        return in_session(
            lambda s: subscription_service.generate_period_invoice(s, s.get(Subscription, sub.id), actor_label="system").id
        )

    results, errors = run_concurrently(generate, n=3)
    ok = [r for r in results if r]
    assert len(ok) == 1, (results, errors)
    assert all(e is None or "already exists" in str(e) for e in errors), errors
    assert _invoice_count(sub.id, sub.current_period_start) == 1


# --- 3. gateway payment capture ----------------------------------------------------------------------------------


def test_concurrent_capture_allocates_once(tenant, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1000.00")
    payment = _pending_gateway_payment(db, tenant, inv)
    gateway_payment_id = f"pay_{uuid.uuid4().hex[:14]}"

    def capture(_i):
        def work(s):
            p = s.get(Payment, payment.id)
            i = s.get(Invoice, inv.id)
            return payment_service.capture_gateway_payment(
                s, p, i, gateway_payment_id=gateway_payment_id, actor_label="system"
            ).status
        return in_session(work)

    results, errors = run_concurrently(capture, n=3)
    assert errors == [None] * 3, errors
    assert results == [PaymentStatus.SUCCEEDED] * 3
    with fresh() as s:
        assert s.scalar(select(func.count()).select_from(Payment).where(Payment.gateway_payment_id == gateway_payment_id)) == 1
    _assert_invoice_settled_once(inv.id, "1000.00")


# --- 4. duplicate webhook delivered concurrently -----------------------------------------------------------------


def test_concurrent_duplicate_webhook_settles_once(tenant, db, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1500.00")
    payment = _pending_gateway_payment(db, tenant, inv)
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    body = json.dumps(
        {
            "event": "payment.captured",
            "created_at": int(time.time()),
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_{uuid.uuid4().hex[:14]}",
                        "order_id": payment.gateway_order_id,
                        "amount": 150000,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest(),
        "X-Razorpay-Event-Id": event_id,
    }

    def deliver(_i):
        return thread_client().post("/api/v1/webhooks/razorpay", content=body, headers=headers).status_code

    codes, errors = run_concurrently(deliver, n=3)
    assert errors == [None] * 3, errors
    assert 200 in codes, codes
    # A delivery that loses the event_id insert race must never be a 2xx that dropped work;
    # a 5xx makes Razorpay redeliver, and the redelivery is then acknowledged as a duplicate.
    assert all(c in (200, 500, 503) for c in codes), codes
    with fresh() as s:
        assert s.scalar(select(func.count()).select_from(WebhookEvent).where(WebhookEvent.event_id == event_id)) == 1
        assert s.get(Payment, payment.id).status == PaymentStatus.SUCCEEDED
    _assert_invoice_settled_once(inv.id, "1500.00")
    # Redelivery after the race is acknowledged without re-processing.
    assert thread_client().post("/api/v1/webhooks/razorpay", content=body, headers=headers).status_code == 200
    _assert_invoice_settled_once(inv.id, "1500.00")


# --- 5. manual payment with the same Idempotency-Key -------------------------------------------------------------


def test_concurrent_idempotent_manual_payment_records_once(tenant, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="900.00")
    headers = {**tenant.headers(), "Idempotency-Key": f"idem-{uuid.uuid4().hex}"}
    body = {
        "customer_id": customer.id,
        "amount": "900.00",
        "method": "bank_transfer",
        "allocations": [{"invoice_id": inv.id, "amount": "900.00"}],
    }

    def post(_i):
        return thread_client().post("/api/v1/payments", headers=headers, json=body).status_code

    codes, errors = run_concurrently(post, n=3)
    assert errors == [None] * 3, errors
    assert 201 in codes, codes
    assert all(c in (201, 409, 500) for c in codes), codes
    with fresh() as s:
        assert s.scalar(select(func.count()).select_from(Payment).where(Payment.customer_id == customer.id)) == 1
    _assert_invoice_settled_once(inv.id, "900.00")


# --- 6. hosted checkout confirm ----------------------------------------------------------------------------------


class _FakeRazorpay:
    def __init__(self):
        self.orders, self.payments = {}, {}
        self.fetch_calls = 0
        self._lock = threading.Lock()

    def install(self, monkeypatch):
        creds = razorpay_gateway.RazorpayCredentials("rzp_conc_key", KEY_SECRET, WEBHOOK_SECRET)
        monkeypatch.setattr(razorpay_gateway, "credentials_for", lambda db, org_id: creds)
        monkeypatch.setattr(razorpay_gateway, "create_order", self.create_order)
        monkeypatch.setattr(razorpay_gateway, "fetch_payment", self.fetch_payment)
        monkeypatch.setattr(razorpay_gateway, "create_customer", lambda *a, **k: {"id": "cust_conc_1"})
        monkeypatch.setattr(razorpay_gateway, "fetch_card", lambda *a, **k: {})
        monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
        return self

    def create_order(self, amount_paise, currency, receipt, notes=None, *, creds=None, customer_id=None):
        order = {"id": f"order_{uuid.uuid4().hex[:12]}", "amount": int(amount_paise), "currency": currency,
                 "notes": notes or {}, "customer_id": customer_id}
        self.orders[order["id"]] = order
        return order

    def pay(self, order_id):
        pid = f"pay_{uuid.uuid4().hex[:12]}"
        order = self.orders[order_id]
        self.payments[pid] = {"id": pid, "order_id": order_id, "status": "captured", "amount": order["amount"],
                              "currency": order["currency"], "method": "card", "token_id": None}
        return pid

    def fetch_payment(self, payment_id, *, creds=None):
        with self._lock:
            self.fetch_calls += 1
        time.sleep(0.2)  # widen the window between verification and capture
        return self.payments[payment_id]


def test_concurrent_checkout_confirm_settles_once(client, tenant, db, monkeypatch):
    rzp = _FakeRazorpay().install(monkeypatch)
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="2000.00")
    res = client.post("/api/v1/checkout/sessions", headers=tenant.headers(),
                      json={"purpose": "invoice_payment", "invoice_id": inv.id})
    assert res.status_code == 201, res.text
    token = res.json()["token"]
    order_id = client.get(f"/api/v1/checkout/public/{token}").json()["gateway_order_id"]
    assert order_id
    pid = rzp.pay(order_id)
    sig = hmac.new(KEY_SECRET.encode(), f"{order_id}|{pid}".encode(), hashlib.sha256).hexdigest()
    body = {"razorpay_payment_id": pid, "razorpay_order_id": order_id, "razorpay_signature": sig}

    def confirm(_i):
        r = thread_client().post(f"/api/v1/checkout/public/{token}/confirm", json=body)
        return r.status_code, r.json().get("status") if r.status_code == 200 else r.text

    results, errors = run_concurrently(confirm, n=3)
    assert errors == [None] * 3, errors
    assert all(code == 200 and status == "successful" for code, status in results), results
    with fresh() as s:
        assert s.scalar(select(func.count()).select_from(Payment).where(Payment.customer_id == customer.id)) == 1
        assert s.scalar(select(func.count()).select_from(Payment).where(Payment.gateway_payment_id == pid)) == 1
    _assert_invoice_settled_once(inv.id, "2000.00")
    assert rzp.fetch_calls == 1  # the losers saw the committed capture and never re-verified


# --- 7. credit note application ----------------------------------------------------------------------------------


def test_concurrent_credit_note_application_never_overspends(client, tenant, db):
    customer = tenant.customer()
    res = client.post("/api/v1/credit-notes", headers=tenant.headers(), json={
        "customer_id": customer.id, "reason": "goodwill", "currency": "INR",
        "lines": [{"description": "credit", "amount": 400.00}],
    })
    assert res.status_code == 201, res.text
    cn_id = res.json()["id"]
    invoices = [tenant.invoice(customer, amount="400.00") for _ in range(3)]
    headers = tenant.headers()

    def apply(i):
        return thread_client().post(
            f"/api/v1/credit-notes/{cn_id}/apply", headers=headers,
            json={"invoice_id": invoices[i].id, "amount": 400.00},
        ).status_code

    codes, errors = run_concurrently(apply, n=3)
    assert errors == [None] * 3, errors
    assert sorted(codes) == [200, 409, 409], codes
    with fresh() as s:
        cn = s.get(CreditNote, cn_id)
        applied = s.scalars(select(CreditApplication).where(CreditApplication.credit_note_id == cn_id)).all()
        assert len(applied) == 1
        assert sum(Decimal(a.amount) for a in applied) == Decimal("400.00")
        assert Decimal(cn.balance_remaining) == Decimal("0.00")


# --- 8. trial conversion -----------------------------------------------------------------------------------------


def test_concurrent_trial_conversion_issues_one_invoice(client, tenant, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="2500.00", trial_days=14)
    res = client.post("/api/v1/subscriptions", headers=tenant.headers(),
                      json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1, "start_date": str(date.today())})
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "trialing"
    sub_id = res.json()["id"]
    headers = tenant.headers()

    def convert(_i):
        return thread_client().post(f"/api/v1/trials/{sub_id}/convert", headers=headers,
                                    json={"generate_first_invoice": True}).status_code

    codes, errors = run_concurrently(convert, n=3)
    assert errors == [None] * 3, errors
    assert codes.count(200) == 1, codes
    assert all(c in (200, 409, 422) for c in codes), codes
    assert _invoice_count(sub_id) == 1
    with fresh() as s:
        assert s.get(Subscription, sub_id).status == SubscriptionStatus.ACTIVE


# --- 9. draft activation -----------------------------------------------------------------------------------------


def test_concurrent_activation_issues_one_first_invoice(client, tenant, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1200.00")
    res = client.post("/api/v1/subscriptions", headers=tenant.headers(),
                      json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1, "status": "draft"})
    assert res.status_code == 201, res.text
    sub_id = res.json()["id"]
    headers = tenant.headers()

    def activate(_i):
        return thread_client().post(f"/api/v1/subscriptions/{sub_id}/activate", headers=headers).status_code

    codes, errors = run_concurrently(activate, n=3)
    assert errors == [None] * 3, errors
    assert 200 in codes, codes
    assert all(c in (200, 409, 422) for c in codes), codes
    assert _invoice_count(sub_id) == 1
    with fresh() as s:
        assert s.get(Subscription, sub_id).status == SubscriptionStatus.ACTIVE


# --- 10. quote conversion ----------------------------------------------------------------------------------------


def test_concurrent_quote_conversion_issues_one_invoice(client, tenant, db):
    customer = tenant.customer()
    headers = tenant.headers()
    res = client.post("/api/v1/quotes", headers=headers, json={
        "customer_id": customer.id, "title": "Concurrency",
        "items": [{"description": "Work", "quantity": "1", "unit_price": "1000.00", "tax_rate_pct": "18"}],
    })
    assert res.status_code == 201, res.text
    qid = res.json()["id"]
    assert client.post(f"/api/v1/quotes/{qid}/send", headers=headers).status_code == 200
    assert client.post(f"/api/v1/quotes/{qid}/mark-accepted", headers=headers, json={"reason": "Signed PDF received"}).status_code == 200

    def convert(_i):
        return thread_client().post(f"/api/v1/quotes/{qid}/convert", headers=headers, json={}).status_code

    codes, errors = run_concurrently(convert, n=3)
    assert errors == [None] * 3, errors
    assert sorted(codes) == [201, 409, 409], codes
    with fresh() as s:
        assert s.scalar(select(func.count()).select_from(Invoice).where(Invoice.quote_id == qid)) == 1


# --- 11. scheduler lock + heartbeat ------------------------------------------------------------------------------


def test_scheduler_skips_while_advisory_lock_is_held(tenant, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="300.00")
    sub = _due_subscription(db, tenant, customer, plan)
    with engine.connect() as holder:
        assert holder.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": scheduler.ADVISORY_LOCK_KEY}).scalar()
        holder.commit()
        try:
            results, errors = run_concurrently(lambda _i: scheduler.run_billing_jobs(fresh()), n=2)
        finally:
            holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": scheduler.ADVISORY_LOCK_KEY})
            holder.commit()
    assert errors == [None, None], errors
    assert all(r.get("skipped_locked") == 1 and r["renewals"] == 0 for r in results), results
    assert _invoice_count(sub.id) == 0
    with fresh() as s:
        assert s.get(Subscription, sub.id).next_billing_date == date.today()


def test_simultaneous_scheduler_runs_renew_once_and_record_heartbeat(client, tenant, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="450.00")
    sub = _due_subscription(db, tenant, customer, plan)
    old_end = sub.current_period_end

    def run(_i):
        s = fresh()
        try:
            return scheduler.run_billing_jobs(s)
        finally:
            s.close()

    results, errors = run_concurrently(run, n=2)
    assert errors == [None, None], errors
    assert _invoice_count(sub.id) == 1
    with fresh() as s:
        stored = s.get(Subscription, sub.id)
        assert stored.current_period_start == old_end
        assert stored.next_billing_date > date.today()
        hb = scheduler.get_scheduler_heartbeat(s)
    assert hb is not None and hb["seconds_since_last_run"] < 120
    assert hb["total_runs"] >= 1

    ready = client.get("/api/v1/health/ready").json()
    beat = ready["features"]["scheduler_heartbeat"]
    assert beat["status"] == "ok", beat
    assert beat["age_seconds"] < 120


# --- 12. dunning retry -------------------------------------------------------------------------------------------


class _CountingAdapter:
    gateway_type = PaymentGateway.RAZORPAY

    def __init__(self):
        self.calls = 0
        self._lock = threading.Lock()

    def charge(self, **kwargs):
        from backend.app.services.gateways.base import GatewayChargeResult

        with self._lock:
            self.calls += 1
            n = self.calls
        time.sleep(0.3)  # a real gateway round-trip; widens the race window
        return GatewayChargeResult(success=True, gateway_payment_id=f"pay_dun_{uuid.uuid4().hex[:10]}_{n}")

    def refund(self, **kwargs):
        raise NotImplementedError

    def verify_webhook(self, **kwargs):
        return True


def _dunning_case(db, tenant, amount="2000.00"):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount=amount)
    sub = Subscription(
        organization_id=tenant.organization.id,
        subscription_number=f"SUB-{uuid.uuid4().hex[:8].upper()}",
        customer_id=customer.id, plan_id=plan.id, status=SubscriptionStatus.ACTIVE, quantity=1,
        start_date=date.today(), current_period_start=date.today(),
        current_period_end=date.today() + timedelta(days=30),
    )
    db.add(sub)
    db.commit()
    inv = tenant.invoice(customer, amount=amount, status=InvoiceStatus.SENT)
    case = dunning_service.trigger_dunning_for_failed_payment(
        db=db, organization_id=tenant.organization.id, invoice_id=inv.id, customer_id=customer.id,
        subscription_id=sub.id, reason="card_declined", payment_method_type="card",
    )
    db.commit()
    db.add(CustomerPaymentMethod(
        organization_id=tenant.organization.id, customer_id=customer.id, type="card",
        status=CustomerPaymentMethodStatus.ACTIVE, gateway="razorpay", gateway_token="tok_conc",
        last4="4242", card_brand="visa", exp_month=12, exp_year=2030, is_default=True,
    ))
    case.next_retry_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    return case, inv


def test_concurrent_dunning_retry_charges_once(tenant, db):
    from backend.app.services.gateways.registry import get_gateway_adapter, register_gateway_adapter

    case, inv = _dunning_case(db, tenant)
    org_id = tenant.organization.id
    adapter = _CountingAdapter()
    real = get_gateway_adapter(PaymentGateway.RAZORPAY)
    register_gateway_adapter(PaymentGateway.RAZORPAY, adapter)
    try:
        results, errors = run_concurrently(
            lambda _i: in_session(lambda s: dunning_service.execute_dunning_retries(s, org_id)), n=3
        )
    finally:
        register_gateway_adapter(PaymentGateway.RAZORPAY, real)
    assert adapter.calls == 1, f"customer card charged {adapter.calls} times ({errors})"
    assert errors == [None] * 3, errors
    with fresh() as s:
        assert s.scalar(select(func.count()).select_from(Payment).where(Payment.customer_id == inv.customer_id)) == 1
        assert s.get(DunningCase, case.id).status == DunningCaseStatus.RECOVERED
    _assert_invoice_settled_once(inv.id, "2000.00")


def test_concurrent_retry_now_and_scheduler_charge_once(tenant, db):
    """The production shape of the race: finance clicks "retry now" (twice) while the
    scheduler's dunning step runs over the same case."""
    from backend.app.services.gateways.registry import get_gateway_adapter, register_gateway_adapter

    case, inv = _dunning_case(db, tenant)
    org_id = tenant.organization.id
    headers = tenant.headers()
    adapter = _CountingAdapter()
    real = get_gateway_adapter(PaymentGateway.RAZORPAY)
    register_gateway_adapter(PaymentGateway.RAZORPAY, adapter)

    def act(i):
        if i == 0:
            return in_session(lambda s: dunning_service.execute_dunning_retries(s, org_id)) and 200
        return thread_client().post(f"/api/v1/dunning/cases/{case.id}/retry-now", headers=headers).status_code

    try:
        codes, errors = run_concurrently(act, n=3)
    finally:
        register_gateway_adapter(PaymentGateway.RAZORPAY, real)
    assert adapter.calls == 1, f"customer card charged {adapter.calls} times ({codes}, {errors})"
    assert errors == [None] * 3, errors
    with fresh() as s:
        assert s.scalar(select(func.count()).select_from(Payment).where(Payment.customer_id == inv.customer_id)) == 1
        assert s.get(DunningCase, case.id).status == DunningCaseStatus.RECOVERED
    _assert_invoice_settled_once(inv.id, "2000.00")


# --- 13. different payments / credits racing for the same invoice balance ----------------------------------------


def _assert_not_over_applied(invoice_id):
    """allocations + applied credits never exceed the invoice total, and the stored
    paid/due figures agree with what recompute derives from them."""
    with fresh() as s:
        inv = s.get(Invoice, invoice_id)
        allocated = s.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(PaymentAllocation.invoice_id == invoice_id)
        )
        credited = s.scalar(
            select(func.coalesce(func.sum(CreditApplication.amount), 0)).where(CreditApplication.invoice_id == invoice_id)
        )
        applied = Decimal(allocated) + Decimal(credited)
        total = Decimal(inv.total)
        assert applied <= total, f"over-applied: {applied} applied against total {total}"
        assert Decimal(inv.amount_due) >= 0
        assert Decimal(inv.amount_paid) == applied
        assert Decimal(inv.amount_due) == total - applied
        return applied


def test_concurrent_different_manual_payments_do_not_over_allocate(tenant, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1000.00")
    headers = tenant.headers()

    def record(i):
        return thread_client().post(
            f"/api/v1/invoices/{inv.id}/record-payment", headers=headers,
            json={"amount": "1000.00", "method": "bank_transfer", "reference": f"ref-{i}"},
        ).status_code

    codes, errors = run_concurrently(record, n=3)
    assert errors == [None] * 3, errors
    assert _assert_not_over_applied(inv.id) == Decimal("1000.00"), codes
    assert codes.count(201) == 1, codes
    with fresh() as s:
        assert s.scalar(select(func.count()).select_from(Payment).where(Payment.customer_id == customer.id)) == 1


def test_concurrent_different_payments_with_allocations_do_not_over_allocate(tenant, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1000.00")
    headers = tenant.headers()

    def create(i):
        return thread_client().post("/api/v1/payments", headers=headers, json={
            "customer_id": customer.id, "amount": "1000.00", "method": "cash", "reference": f"ref-{i}",
            "allocations": [{"invoice_id": inv.id, "amount": "1000.00"}],
        }).status_code

    codes, errors = run_concurrently(create, n=3)
    assert errors == [None] * 3, errors
    assert _assert_not_over_applied(inv.id) == Decimal("1000.00"), codes
    assert codes.count(201) == 1, codes


def test_concurrent_capture_of_two_gateway_payments_keeps_excess_unallocated(tenant, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1000.00")
    payments = [_pending_gateway_payment(db, tenant, inv) for _ in range(3)]

    def capture(i):
        def work(s):
            p = s.get(Payment, payments[i].id)
            return payment_service.capture_gateway_payment(
                s, p, s.get(Invoice, inv.id), gateway_payment_id=f"pay_{uuid.uuid4().hex[:14]}", actor_label="system"
            ).status
        return in_session(work)

    results, errors = run_concurrently(capture, n=3)
    assert errors == [None] * 3, errors
    # The money really arrived three times: every payment is captured...
    assert results == [PaymentStatus.SUCCEEDED] * 3
    assert _assert_not_over_applied(inv.id) == Decimal("1000.00")
    # ...but only one is applied; the excess stays as unallocated payment balance.
    with fresh() as s:
        unallocated = 0
        for p in payments:
            stored = s.get(Payment, p.id)
            if not stored.allocations:
                unallocated += 1
                assert payment_service.allocated_amount(stored) == 0
        assert unallocated == 2


def test_concurrent_different_credit_notes_do_not_over_apply(client, tenant, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1000.00")
    headers = tenant.headers()
    cn_ids = []
    for _ in range(3):
        res = client.post("/api/v1/credit-notes", headers=headers, json={
            "customer_id": customer.id, "reason": "goodwill", "currency": "INR",
            "lines": [{"description": "credit", "amount": 1000.00}],
        })
        assert res.status_code == 201, res.text
        cn_ids.append(res.json()["id"])

    def apply(i):
        return thread_client().post(
            f"/api/v1/credit-notes/{cn_ids[i]}/apply", headers=headers,
            json={"invoice_id": inv.id, "amount": 1000.00},
        ).status_code

    codes, errors = run_concurrently(apply, n=3)
    assert errors == [None] * 3, errors
    assert _assert_not_over_applied(inv.id) == Decimal("1000.00"), codes
    assert sorted(codes) == [200, 409, 409], codes
    with fresh() as s:
        balances = sorted(Decimal(s.get(CreditNote, c).balance_remaining) for c in cn_ids)
    assert balances == [Decimal("0.00"), Decimal("1000.00"), Decimal("1000.00")]


def _ctx(s, tenant):
    from backend.app.api.deps import CurrentContext
    from backend.app.models import Membership, Organization, User

    org = s.get(Organization, tenant.organization.id)
    user = s.get(User, tenant.owner.id)
    membership = s.scalars(
        select(Membership).where(Membership.organization_id == org.id, Membership.user_id == user.id)
    ).first()
    return CurrentContext(user=user, organization=org, membership=membership, ip_address=None, user_agent=None)


def test_concurrent_record_invoice_payment_service_does_not_over_allocate(tenant, db):
    from backend.app.schemas.invoices import RecordPaymentIn

    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1000.00")

    def record(i):
        def work(s):
            return payment_service.record_invoice_payment(
                s, _ctx(s, tenant), s.get(Invoice, inv.id),
                RecordPaymentIn(amount=Decimal("1000.00"), method="bank_transfer", reference=f"svc-{i}"),
            ).id
        return in_session(work)

    results, errors = run_concurrently(record, n=3)
    assert _assert_not_over_applied(inv.id) == Decimal("1000.00"), (results, errors)
    assert len([r for r in results if r]) == 1, (results, errors)
    # Losers are clean business rejections - never a duplicate payment number (IntegrityError).
    from sqlalchemy.exc import IntegrityError
    assert not any(isinstance(e, IntegrityError) for e in errors), errors


def test_concurrent_create_payment_service_does_not_over_allocate(tenant, db):
    from backend.app.schemas.payments import PaymentCreate

    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1000.00")

    def create(i):
        def work(s):
            data = PaymentCreate(
                customer_id=customer.id, amount=Decimal("1000.00"), method="cash", reference=f"svc-{i}",
                allocations=[{"invoice_id": inv.id, "amount": Decimal("1000.00")}],
            )
            return payment_service.create_payment(s, _ctx(s, tenant), data).id
        return in_session(work)

    results, errors = run_concurrently(create, n=3)
    assert _assert_not_over_applied(inv.id) == Decimal("1000.00"), (results, errors)
    assert len([r for r in results if r]) == 1, (results, errors)
    # Losers are clean business rejections - never a duplicate payment number (IntegrityError).
    from sqlalchemy.exc import IntegrityError
    assert not any(isinstance(e, IntegrityError) for e in errors), errors

"""Stale PENDING Razorpay payments are settled from Razorpay's own record when no webhook arrived."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from backend.app.models import Invoice, InvoiceStatus, Payment, PaymentGateway, PaymentMethod, PaymentStatus
from backend.app.models.base import utcnow
from backend.app.services import gateway_reconciliation_service as recon
from backend.app.services import razorpay_gateway

CREDS = razorpay_gateway.RazorpayCredentials("rzp_test_key", "test_secret", "whsec")


def _pending(db, tenant, invoice, *, age=timedelta(hours=2), amount=None):
    payment = Payment(
        organization_id=tenant.organization.id,
        payment_number=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        customer_id=invoice.customer_id,
        amount=Decimal(amount or invoice.amount_due),
        currency="INR",
        method=PaymentMethod.RAZORPAY,
        gateway=PaymentGateway.RAZORPAY,
        status=PaymentStatus.PENDING,
        gateway_order_id=f"order_{uuid.uuid4().hex[:14]}",
        gateway_payload={"notes": {"invoice_id": invoice.id, "organization_id": tenant.organization.id}},
    )
    db.add(payment)
    db.commit()
    payment.created_at = utcnow() - age
    db.commit()
    db.refresh(payment)
    return payment


@pytest.fixture
def gateway(monkeypatch):
    """Fake Razorpay: order id -> list of payment attempts."""
    orders = {}
    calls = []
    monkeypatch.setattr(razorpay_gateway, "credentials_for", lambda db_, oid: CREDS)

    def fetch(order_id, creds=None):
        calls.append(order_id)
        return orders.get(order_id, [])

    monkeypatch.setattr(razorpay_gateway, "fetch_order_payments", fetch)
    return orders, calls


def _attempt(payment, status, **extra):
    return {"id": f"pay_{uuid.uuid4().hex[:10]}", "order_id": payment.gateway_order_id, "status": status,
            "amount": int(payment.amount * 100), "currency": "INR", **extra}


def _reload(db, model, id_):
    db.expire_all()
    return db.get(model, id_)


def test_captured_at_gateway_but_never_notified_is_captured_and_allocated(db, tenant, gateway):
    orders, _ = gateway
    inv = tenant.invoice(tenant.customer(), amount="500.00")
    payment = _pending(db, tenant, inv)
    orders[payment.gateway_order_id] = [_attempt(payment, "failed"), _attempt(payment, "captured")]

    counts = recon.reconcile_stale_gateway_payments(db)

    assert counts["captured"] == 1 and counts["errors"] == 0
    settled = _reload(db, Payment, payment.id)
    assert settled.status == PaymentStatus.SUCCEEDED
    assert settled.gateway_payment_id == orders[payment.gateway_order_id][1]["id"]
    assert settled.gateway_signature_verified is False  # fetched with our keys, not browser-signed
    assert _reload(db, Invoice, inv.id).status == InvoiceStatus.PAID

    # Running again changes nothing and never books the money twice.
    again = recon.reconcile_stale_gateway_payments(db)
    assert again["captured"] == 0
    assert len(_reload(db, Payment, payment.id).allocations) == 1


def test_all_attempts_failed_marks_the_payment_failed(db, tenant, gateway):
    orders, _ = gateway
    inv = tenant.invoice(tenant.customer(), amount="300.00")
    payment = _pending(db, tenant, inv)
    orders[payment.gateway_order_id] = [_attempt(payment, "failed", error_description="Card declined")]

    assert recon.reconcile_stale_gateway_payments(db)["failed"] == 1
    failed = _reload(db, Payment, payment.id)
    assert failed.status == PaymentStatus.FAILED
    assert failed.failure_reason == "Card declined"
    assert _reload(db, Invoice, inv.id).status != InvoiceStatus.PAID


@pytest.mark.parametrize("attempts", [[], [{"status": "authorized"}], [{"status": "created"}]])
def test_no_final_outcome_leaves_the_payment_pending(db, tenant, gateway, attempts):
    orders, _ = gateway
    inv = tenant.invoice(tenant.customer(), amount="250.00")
    payment = _pending(db, tenant, inv)
    orders[payment.gateway_order_id] = [{**_attempt(payment, a["status"])} for a in attempts]

    assert recon.reconcile_stale_gateway_payments(db)["unchanged"] == 1
    assert _reload(db, Payment, payment.id).status == PaymentStatus.PENDING


def test_amount_mismatch_is_never_applied(db, tenant, gateway):
    orders, _ = gateway
    inv = tenant.invoice(tenant.customer(), amount="400.00")
    payment = _pending(db, tenant, inv)
    orders[payment.gateway_order_id] = [{**_attempt(payment, "captured"), "amount": 100}]

    counts = recon.reconcile_stale_gateway_payments(db)
    assert counts["errors"] == 1 and counts["captured"] == 0
    assert _reload(db, Payment, payment.id).status == PaymentStatus.PENDING


def test_recent_and_very_old_orders_are_not_polled(db, tenant, gateway):
    _, calls = gateway
    inv = tenant.invoice(tenant.customer(), amount="100.00")
    fresh = _pending(db, tenant, inv, age=timedelta(minutes=5))       # browser/webhook still in flight
    ancient = _pending(db, tenant, inv, age=timedelta(days=30))
    recon.reconcile_stale_gateway_payments(db)
    assert fresh.gateway_order_id not in calls
    assert ancient.gateway_order_id not in calls


def test_unconfigured_gateway_is_skipped(db, tenant, monkeypatch):
    monkeypatch.setattr(razorpay_gateway, "credentials_for",
                        lambda db_, oid: razorpay_gateway.RazorpayCredentials(None, None, None))

    def must_not_call(*a, **k):
        raise AssertionError("Razorpay must not be called without credentials")

    monkeypatch.setattr(razorpay_gateway, "fetch_order_payments", must_not_call)
    inv = tenant.invoice(tenant.customer(), amount="100.00")
    payment = _pending(db, tenant, inv)
    counts = recon.reconcile_stale_gateway_payments(db)
    assert counts["errors"] == 0
    assert _reload(db, Payment, payment.id).status == PaymentStatus.PENDING


def test_scheduler_run_reconciles_stale_payments(db, tenant, gateway):
    from backend.app.services import scheduler

    orders, _ = gateway
    inv = tenant.invoice(tenant.customer(), amount="600.00")
    payment = _pending(db, tenant, inv)
    orders[payment.gateway_order_id] = [_attempt(payment, "captured")]

    counts = scheduler.run_billing_jobs(db)

    assert counts["gateway_payments_reconciled"] >= 1
    assert _reload(db, Payment, payment.id).status == PaymentStatus.SUCCEEDED

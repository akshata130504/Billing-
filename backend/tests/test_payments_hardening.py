"""Payment integrity hardening: webhooks, refunds, public invoice verification, recurring
charges, dunning, credit notes, GST numbering/exports, PDF logo loading and idempotency."""
import hashlib
import hmac
import json
import os
import time
import uuid
from decimal import Decimal

import pytest

from backend.app.core.config import settings
from backend.app.core.exceptions import InvalidStateError
from backend.app.models import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    Refund,
    RefundStatus,
    WebhookEvent,
)
from backend.app.services import payment_service, razorpay_gateway
from backend.app.services.gateways.razorpay_adapter import RazorpayGatewayAdapter

INVOICES = "/api/v1/invoices"
WEBHOOK = "/api/v1/webhooks/razorpay"
SECRET = "hardening_webhook_secret"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post_event(client, event: str, kind: str, entity: dict, *, secret: str = SECRET, created_at=None):
    payload = {"event": event, "payload": {kind: {"entity": entity}}}
    if created_at is not None:
        payload["created_at"] = created_at
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex}",
               "X-Razorpay-Signature": _sign(body, secret)}
    return client.post(WEBHOOK, content=body, headers=headers), headers["X-Razorpay-Event-Id"]


def _pending(db, tenant, invoice, amount=None, status=PaymentStatus.PENDING) -> Payment:
    payment = Payment(
        organization_id=tenant.organization.id,
        payment_number=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        customer_id=invoice.customer_id,
        amount=Decimal(amount or invoice.amount_due),
        currency="INR",
        method=PaymentMethod.RAZORPAY,
        gateway=PaymentGateway.RAZORPAY,
        status=status,
        gateway_order_id=f"order_{uuid.uuid4().hex[:14]}",
        gateway_payload={"notes": {"invoice_id": invoice.id, "organization_id": tenant.organization.id}},
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def _sent_invoice(client, headers, customer, amount="1000.00", tax="0"):
    res = client.post(INVOICES, headers=headers, json={
        "customer_id": customer.id,
        "items": [{"description": "Item", "quantity": "1", "unit_price": amount, "tax_rate_pct": tax}],
    })
    assert res.status_code == 201, res.text
    inv_id = res.json()["id"]
    assert client.post(f"{INVOICES}/{inv_id}/send", headers=headers).status_code == 200
    return inv_id


# --- webhooks -------------------------------------------------------------------------------------------


def test_capture_after_failure_settles_payment(client, tenant, db, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    inv = tenant.invoice(tenant.customer(), amount="800.00")
    payment = _pending(db, tenant, inv)
    res, _ = _post_event(client, "payment.failed", "payment", {"id": "pay_first", "order_id": payment.gateway_order_id,
                                                                "error_description": "declined"})
    assert res.status_code == 200
    res, _ = _post_event(client, "payment.captured", "payment", {"id": "pay_retry_ok", "order_id": payment.gateway_order_id,
                                                                  "amount": 80000, "currency": "INR"})
    assert res.status_code == 200
    db.expire_all()
    payment = db.get(Payment, payment.id)
    assert payment.status == PaymentStatus.SUCCEEDED and payment.gateway_payment_id == "pay_retry_ok"
    assert db.get(Invoice, inv.id).status == InvoiceStatus.PAID


def test_unknown_order_is_retried_not_acknowledged(client, db, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    res, event_id = _post_event(client, "payment.captured", "payment",
                                {"id": "pay_x", "order_id": "order_not_yet_committed", "amount": 100}, created_at=int(time.time()))
    assert res.status_code == 503
    assert db.query(WebhookEvent).filter_by(event_id=event_id).count() == 0  # redelivery will be processed
    # An old event about an order we never had is acknowledged (stored with the error) so
    # Razorpay does not keep failing and disable the webhook.
    res, event_id = _post_event(client, "payment.captured", "payment",
                                {"id": "pay_y", "order_id": "order_foreign"}, created_at=int(time.time()) - 7200)
    assert res.status_code == 200
    evt = db.query(WebhookEvent).filter_by(event_id=event_id).one()
    assert "no payment" in evt.error


def test_amount_mismatch_is_permanent_error(client, tenant, db, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    inv = tenant.invoice(tenant.customer(), amount="500.00")
    payment = _pending(db, tenant, inv)
    res, event_id = _post_event(client, "payment.captured", "payment",
                                {"id": "pay_short", "order_id": payment.gateway_order_id, "amount": 100, "currency": "INR"})
    assert res.status_code == 200
    assert "amount mismatch" in db.query(WebhookEvent).filter_by(event_id=event_id).one().error.lower()
    db.expire_all()
    assert db.get(Payment, payment.id).status == PaymentStatus.PENDING



def test_currency_mismatch_is_permanent_error(client, tenant, db, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    inv = tenant.invoice(tenant.customer(), amount="500.00")
    payment = _pending(db, tenant, inv)
    res, event_id = _post_event(client, "payment.captured", "payment",
                                {"id": "pay_usd", "order_id": payment.gateway_order_id, "amount": 50000, "currency": "USD"})
    assert res.status_code == 200
    assert "currency mismatch" in db.query(WebhookEvent).filter_by(event_id=event_id).one().error.lower()
    db.expire_all()
    assert db.get(Payment, payment.id).status == PaymentStatus.PENDING


def test_capture_without_amount_is_not_applied(client, tenant, db, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    inv = tenant.invoice(tenant.customer(), amount="500.00")
    payment = _pending(db, tenant, inv)
    res, event_id = _post_event(client, "payment.captured", "payment",
                                {"id": "pay_noamt", "order_id": payment.gateway_order_id, "currency": "INR"})
    assert res.status_code == 200
    assert "amount mismatch" in db.query(WebhookEvent).filter_by(event_id=event_id).one().error.lower()
    db.expire_all()
    assert db.get(Payment, payment.id).status == PaymentStatus.PENDING

def test_org_webhook_secret_verifies_org_events(client, tenant, db, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    org_secret = "tenant_own_secret"
    org_id = tenant.organization.id
    real = razorpay_gateway.credentials_for
    monkeypatch.setattr(razorpay_gateway, "credentials_for",
                        lambda db_, oid: razorpay_gateway.RazorpayCredentials("k", "s", org_secret) if oid == org_id else real(db_, oid))
    inv = tenant.invoice(tenant.customer(), amount="200.00")
    payment = _pending(db, tenant, inv)
    entity = {"id": "pay_org", "order_id": payment.gateway_order_id, "amount": 20000, "currency": "INR",
              "notes": {"organization_id": org_id}}
    res, _ = _post_event(client, "payment.captured", "payment", entity, secret=org_secret)
    assert res.status_code == 200
    db.expire_all()
    assert db.get(Payment, payment.id).status == PaymentStatus.SUCCEEDED
    # Some other secret is still rejected.
    res, _ = _post_event(client, "payment.captured", "payment", entity, secret="nope")
    assert res.status_code == 400


def _settled_razorpay_payment(db, tenant, invoice):
    payment = _pending(db, tenant, invoice)
    payment_service.capture_gateway_payment(db, payment, invoice, gateway_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
                                            actor_label="test")
    db.commit()
    return payment


def test_refund_processed_is_deduplicated(client, tenant, db, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    inv = tenant.invoice(tenant.customer(), amount="1000.00")
    payment = _settled_razorpay_payment(db, tenant, inv)
    entity = {"id": "rfnd_dup", "payment_id": payment.gateway_payment_id, "amount": 40000}
    for _ in range(2):  # two distinct deliveries (different event ids) of the same refund
        res, _ = _post_event(client, "refund.processed", "refund", entity)
        assert res.status_code == 200
    db.expire_all()
    payment = db.get(Payment, payment.id)
    assert payment.amount_refunded == Decimal("400.00")
    assert db.query(Refund).filter_by(gateway_refund_id="rfnd_dup").count() == 1


def test_pending_refund_settles_on_processed_and_discards_on_failed(client, tenant, auth_headers, db, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    creds = razorpay_gateway.RazorpayCredentials("k", "s", None)
    monkeypatch.setattr(razorpay_gateway, "credentials_for", lambda db_, oid: creds)
    ids = iter(["rfnd_p1", "rfnd_p2"])
    monkeypatch.setattr(razorpay_gateway, "refund_payment", lambda *a, **k: {"id": next(ids), "status": "pending"})
    inv = tenant.invoice(tenant.customer(), amount="1000.00")
    payment = _settled_razorpay_payment(db, tenant, inv)

    res = client.post(f"/api/v1/payments/{payment.id}/refund", headers=auth_headers, json={"amount": "300.00", "reason": "x"})
    assert res.status_code == 200, res.text
    assert res.json()["amount_refunded"] == "0.00"  # not booked until Razorpay confirms
    # Only 700 remains refundable while 300 is in flight.
    over = client.post(f"/api/v1/payments/{payment.id}/refund", headers=auth_headers, json={"amount": "800.00"})
    assert over.status_code == 422

    res, _ = _post_event(client, "refund.processed", "refund", {"id": "rfnd_p1", "payment_id": payment.gateway_payment_id, "amount": 30000})
    assert res.status_code == 200
    db.expire_all()
    assert db.get(Payment, payment.id).amount_refunded == Decimal("300.00")
    assert db.get(Invoice, inv.id).amount_due == Decimal("300.00")

    client.post(f"/api/v1/payments/{payment.id}/refund", headers=auth_headers, json={"amount": "100.00"})
    res, _ = _post_event(client, "refund.failed", "refund", {"id": "rfnd_p2", "payment_id": payment.gateway_payment_id, "amount": 10000})
    assert res.status_code == 200
    db.expire_all()
    assert db.query(Refund).filter_by(gateway_refund_id="rfnd_p2").one().status == RefundStatus.FAILED
    assert db.get(Payment, payment.id).amount_refunded == Decimal("300.00")


def test_failed_gateway_refund_is_not_applied(client, tenant, auth_headers, db, monkeypatch):
    creds = razorpay_gateway.RazorpayCredentials("k", "s", None)
    monkeypatch.setattr(razorpay_gateway, "credentials_for", lambda db_, oid: creds)
    monkeypatch.setattr(razorpay_gateway, "refund_payment", lambda *a, **k: {"id": "rfnd_bad", "status": "failed"})
    inv = tenant.invoice(tenant.customer(), amount="500.00")
    payment = _settled_razorpay_payment(db, tenant, inv)
    res = client.post(f"/api/v1/payments/{payment.id}/refund", headers=auth_headers, json={"amount": "100.00"})
    assert res.status_code == 502
    db.expire_all()
    assert db.get(Payment, payment.id).amount_refunded == Decimal("0.00")
    assert db.get(Invoice, inv.id).status == InvoiceStatus.PAID


def test_same_gateway_payment_cannot_settle_two_payments(db, tenant):
    customer = tenant.customer()
    inv1 = tenant.invoice(customer, amount="100.00")
    inv2 = tenant.invoice(customer, amount="100.00")
    p1, p2 = _pending(db, tenant, inv1), _pending(db, tenant, inv2)
    payment_service.capture_gateway_payment(db, p1, inv1, gateway_payment_id="pay_once", actor_label="t")
    db.commit()
    from backend.app.core.exceptions import ConflictAppError

    with pytest.raises(ConflictAppError):
        payment_service.capture_gateway_payment(db, p2, inv2, gateway_payment_id="pay_once", actor_label="t")
    db.rollback()


# --- public invoice page ------------------------------------------------------------------------------


@pytest.fixture()
def public_rzp(monkeypatch):
    creds = razorpay_gateway.RazorpayCredentials("rzp_key", "rzp_secret", None)
    state = {"payments": {}}
    monkeypatch.setattr(razorpay_gateway, "credentials_for", lambda db_, oid: creds)
    monkeypatch.setattr(razorpay_gateway, "create_order",
                        lambda amount_paise, currency, receipt, notes=None, **k: {"id": f"order_{uuid.uuid4().hex[:8]}", "amount": amount_paise, "currency": currency})
    monkeypatch.setattr(razorpay_gateway, "fetch_payment", lambda pid, **k: state["payments"][pid])
    return state


def _public_sig(order_id, pid):
    return hmac.new(b"rzp_secret", f"{order_id}|{pid}".encode(), hashlib.sha256).hexdigest()


def test_public_invoice_minimum_partial_amount(client, tenant, public_rzp):
    inv = tenant.invoice(tenant.customer(), amount="500.00")
    url = f"/api/v1/public/invoices/{inv.public_token}/razorpay-order"
    assert client.post(url, json={"amount": "0.50"}).status_code == 422
    assert client.post(url, json={"amount": "1.00"}).status_code == 200
    tiny = tenant.invoice(tenant.customer(), amount="0.75")
    tiny_url = f"/api/v1/public/invoices/{tiny.public_token}/razorpay-order"
    assert client.post(tiny_url, json={"amount": "0.50"}).status_code == 422
    assert client.post(tiny_url, json={}).status_code == 200


def test_public_invoice_verify_checks_gateway_amount(client, tenant, db, public_rzp):
    inv = tenant.invoice(tenant.customer(), amount="500.00")
    order = client.post(f"/api/v1/public/invoices/{inv.public_token}/razorpay-order", json={}).json()
    order_id = order["order_id"]
    verify = f"/api/v1/public/invoices/{inv.public_token}/razorpay-verify"

    public_rzp["payments"]["pay_short"] = {"id": "pay_short", "order_id": order_id, "status": "captured", "amount": 100, "currency": "INR"}
    res = client.post(verify, json={"razorpay_order_id": order_id, "razorpay_payment_id": "pay_short",
                                    "razorpay_signature": _public_sig(order_id, "pay_short")})
    assert res.status_code == 422
    db.expire_all()
    assert db.get(Invoice, inv.id).status == InvoiceStatus.SENT

    public_rzp["payments"]["pay_ok"] = {"id": "pay_ok", "order_id": order_id, "status": "captured", "amount": 50000, "currency": "INR"}
    res = client.post(verify, json={"razorpay_order_id": order_id, "razorpay_payment_id": "pay_ok",
                                    "razorpay_signature": _public_sig(order_id, "pay_ok")})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.get(Invoice, inv.id).status == InvoiceStatus.PAID


# --- recurring charges / dunning ------------------------------------------------------------------------


def test_razorpay_adapter_recurring_charge_is_pending(monkeypatch):
    creds = razorpay_gateway.RazorpayCredentials("k", "s", None)
    calls = {}
    monkeypatch.setattr(razorpay_gateway, "create_order", lambda **kw: calls.setdefault("order", kw) and {"id": "order_rec_1"})
    monkeypatch.setattr(razorpay_gateway, "create_recurring_payment",
                        lambda payload, **kw: calls.setdefault("recurring", payload) and {"razorpay_payment_id": "pay_rec_1", "razorpay_order_id": "order_rec_1"})
    adapter = RazorpayGatewayAdapter()
    res = adapter.charge(amount=Decimal("250.00"), currency="INR", customer_id="c1", payment_method_token="token_1",
                         notes={"invoice_id": "i1"}, credentials=creds, gateway_customer_id="cust_1", email="a@b.c")
    assert res.success and res.pending and res.gateway_payment_id == "pay_rec_1" and res.gateway_order_id == "order_rec_1"
    assert calls["order"]["amount_paise"] == 25000 and calls["order"]["customer_id"] == "cust_1"
    rec = calls["recurring"]
    assert rec["token"] == "token_1" and rec["customer_id"] == "cust_1" and rec["order_id"] == "order_rec_1"
    assert rec["recurring"] == "1" and rec["amount"] == 25000

    # Without a Razorpay customer id the token cannot be charged.
    res = adapter.charge(amount=Decimal("1"), currency="INR", customer_id="c1", payment_method_token="token_1", credentials=creds)
    assert not res.success and res.error_category == "payment_method_not_chargeable"


def test_dunning_pending_charge_waits_for_webhook(client, tenant, db, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from backend.app.models.dunning import DunningCase, DunningCaseStatus
    from backend.app.models.subscriptions import Subscription, SubscriptionStatus
    from backend.app.services import dunning_service
    from backend.app.services.gateways.base import GatewayChargeResult
    from backend.app.services.gateways.registry import get_gateway_adapter, register_gateway_adapter

    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1200.00")
    sub = Subscription(organization_id=tenant.organization.id, subscription_number=f"SUB-{uuid.uuid4().hex[:6]}",
                       customer_id=customer.id, plan_id=plan.id, status=SubscriptionStatus.PAST_DUE, quantity=1,
                       start_date=datetime.now().date(), current_period_start=datetime.now().date(),
                       current_period_end=datetime.now().date() + timedelta(days=30))
    db.add(sub)
    db.commit()
    inv = tenant.invoice(customer, amount="1200.00")
    inv.subscription_id = sub.id
    db.add(CustomerPaymentMethod(organization_id=tenant.organization.id, customer_id=customer.id, gateway=PaymentGateway.RAZORPAY,
                                 gateway_customer_id="cust_d", gateway_token="token_d", is_default=True,
                                 status=CustomerPaymentMethodStatus.ACTIVE))
    db.commit()
    case = dunning_service.trigger_dunning_for_failed_payment(db, organization_id=tenant.organization.id, invoice_id=inv.id,
                                                              customer_id=customer.id, subscription_id=sub.id, reason="declined")
    case.next_retry_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    real = get_gateway_adapter(PaymentGateway.RAZORPAY)

    class _Pending:
        gateway_type = PaymentGateway.RAZORPAY

        def charge(self, **kwargs):
            return GatewayChargeResult(success=True, pending=True, gateway_payment_id="pay_dun_1", gateway_order_id="order_dun_1")

    register_gateway_adapter(PaymentGateway.RAZORPAY, _Pending())
    try:
        res = dunning_service.execute_dunning_retries(db, tenant.organization.id)
        db.commit()
    finally:
        register_gateway_adapter(PaymentGateway.RAZORPAY, real)
    assert res["recovered_count"] == 0
    db.expire_all()
    case = db.get(DunningCase, case.id)
    assert case.status == DunningCaseStatus.RETRYING
    assert db.get(Invoice, inv.id).status != InvoiceStatus.PAID  # nothing collected yet
    pending = db.query(Payment).filter(Payment.gateway_order_id == "order_dun_1").one()
    assert pending.status == PaymentStatus.PENDING

    res_wh, _ = _post_event(client, "payment.captured", "payment", {"id": "pay_dun_1", "order_id": "order_dun_1",
                                                                     "amount": 120000, "currency": "INR"})
    assert res_wh.status_code == 200
    db.expire_all()
    assert db.get(Invoice, inv.id).status == InvoiceStatus.PAID
    case = db.get(DunningCase, case.id)
    case.next_retry_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    assert dunning_service.execute_dunning_retries(db, tenant.organization.id)["recovered_count"] == 1


# --- credit notes ------------------------------------------------------------------------------------------


def test_credit_application_survives_payment_recompute(client, tenant, auth_headers, db):
    customer = tenant.customer()
    inv_id = _sent_invoice(client, auth_headers, customer, "1000.00")
    cn = client.post("/api/v1/credit-notes", headers=auth_headers, json={
        "customer_id": customer.id, "invoice_id": inv_id, "lines": [{"description": "Goodwill", "amount": "300.00"}],
    }).json()
    assert client.post(f"/api/v1/credit-notes/{cn['id']}/apply", headers=auth_headers,
                       json={"invoice_id": inv_id, "amount": "300.00"}).status_code == 200
    # A payment triggers recompute_invoice, which used to erase the credit.
    res = client.post(f"{INVOICES}/{inv_id}/record-payment", headers=auth_headers, json={"amount": "200.00", "method": "cash"})
    assert res.status_code == 201, res.text
    inv = client.get(f"{INVOICES}/{inv_id}", headers=auth_headers).json()
    assert inv["amount_paid"] == "500.00" and inv["amount_due"] == "500.00"
    assert inv["status"] == "partially_paid"


def test_credit_note_numbering_gst_split_and_invoice_link(client, tenant, auth_headers, db):
    customer = tenant.customer()
    inv_id = _sent_invoice(client, auth_headers, customer, "1000.00", tax="18")
    first = client.post("/api/v1/credit-notes", headers=auth_headers, json={
        "customer_id": customer.id, "invoice_id": inv_id,
        "lines": [{"description": "Refund of overcharge", "amount": "100.00", "tax_rate_pct": "18"}],
    })
    assert first.status_code == 201, first.text
    cn = first.json()
    assert cn["invoice_id"] == inv_id and cn["tax_amount"] == "18.00" and cn["total"] == "118.00"
    assert Decimal(cn["cgst_amount"]) + Decimal(cn["sgst_amount"]) + Decimal(cn["igst_amount"]) == Decimal("18.00")
    second = client.post("/api/v1/credit-notes", headers=auth_headers, json={
        "customer_id": customer.id, "lines": [{"description": "x", "amount": "1.00"}]}).json()
    assert int(second["credit_note_number"].split("-")[-1]) == int(cn["credit_note_number"].split("-")[-1]) + 1
    other = tenant.customer()
    assert client.post("/api/v1/credit-notes", headers=auth_headers, json={
        "customer_id": other.id, "invoice_id": inv_id, "lines": [{"description": "x", "amount": "1.00"}]}).status_code == 409


# --- GST numbering / exports / PDF -------------------------------------------------------------------------


def test_only_latest_draft_can_be_deleted(client, tenant, auth_headers):
    customer = tenant.customer()
    items = [{"description": "Item", "quantity": "1", "unit_price": "10.00", "tax_rate_pct": "0"}]
    a = client.post(INVOICES, headers=auth_headers, json={"customer_id": customer.id, "items": items}).json()
    b = client.post(INVOICES, headers=auth_headers, json={"customer_id": customer.id, "items": items}).json()
    # Deleting an earlier draft would leave a gap in the series.
    assert client.delete(f"{INVOICES}/{a['id']}", headers=auth_headers).status_code == 409
    assert client.delete(f"{INVOICES}/{b['id']}", headers=auth_headers).status_code == 204
    c = client.post(INVOICES, headers=auth_headers, json={"customer_id": customer.id, "items": items}).json()
    assert c["invoice_number"] == b["invoice_number"]  # number re-used, series stays continuous
    assert client.post(f"{INVOICES}/{a['id']}/void", headers=auth_headers, json={"reason": "not needed"}).status_code == 200


def test_export_invoice_is_zero_rated(client, tenant, auth_headers):
    customer = tenant.customer(billing_country="US")
    res = client.post(INVOICES, headers=auth_headers, json={
        "customer_id": customer.id, "items": [{"description": "SaaS", "quantity": "1", "unit_price": "1000.00", "tax_rate_pct": "18"}]})
    inv = res.json()
    assert inv["supply_type"] == "export"
    assert inv["tax_amount"] == "0.00" and inv["total"] == "1000.00"


def test_pdf_logo_never_fetches_remote_urls(monkeypatch, tmp_path):
    import urllib.request

    from backend.app.services import invoice_pdf

    def _boom(*a, **k):
        raise AssertionError("remote fetch attempted")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    assert invoice_pdf._load_logo_image("https://example.com/logo.png") is None
    assert invoice_pdf._load_logo_image("http://169.254.169.254/latest/meta-data") is None
    assert invoice_pdf._load_logo_image("/uploads/../../etc/passwd") is None


def test_pdf_uses_frozen_gstins(tenant, db):
    from backend.app.services import invoice_pdf

    captured = []
    real_p = invoice_pdf._p
    customer = tenant.customer(gstin="29ABCDE1234F1Z5")
    inv = tenant.invoice(customer, amount="100.00")
    inv.supplier_gstin = "27AAAAA0000A1Z5"
    inv.customer_gstin = "29ABCDE1234F1Z5"
    db.commit()
    tenant.organization.gstin = "07ZZZZZ9999Z1Z5"  # changed after issue
    customer.gstin = "07YYYYY8888Y1Z5"
    db.commit()
    db.refresh(inv)

    def spy(text, style):
        captured.append(text)
        return real_p(text, style)

    invoice_pdf._p = spy
    try:
        invoice_pdf.render_invoice_pdf(inv, tenant.organization)
    finally:
        invoice_pdf._p = real_p
    assert "GSTIN: 27AAAAA0000A1Z5" in captured and "GSTIN: 29ABCDE1234F1Z5" in captured
    assert "GSTIN: 07ZZZZZ9999Z1Z5" not in captured


# --- idempotency ---------------------------------------------------------------------------------------------


def test_record_payment_idempotency_key(client, tenant, auth_headers, db):
    customer = tenant.customer()
    inv_id = _sent_invoice(client, auth_headers, customer, "900.00")
    headers = {**auth_headers, "Idempotency-Key": f"idem-{uuid.uuid4().hex}"}
    body = {"amount": "300.00", "method": "bank_transfer"}
    r1 = client.post(f"{INVOICES}/{inv_id}/record-payment", headers=headers, json=body)
    r2 = client.post(f"{INVOICES}/{inv_id}/record-payment", headers=headers, json=body)
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert client.get(f"{INVOICES}/{inv_id}", headers=auth_headers).json()["amount_paid"] == "300.00"
    # Same key, different body -> conflict.
    assert client.post(f"{INVOICES}/{inv_id}/record-payment", headers=headers, json={**body, "amount": "10.00"}).status_code == 409


def test_create_payment_idempotency_key(client, tenant, auth_headers):
    customer = tenant.customer()
    headers = {**auth_headers, "Idempotency-Key": f"idem-{uuid.uuid4().hex}"}
    body = {"customer_id": customer.id, "amount": "50.00", "method": "cash"}
    r1 = client.post("/api/v1/payments", headers=headers, json=body)
    r2 = client.post("/api/v1/payments", headers=headers, json=body)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


def test_webhook_receiver_is_rate_limited_per_client_ip(client, monkeypatch, db):
    """Unsigned junk from one source cannot fill webhook_events/audit_logs without limit."""
    from fastapi.testclient import TestClient

    from backend.app.main import app

    monkeypatch.setattr(settings, "WEBHOOK_RATE_LIMIT", "3/minute")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    ip = f"10.5.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    attacker = TestClient(app, client=(ip, 50000))
    body = json.dumps({"event": "payment.captured", "payload": {}}).encode()
    headers = {"Content-Type": "application/json", "X-Razorpay-Signature": "bad"}
    before = db.query(WebhookEvent).count()
    statuses = [attacker.post(WEBHOOK, content=body, headers=headers).status_code for _ in range(5)]
    assert statuses[:3] == [400, 400, 400]
    assert statuses[3:] == [429, 429]
    db.expire_all()
    assert db.query(WebhookEvent).count() == before + 3  # limited requests store nothing
    # A different source is unaffected.
    other = TestClient(app, client=(f"10.4.{uuid.uuid4().int % 250}.1", 50000))
    assert other.post(WEBHOOK, content=body, headers=headers).status_code == 400

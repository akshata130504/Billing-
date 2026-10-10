"""Hosted checkout payment flow: order + pending payment, verified confirm, webhook completion,
GST invoicing for subscriptions/add-ons, and the hardening around the public endpoint."""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.app.core.config import settings
from backend.app.models import (
    CustomerPaymentMethod,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
)
from backend.app.models.checkout import CheckoutSession, CheckoutSessionPurpose, CheckoutSessionStatus
from backend.app.services import razorpay_gateway

KEY_SECRET = "rzp_test_secret_value"
WEBHOOK_SECRET = "platform_webhook_secret"


class FakeRazorpay:
    """Stands in for the Razorpay API at the razorpay_gateway module boundary."""

    def __init__(self):
        self.orders = {}
        self.payments = {}
        self.counter = 0

    def install(self, monkeypatch):
        creds = razorpay_gateway.RazorpayCredentials("rzp_test_key", KEY_SECRET, WEBHOOK_SECRET)
        monkeypatch.setattr(razorpay_gateway, "credentials_for", lambda db, org_id: creds)
        monkeypatch.setattr(razorpay_gateway, "create_order", self.create_order)
        monkeypatch.setattr(razorpay_gateway, "fetch_payment", self.fetch_payment)
        monkeypatch.setattr(razorpay_gateway, "create_customer", lambda *a, **k: {"id": "cust_test_1"})
        monkeypatch.setattr(razorpay_gateway, "fetch_card", lambda *a, **k: {})
        monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
        return self

    def create_order(self, amount_paise, currency, receipt, notes=None, *, creds=None, customer_id=None):
        self.counter += 1
        order = {"id": f"order_{self.counter}_{uuid.uuid4().hex[:6]}", "amount": int(amount_paise), "currency": currency,
                 "notes": notes or {}, "customer_id": customer_id}
        self.orders[order["id"]] = order
        return order

    def pay(self, order_id, *, status="captured", amount=None, token=True):
        pid = f"pay_{uuid.uuid4().hex[:12]}"
        order = self.orders[order_id]
        self.payments[pid] = {
            "id": pid,
            "order_id": order_id,
            "status": status,
            "amount": order["amount"] if amount is None else amount,
            "currency": order["currency"],
            "method": "card",
            "token_id": "token_saved_123" if token else None,
            "customer_id": order.get("customer_id"),
            "card": {"network": "MasterCard", "last4": "5555", "expiry_month": 12, "expiry_year": 2030},
        }
        return pid

    def fetch_payment(self, payment_id, *, creds=None):
        return self.payments[payment_id]


def _sig(order_id, payment_id):
    return hmac.new(KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def _create_session(client, headers, **body):
    res = client.post("/api/v1/checkout/sessions", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture()
def rzp(monkeypatch):
    return FakeRazorpay().install(monkeypatch)


def test_invoice_checkout_verified_confirm_saves_real_card(client, tenant, auth_headers, db, rzp):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="2000.00")
    session = _create_session(client, auth_headers, purpose="invoice_payment", invoice_id=inv.id, save_payment_method=True)
    token = session["token"]
    assert session["checkout_url"] == f"/checkout/{token}"

    view = client.get(f"/api/v1/checkout/public/{token}").json()
    assert view["gateway_available"] is True
    order_id = view["gateway_order_id"]
    assert order_id and view["gateway_key_id"] == "rzp_test_key"
    assert view["gateway_customer_id"] == "cust_test_1"
    # The pending payment exists before the customer pays (webhook can settle it).
    pending = db.query(Payment).filter(Payment.gateway_order_id == order_id).one()
    assert pending.status == PaymentStatus.PENDING and pending.amount == Decimal("2000.00")
    # Re-opening the page reuses the same order.
    assert client.get(f"/api/v1/checkout/public/{token}").json()["gateway_order_id"] == order_id

    pid = rzp.pay(order_id)
    res = client.post(
        f"/api/v1/checkout/public/{token}/confirm",
        json={"razorpay_payment_id": pid, "razorpay_order_id": order_id, "razorpay_signature": _sig(order_id, pid),
              "card_last4": "4242", "card_brand": "Visa", "save_payment_method": True},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "successful"

    db.expire_all()
    inv = db.get(Invoice, inv.id)
    assert inv.status == InvoiceStatus.PAID and inv.amount_due == Decimal("0.00")
    payment = db.get(Payment, pending.id)
    assert payment.status == PaymentStatus.SUCCEEDED and payment.gateway_payment_id == pid
    assert len(payment.allocations) == 1

    pm = db.query(CustomerPaymentMethod).filter(CustomerPaymentMethod.customer_id == customer.id).one()
    # Details come from Razorpay, never from the browser-supplied card_last4/card_brand.
    assert pm.last4 == "5555" and pm.card_brand == "MasterCard"
    assert pm.gateway_token == "token_saved_123" and pm.gateway_customer_id == "cust_test_1"

    # Double submit is idempotent: no second payment.
    again = client.post(
        f"/api/v1/checkout/public/{token}/confirm",
        json={"razorpay_payment_id": pid, "razorpay_order_id": order_id, "razorpay_signature": _sig(order_id, pid)},
    )
    assert again.status_code == 200
    assert db.query(Payment).filter(Payment.customer_id == customer.id).count() == 1


def test_no_card_saved_without_gateway_token(client, tenant, auth_headers, db, rzp):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="300.00")
    token = _create_session(client, auth_headers, purpose="invoice_payment", invoice_id=inv.id, save_payment_method=True)["token"]
    order_id = client.get(f"/api/v1/checkout/public/{token}").json()["gateway_order_id"]
    pid = rzp.pay(order_id, token=False)
    res = client.post(
        f"/api/v1/checkout/public/{token}/confirm",
        json={"razorpay_payment_id": pid, "razorpay_order_id": order_id, "razorpay_signature": _sig(order_id, pid)},
    )
    assert res.status_code == 200
    assert db.query(CustomerPaymentMethod).filter(CustomerPaymentMethod.customer_id == customer.id).count() == 0


def test_public_confirm_rejects_manual_tokens_forgery_and_replay(client, tenant, auth_headers, db, rzp):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="3000.00")
    token = _create_session(client, auth_headers, purpose="invoice_payment", invoice_id=inv.id)["token"]
    order_id = client.get(f"/api/v1/checkout/public/{token}").json()["gateway_order_id"]
    url = f"/api/v1/checkout/public/{token}/confirm"

    # The manual gateway can never settle a public checkout.
    assert client.post(url, json={"gateway": "manual"}).status_code == 400
    # Nor can a browser-supplied vaulted token.
    assert client.post(url, json={"gateway_token": "tok_anything"}).status_code == 400
    # Browser card details alone are not a payment.
    assert client.post(url, json={"card_last4": "1234", "card_brand": "Visa"}).status_code == 422

    pid = rzp.pay(order_id)
    # Forged signature.
    bad = client.post(url, json={"razorpay_payment_id": pid, "razorpay_order_id": order_id, "razorpay_signature": "forged"})
    assert bad.status_code == 422
    assert "signature verification failed" in bad.json()["error"]["message"].lower()

    # A genuinely signed payment for a *different* order (replay from another checkout) is refused.
    other_order = rzp.create_order(100, "INR", "x")["id"]
    other_pid = rzp.pay(other_order)
    replay = client.post(url, json={"razorpay_payment_id": other_pid, "razorpay_order_id": other_order,
                                    "razorpay_signature": _sig(other_order, other_pid)})
    assert replay.status_code == 422
    assert "order id does not match" in replay.json()["error"]["message"].lower()

    # Correctly signed but Razorpay says it was not captured / wrong amount.
    failed_pid = rzp.pay(order_id, status="failed")
    res = client.post(url, json={"razorpay_payment_id": failed_pid, "razorpay_order_id": order_id,
                                 "razorpay_signature": _sig(order_id, failed_pid)})
    assert res.status_code == 422
    short_pid = rzp.pay(order_id, amount=100)
    res = client.post(url, json={"razorpay_payment_id": short_pid, "razorpay_order_id": order_id,
                                 "razorpay_signature": _sig(order_id, short_pid)})
    assert res.status_code == 422 and "amount mismatch" in res.json()["error"]["message"].lower()

    db.expire_all()
    assert db.get(Invoice, inv.id).status != InvoiceStatus.PAID

    ok = client.post(url, json={"razorpay_payment_id": pid, "razorpay_order_id": order_id, "razorpay_signature": _sig(order_id, pid)})
    assert ok.status_code == 200
    db.expire_all()
    assert db.get(Invoice, inv.id).status == InvoiceStatus.PAID


def test_webhook_completes_checkout_when_browser_closed(client, tenant, auth_headers, db, rzp):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1500.00")
    token = _create_session(client, auth_headers, purpose="invoice_payment", invoice_id=inv.id)["token"]
    order_id = client.get(f"/api/v1/checkout/public/{token}").json()["gateway_order_id"]
    pid = rzp.pay(order_id)

    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": rzp.payments[pid]}}}).encode()
    headers = {"Content-Type": "application/json", "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex}",
               "X-Razorpay-Signature": hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()}
    assert client.post("/api/v1/webhooks/razorpay", content=body, headers=headers).status_code == 200

    db.expire_all()
    session = db.query(CheckoutSession).filter(CheckoutSession.invoice_id == inv.id).one()
    assert session.status == CheckoutSessionStatus.SUCCESSFUL
    assert db.get(Invoice, inv.id).status == InvoiceStatus.PAID

    # A late browser confirm is idempotent (no double settlement).
    late = client.post(f"/api/v1/checkout/public/{token}/confirm",
                       json={"razorpay_payment_id": pid, "razorpay_order_id": order_id, "razorpay_signature": _sig(order_id, pid)})
    assert late.status_code == 200
    assert db.query(Payment).filter(Payment.customer_id == customer.id, Payment.status == PaymentStatus.SUCCEEDED).count() == 1


def test_new_subscription_checkout_issues_gst_invoice(client, tenant, auth_headers, db, rzp):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00")  # product carries 18% GST
    session = _create_session(client, auth_headers, purpose="new_subscription", plan_id=plan.id, customer_id=customer.id)
    assert Decimal(str(session["amount"])) == Decimal("1180.00")
    token = session["token"]
    order_id = client.get(f"/api/v1/checkout/public/{token}").json()["gateway_order_id"]
    assert rzp.orders[order_id]["amount"] == 118000
    pid = rzp.pay(order_id)
    res = client.post(f"/api/v1/checkout/public/{token}/confirm",
                      json={"razorpay_payment_id": pid, "razorpay_order_id": order_id, "razorpay_signature": _sig(order_id, pid)})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["subscription_id"] and out["invoice_id"]

    db.expire_all()
    sub = db.get(Subscription, out["subscription_id"])
    assert sub.status == SubscriptionStatus.ACTIVE and sub.customer_id == customer.id
    inv = db.get(Invoice, out["invoice_id"])
    assert inv.status == InvoiceStatus.PAID and inv.subscription_id == sub.id
    assert inv.tax_amount == Decimal("180.00") and inv.total == Decimal("1180.00")
    assert inv.cgst_amount + inv.sgst_amount + inv.igst_amount == inv.tax_amount
    assert inv.items and inv.items[0].plan_id == plan.id


def test_new_subscription_requires_customer_and_unsupported_purposes_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    res = client.post("/api/v1/checkout/sessions", headers=auth_headers, json={"purpose": "new_subscription", "plan_id": plan.id})
    assert res.status_code == 422
    for purpose in ("update_subscription", "update_card", "add_payment_method"):
        res = client.post("/api/v1/checkout/sessions", headers=auth_headers,
                          json={"purpose": purpose, "customer_id": customer.id, "subscription_id": "x"})
        assert res.status_code == 422, purpose


def test_one_time_addon_checkout_builds_invoice(client, tenant, auth_headers, db, rzp):
    customer = tenant.customer()
    session = _create_session(client, auth_headers, purpose="one_time_addon", customer_id=customer.id, amount="500.00",
                              metadata_snapshot={"description": "Setup help", "tax_rate_pct": "18", "gateway_order_id": "order_evil"})
    assert Decimal(str(session["amount"])) == Decimal("590.00")
    token = session["token"]
    view = client.get(f"/api/v1/checkout/public/{token}").json()
    order_id = view["gateway_order_id"]
    assert order_id != "order_evil"  # clients cannot pre-seed server-owned metadata
    pid = rzp.pay(order_id)
    res = client.post(f"/api/v1/checkout/public/{token}/confirm",
                      json={"razorpay_payment_id": pid, "razorpay_order_id": order_id, "razorpay_signature": _sig(order_id, pid)})
    assert res.status_code == 200
    db.expire_all()
    inv = db.get(Invoice, res.json()["invoice_id"])
    assert inv.status == InvoiceStatus.PAID and inv.total == Decimal("590.00")
    assert inv.invoice_number.startswith("INV-")


def test_no_gateway_configured_shows_unavailable(client, tenant, auth_headers):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="100.00")
    token = _create_session(client, auth_headers, purpose="invoice_payment", invoice_id=inv.id)["token"]
    view = client.get(f"/api/v1/checkout/public/{token}").json()
    assert view["gateway_available"] is False
    assert "contact the merchant" in view["gateway_message"].lower()


def test_trial_merchant_checkout_says_payments_not_accepted_yet(client, tenant, auth_headers, db):
    """BUG-15: a merchant in its free trial is not "temporarily unavailable" (suspended wording)."""
    inv = tenant.invoice(tenant.customer(), amount="100.00")
    token = _create_session(client, auth_headers, purpose="invoice_payment", invoice_id=inv.id)["token"]
    tenant.organization.module_access = "trial"
    db.commit()
    view = client.get(f"/api/v1/checkout/public/{token}").json()
    assert view["gateway_available"] is False
    assert "not accepting online payments yet" in view["gateway_message"]
    assert "temporarily unavailable" not in view["gateway_message"]


def test_session_list_never_exposes_usable_token(client, tenant, auth_headers, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="100.00")
    created = _create_session(client, auth_headers, purpose="invoice_payment", invoice_id=inv.id)
    items = client.get("/api/v1/checkout/sessions", headers=auth_headers).json()["items"]
    row = next(i for i in items if i["id"] == created["id"])
    assert row["token"].startswith("ref_") and row["checkout_url"] is None
    stored_hash = db.get(CheckoutSession, created["id"]).token
    # The stored hash is not accepted as a bearer token.
    assert client.get(f"/api/v1/checkout/public/{stored_hash}").status_code == 404


def test_expired_session_cannot_be_confirmed(client, tenant, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="1500.00")
    raw = "expired-token-" + uuid.uuid4().hex
    db.add(CheckoutSession(
        organization_id=tenant.organization.id,
        token=hashlib.sha256(raw.encode()).hexdigest(),
        purpose=CheckoutSessionPurpose.INVOICE_PAYMENT,
        status=CheckoutSessionStatus.CREATED,
        customer_id=customer.id,
        invoice_id=inv.id,
        amount=Decimal("1500.00"),
        currency="INR",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    ))
    db.commit()
    res = client.get(f"/api/v1/checkout/public/{raw}")
    assert res.status_code == 200
    assert res.json()["is_expired"] is True and res.json()["status"] == "expired"
    assert client.post(f"/api/v1/checkout/public/{raw}/confirm", json={"card_last4": "1111"}).status_code in (400, 422)

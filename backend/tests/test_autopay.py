"""UPI AutoPay / e-mandate through Razorpay Subscriptions (BUSINESS-217).

Razorpay is replaced by a deterministic fake here: these tests prove our side (mandate set-up,
authorisation verification, webhook application, idempotency, notifications, isolation). They are
not evidence that Razorpay charged anything; that needs the test-mode end-to-end run.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.app.core.config import settings
from backend.app.core.exceptions import GatewayError
from backend.app.models import (
    AutopayStatus,
    GatewaySubscription,
    Invoice,
    InvoiceStatus,
    MemberRole,
    NotificationDelivery,
    Payment,
    Subscription,
)
from backend.app.services import razorpay_gateway
from backend.tests.conftest import Tenant

API = "/api/v1"
WEBHOOK = f"{API}/webhooks/razorpay"
SECRET = "autopay_test_webhook_secret"
KEY_ID, KEY_SECRET = "rzp_test_autopay", "autopay_key_secret"


class FakeRazorpay:
    """Records calls; behaves like the Razorpay Subscriptions API for what we use."""

    def __init__(self):
        self.plans, self.subscriptions, self.cancelled = [], {}, []
        self.fail_cancel = False

    def create_plan(self, *, period, interval, name, amount_paise, currency, notes=None, creds=None):
        plan = {"id": f"plan_{uuid.uuid4().hex[:14]}", "period": period, "interval": interval,
                "item": {"name": name, "amount": amount_paise, "currency": currency}, "notes": notes}
        self.plans.append(plan)
        return plan

    def create_subscription(self, *, plan_id, total_count, start_at=None, expire_by=None, customer_notify=True, notes=None, creds=None):
        sub = {"id": f"sub_{uuid.uuid4().hex[:14]}", "plan_id": plan_id, "status": "created", "total_count": total_count,
               "start_at": start_at, "expire_by": expire_by, "notes": notes, "paid_count": 0,
               "short_url": "https://rzp.io/i/test"}
        self.subscriptions[sub["id"]] = sub
        return sub

    def fetch_subscription(self, sid, *, creds=None):
        return dict(self.subscriptions[sid])

    def cancel_subscription(self, sid, *, creds=None):
        if self.fail_cancel:
            raise GatewayError("Razorpay could not cancel the subscription: timeout")
        self.cancelled.append(sid)
        self.subscriptions[sid]["status"] = "cancelled"
        return dict(self.subscriptions[sid])


@pytest.fixture()
def rzp(monkeypatch):
    fake = FakeRazorpay()
    creds = razorpay_gateway.RazorpayCredentials(KEY_ID, KEY_SECRET, SECRET)
    monkeypatch.setattr(razorpay_gateway, "credentials_for", lambda db, org_id: creds)
    for name in ("create_plan", "create_subscription", "fetch_subscription", "cancel_subscription"):
        monkeypatch.setattr(razorpay_gateway, name, getattr(fake, name))
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    return fake


def _subscription(client, tenant: Tenant, auth_headers, *, autopay=True, amount="1000.00", interval="monthly"):
    customer = tenant.customer(phone="+919999999999")
    _, plan = tenant.product_with_plan(unit_amount=amount, interval=interval)
    if autopay:
        r = client.patch(f"{API}/plans/{plan.id}", headers=auth_headers, json={"autopay_enabled": True})
        assert r.status_code == 200, r.text
    r = client.post(f"{API}/subscriptions", headers=auth_headers,
                    json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1, "auto_renewal": True})
    assert r.status_code == 201, r.text
    return r.json(), customer, plan


def _setup(client, auth_headers, sub_id):
    r = client.post(f"{API}/subscriptions/{sub_id}/autopay", headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _token(link: str) -> str:
    return link.rstrip("/").rsplit("/", 1)[-1]


def _event(event: str, sub_entity: dict, *, payment: dict | None = None, created_at: int | None = None,
           event_id: str | None = None):
    body = {"entity": "event", "event": event, "created_at": created_at or int(time.time()),
            "payload": {"subscription": {"entity": sub_entity}}}
    if payment is not None:
        body["payload"]["payment"] = {"entity": payment}
    raw = json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "X-Razorpay-Event-Id": event_id or f"evt_{uuid.uuid4().hex}",
               "X-Razorpay-Signature": hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()}
    return raw, headers


def _mandate(db, gateway_subscription_id) -> GatewaySubscription:
    db.expire_all()
    from backend.app.core.tenant_context import system_context
    with system_context():
        return db.query(GatewaySubscription).filter_by(gateway_subscription_id=gateway_subscription_id).one()


def _mails(db, recipient: str, subject_part: str) -> int:
    db.expire_all()
    from backend.app.core.tenant_context import system_context
    with system_context():
        return sum(1 for d in db.query(NotificationDelivery).filter_by(recipient=recipient) if subject_part in (d.subject or ""))


# --- per-plan setting -------------------------------------------------------------------------------------------------


def test_plan_autopay_setting_is_validated_and_off_by_default(client, tenant, auth_headers):
    _, plan = tenant.product_with_plan(unit_amount="500.00")
    r = client.get(f"{API}/plans/{plan.id}", headers=auth_headers)
    assert r.status_code == 200 and r.json()["autopay_enabled"] is False
    _, one_time = tenant.product_with_plan(unit_amount="500.00", interval="one_time")
    r = client.patch(f"{API}/plans/{one_time.id}", headers=auth_headers, json={"autopay_enabled": True})
    assert r.status_code == 422, r.text
    r = client.patch(f"{API}/plans/{plan.id}", headers=tenant.headers_for_role(MemberRole.VIEWER), json={"autopay_enabled": True})
    assert r.status_code == 403


def test_subscription_on_a_plan_without_autopay_cannot_set_it_up(client, tenant, auth_headers, rzp):
    sub, _, _ = _subscription(client, tenant, auth_headers, autopay=False)
    status = client.get(f"{API}/subscriptions/{sub['id']}/autopay", headers=auth_headers).json()
    assert status["eligible"] is False and "not enabled" in status["reason"]
    r = client.post(f"{API}/subscriptions/{sub['id']}/autopay", headers=auth_headers)
    assert r.status_code in (400, 409, 422), r.text
    assert rzp.plans == [] and rzp.subscriptions == {}


# --- set-up -------------------------------------------------------------------------------------------------------------


def test_setup_creates_one_razorpay_subscription_for_the_period_total(client, tenant, auth_headers, rzp, db):
    sub, _, _ = _subscription(client, tenant, auth_headers, amount="1000.00")
    out = _setup(client, auth_headers, sub["id"])
    assert out["status"] == "created" and out["authorization_link"]
    (plan,) = rzp.plans
    assert plan["period"] == "monthly" and plan["interval"] == 1
    assert plan["item"]["amount"] == int(Decimal(sub["total_amount"]) * 100)  # tax included
    gw = rzp.subscriptions[out["gateway_subscription_id"]]
    assert gw["notes"]["organization_id"] == tenant.organization.id
    assert gw["start_at"] > time.time() and gw["total_count"] == 120
    # the first automatic charge is on the next billing date, not today
    nbd = date.fromisoformat(sub["next_billing_date"])
    assert datetime.fromtimestamp(gw["start_at"], tz=timezone.utc).date() in (nbd, nbd - timedelta(days=1))

    again = _setup(client, auth_headers, sub["id"])  # retry / double click
    assert again["gateway_subscription_id"] == out["gateway_subscription_id"] and len(rzp.subscriptions) == 1
    assert client.get(f"{API}/public/autopay/{_token(out['authorization_link'])}").status_code == 404  # link rotated
    assert client.get(f"{API}/public/autopay/{_token(again['authorization_link'])}").status_code == 200


def test_only_finance_roles_set_up_autopay_and_other_tenants_cannot_see_it(client, tenant, auth_headers, rzp, db):
    sub, _, _ = _subscription(client, tenant, auth_headers)
    r = client.post(f"{API}/subscriptions/{sub['id']}/autopay", headers=tenant.headers_for_role(MemberRole.VIEWER))
    assert r.status_code == 403
    other = Tenant(db, "autopay-other")
    assert client.post(f"{API}/subscriptions/{sub['id']}/autopay", headers=other.headers()).status_code == 404
    assert client.get(f"{API}/subscriptions/{sub['id']}/autopay", headers=other.headers()).status_code == 404


# --- the customer's authorisation ---------------------------------------------------------------------------------------


def _checkout_signature(payment_id: str, gateway_subscription_id: str) -> str:
    return hmac.new(KEY_SECRET.encode(), f"{payment_id}|{gateway_subscription_id}".encode(), hashlib.sha256).hexdigest()


def test_public_page_exposes_only_what_checkout_needs(client, tenant, auth_headers, rzp):
    sub, customer, _ = _subscription(client, tenant, auth_headers)
    out = _setup(client, auth_headers, sub["id"])
    page = client.get(f"{API}/public/autopay/{_token(out['authorization_link'])}")
    assert page.status_code == 200
    body = page.json()
    assert body["can_authorize"] is True and body["key_id"] == KEY_ID
    assert body["gateway_subscription_id"] == out["gateway_subscription_id"]
    assert body["prefill"]["email"] == customer.email
    assert KEY_SECRET not in page.text and SECRET not in page.text


def test_browser_success_alone_never_authorises_the_mandate(client, tenant, auth_headers, rzp, db):
    sub, customer, _ = _subscription(client, tenant, auth_headers)
    out = _setup(client, auth_headers, sub["id"])
    token, gid = _token(out["authorization_link"]), out["gateway_subscription_id"]
    confirm = f"{API}/public/autopay/{token}/confirm"
    # forged signature
    r = client.post(confirm, json={"razorpay_payment_id": "pay_x", "razorpay_subscription_id": gid, "razorpay_signature": "00"})
    assert r.status_code == 422
    # someone else's subscription id
    r = client.post(confirm, json={"razorpay_payment_id": "pay_x", "razorpay_subscription_id": "sub_other",
                                   "razorpay_signature": _checkout_signature("pay_x", "sub_other")})
    assert r.status_code == 422
    # valid signature, but Razorpay has not authenticated it (yet): stays created
    r = client.post(confirm, json={"razorpay_payment_id": "pay_1", "razorpay_subscription_id": gid,
                                   "razorpay_signature": _checkout_signature("pay_1", gid)})
    assert r.status_code == 200 and r.json()["status"] == "created"
    assert _mandate(db, gid).authorized_at is None
    # Razorpay confirms: authorised, one notification
    rzp.subscriptions[gid]["status"] = "authenticated"
    for _ in range(2):
        r = client.post(confirm, json={"razorpay_payment_id": "pay_1", "razorpay_subscription_id": gid,
                                       "razorpay_signature": _checkout_signature("pay_1", gid)})
        assert r.status_code == 200 and r.json()["status"] == "authenticated"
    assert _mandate(db, gid).authorized_at is not None
    assert _mails(db, customer.email, "AutoPay set up") == 1


# --- webhooks -----------------------------------------------------------------------------------------------------------


def _authorised(client, tenant, auth_headers, rzp, **kw):
    sub, customer, plan = _subscription(client, tenant, auth_headers, **kw)
    out = _setup(client, auth_headers, sub["id"])
    gid = out["gateway_subscription_id"]
    raw, headers = _event("subscription.authenticated", {**rzp.subscriptions[gid], "status": "authenticated"})
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 200
    return sub, customer, gid


def _due_now(db, sub_id):
    """Make the subscription's next billing date today (as if the cycle came round)."""
    from backend.app.core.tenant_context import system_context
    with system_context():
        sub = db.get(Subscription, sub_id)
        sub.next_billing_date = date.today()
        sub.current_period_end = date.today()
        db.commit()


def _charge(gid, amount_paise, payment_id=None, method="upi"):
    return {"id": payment_id or f"pay_{uuid.uuid4().hex[:14]}", "entity": "payment", "amount": amount_paise,
            "currency": "INR", "status": "captured", "method": method, "order_id": f"order_{uuid.uuid4().hex[:14]}",
            "invoice_id": f"inv_{uuid.uuid4().hex[:14]}"}


def test_authenticated_webhook_and_its_redelivery(client, tenant, auth_headers, rzp, db):
    sub, customer, gid = _authorised(client, tenant, auth_headers, rzp)
    assert _mandate(db, gid).status == AutopayStatus.AUTHENTICATED
    raw, headers = _event("subscription.authenticated", {**rzp.subscriptions[gid], "status": "authenticated"},
                          event_id="evt_same")
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 200
    assert client.post(WEBHOOK, content=raw, headers=headers).json().get("status") in ("duplicate", "ok", None)
    assert _mails(db, customer.email, "AutoPay set up") == 1


def test_charge_pays_the_renewal_invoice_once(client, tenant, auth_headers, rzp, db):
    sub, customer, gid = _authorised(client, tenant, auth_headers, rzp)
    _due_now(db, sub["id"])  # the charge arrives before the renewal run: the invoice is issued on the spot
    amount = int(Decimal(sub["total_amount"]) * 100)
    payment = _charge(gid, amount)
    entity = {**rzp.subscriptions[gid], "status": "active", "paid_count": 1}
    raw, headers = _event("subscription.charged", entity, payment=payment)
    r = client.post(WEBHOOK, content=raw, headers=headers)
    assert r.status_code == 200, r.text
    # Razorpay redelivers under a new event id, and payment.captured of the same charge arrives too
    raw2, headers2 = _event("subscription.charged", entity, payment=payment)
    assert client.post(WEBHOOK, content=raw2, headers=headers2).status_code == 200
    cap = json.dumps({"event": "payment.captured", "created_at": int(time.time()),
                      "payload": {"payment": {"entity": payment}}}).encode()
    r = client.post(WEBHOOK, content=cap, headers={"Content-Type": "application/json", "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex}",
                                                     "X-Razorpay-Signature": hmac.new(SECRET.encode(), cap, hashlib.sha256).hexdigest()})
    assert r.status_code == 200, r.text  # not a 503 retry loop

    db.expire_all()
    from backend.app.core.tenant_context import system_context
    with system_context():
        payments = db.query(Payment).filter_by(gateway_payment_id=payment["id"]).all()
        assert len(payments) == 1 and payments[0].amount == Decimal(sub["total_amount"])
        invoice = db.query(Invoice).filter_by(subscription_id=sub["id"]).order_by(Invoice.created_at.desc()).first()
        assert invoice.status == InvoiceStatus.PAID and invoice.amount_due == Decimal("0.00")
    row = _mandate(db, gid)
    assert row.status == AutopayStatus.ACTIVE and row.paid_count == 1
    assert _mails(db, customer.email, "Payment received") == 1


def test_older_events_never_roll_the_state_back(client, tenant, auth_headers, rzp, db):
    sub, _, gid = _authorised(client, tenant, auth_headers, rzp)
    now = int(time.time())
    raw, headers = _event("subscription.halted", {**rzp.subscriptions[gid], "status": "halted"}, created_at=now + 100)
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 200
    raw, headers = _event("subscription.activated", {**rzp.subscriptions[gid], "status": "active"}, created_at=now + 50)
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 200
    assert _mandate(db, gid).status == AutopayStatus.HALTED


def test_failed_charges_notify_once_per_cycle_then_halt(client, tenant, auth_headers, rzp, db):
    sub, customer, gid = _authorised(client, tenant, auth_headers, rzp)
    entity = {**rzp.subscriptions[gid], "status": "pending", "charge_at": int(time.time()) + 86400}
    failed = {**_charge(gid, 100000), "status": "failed", "error_description": "Insufficient balance"}
    for day in range(3):  # Razorpay's T+1..T+3 retries: each fails and fires subscription.pending again
        raw, headers = _event("subscription.pending", entity, payment=failed, created_at=int(time.time()) + day)
        assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 200
    assert _mails(db, customer.email, "AutoPay payment failed") == 1
    row = _mandate(db, gid)
    assert row.status == AutopayStatus.PENDING and "Insufficient balance" in (row.last_error or "")
    raw, headers = _event("subscription.halted", {**entity, "status": "halted"}, created_at=int(time.time()) + 10)
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 200
    assert _mandate(db, gid).status == AutopayStatus.HALTED
    assert _mails(db, customer.email, "Action needed") == 1
    # nothing was charged by us in the meantime
    from backend.app.core.tenant_context import system_context
    with system_context():
        assert db.query(Payment).filter(Payment.customer_id == customer.id).count() == 0


def test_invalid_signature_is_rejected_and_changes_nothing(client, tenant, auth_headers, rzp, db):
    sub, _, gid = _authorised(client, tenant, auth_headers, rzp)
    raw, headers = _event("subscription.cancelled", {**rzp.subscriptions[gid], "status": "cancelled"})
    headers["X-Razorpay-Signature"] = "0" * 64
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 400
    assert _mandate(db, gid).status == AutopayStatus.AUTHENTICATED


def test_an_event_naming_another_organization_is_not_applied(client, tenant, auth_headers, rzp, db):
    sub, _, gid = _authorised(client, tenant, auth_headers, rzp)
    entity = {**rzp.subscriptions[gid], "status": "cancelled", "notes": {"organization_id": str(uuid.uuid4())}}
    raw, headers = _event("subscription.cancelled", entity)
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 200  # stored as failed, not retried
    assert _mandate(db, gid).status == AutopayStatus.AUTHENTICATED


def test_unknown_mandate_is_retried_not_dropped(client, rzp):
    raw, headers = _event("subscription.charged", {"id": "sub_unknown00000001", "status": "active"},
                          payment=_charge("sub_unknown00000001", 100))
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 503


# --- stopping ------------------------------------------------------------------------------------------------------------


def test_cancelling_the_subscription_cancels_the_mandate_first(client, tenant, auth_headers, rzp, db):
    sub, _, gid = _authorised(client, tenant, auth_headers, rzp)
    rzp.fail_cancel = True  # Razorpay unreachable: the local cancel must not go ahead
    r = client.post(f"{API}/subscriptions/{sub['id']}/cancel", headers=auth_headers, json={"at_period_end": False})
    assert r.status_code >= 500 or r.status_code == 502, r.text
    assert _mandate(db, gid).status == AutopayStatus.AUTHENTICATED
    rzp.fail_cancel = False
    r = client.post(f"{API}/subscriptions/{sub['id']}/cancel", headers=auth_headers, json={"at_period_end": True})
    assert r.status_code == 200, r.text
    assert rzp.cancelled == [gid] and _mandate(db, gid).status == AutopayStatus.CANCELLED


def test_staff_can_stop_autopay_and_set_it_up_again(client, tenant, auth_headers, rzp, db):
    sub, _, gid = _authorised(client, tenant, auth_headers, rzp)
    r = client.post(f"{API}/subscriptions/{sub['id']}/autopay/cancel", headers=auth_headers)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    again = _setup(client, auth_headers, sub["id"])
    assert again["gateway_subscription_id"] != gid
    status = client.get(f"{API}/subscriptions/{sub['id']}/autopay", headers=auth_headers).json()
    assert status["mandate"]["gateway_subscription_id"] == again["gateway_subscription_id"]


def test_an_unauthorised_request_never_blocks_cancelling_the_subscription(client, tenant, auth_headers, rzp, db):
    sub, _, _ = _subscription(client, tenant, auth_headers)
    gid = _setup(client, auth_headers, sub["id"])["gateway_subscription_id"]
    rzp.fail_cancel = True  # Razorpay refuses to cancel a never-authorised subscription
    r = client.post(f"{API}/subscriptions/{sub['id']}/cancel", headers=auth_headers, json={"at_period_end": False})
    assert r.status_code == 200, r.text
    assert _mandate(db, gid).status == AutopayStatus.CANCELLED

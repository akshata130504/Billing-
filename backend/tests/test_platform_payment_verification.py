"""Stage 4: verified Razorpay payments -> the organization's paid Rooman plan.

Razorpay is never called: checkout creation and the fetches are replaced by fakes, and the SDK client
fails the test if anything reaches it. Plans are published only inside these tests.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from backend.app.core.config import settings
from backend.app.core.tenant_context import system_context, tenant_context
from backend.app.models import (
    MemberRole,
    Organization,
    OrganizationStatus,
    PlatformCheckoutAttempt,
    PlatformPayment,
    PlatformNotification,
    PlatformPaymentReview,
    PlatformProviderPlan,
    PlatformSubscription,
    PlatformWebhookEvent,
)
from backend.app.models.platform import PlatformAuditLog
from backend.app.models.subscription_access import OrganizationEntitlement
from backend.app.services import (
    platform_audit,
    platform_checkout_service as checkout,
    platform_payment_service as payments,
    platform_razorpay as provider,
    platform_subscription_service as subs,
    razorpay_gateway,
)
from backend.tests.test_platform_checkout import KEY_ID, SECRET, FakeProvider, _catalog

API = "/api/v1"
WEBHOOK = f"{API}/webhooks/razorpay-platform"
VERIFY = f"{API}/subscription-checkout/verify"
WEBHOOK_SECRET = "dummy-platform-webhook-secret-123"
UTC = timezone.utc
STARTER_EXTRA = {"quotes", "reports", "integrations"}
GROWTH_EXTRA = STARTER_EXTRA | {"customer_portal", "collections", "reconciliation", "expenses", "projects", "timesheets"}
BUSINESS_ONLY = {"subscriptions", "dunning", "customer_lifecycle", "automation"}


class Razorpay(FakeProvider):
    """Checkout creation (from Stage 3's fake) plus the current subscription / payment state."""

    def __init__(self):
        super().__init__()
        self.subs, self.payments, self.fetches, self.unavailable = {}, {}, [], False
        self.paid_invoices = {}  # subscription id -> list of paid invoices (receipts for later cycles)

    def fetch_subscription(self, sid):
        self.fetches.append(sid)
        if self.unavailable:
            raise provider.ProviderUnavailable("timeout")
        if sid not in self.subs:
            raise provider.ProviderRejected("not found")
        return dict(self.subs[sid])

    def list_paid_subscription_invoices(self, sid):
        self.fetches.append(f"invoices:{sid}")
        if self.unavailable:
            raise provider.ProviderUnavailable("timeout")
        return list(self.paid_invoices.get(sid, []))

    def fetch_payment(self, pid):
        self.fetches.append(pid)
        if self.unavailable:
            raise provider.ProviderUnavailable("timeout")
        if pid not in self.payments:
            raise provider.ProviderRejected("not found")
        return dict(self.payments[pid])


@pytest.fixture(autouse=True)
def isolated(db, monkeypatch):
    with system_context():
        for model in (PlatformNotification, PlatformPaymentReview, PlatformPayment, PlatformWebhookEvent, PlatformCheckoutAttempt, PlatformProviderPlan):
            db.query(model).delete()
        db.commit()
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", SECRET)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", False)

    def no_network(*a, **k):
        raise AssertionError("a test reached the real Razorpay client")

    monkeypatch.setattr(razorpay_gateway, "_get_client", no_network)
    cat = _catalog(starter="published", growth="published", business="published")
    for module in (subs, checkout, payments):
        monkeypatch.setattr(module, "catalog", lambda: cat)


@pytest.fixture
def rzp(monkeypatch):
    fake = Razorpay()
    for name in ("create_plan", "create_subscription", "find_plan", "find_subscription", "fetch_subscription", "fetch_payment",
                 "list_paid_subscription_invoices"):
        monkeypatch.setattr(provider, name, getattr(fake, name))
    return fake


def _code(resp):
    body = resp.json()["error"]
    return body.get("code")


def _expired_trial(db, tenant):
    now = datetime.now(UTC)
    db.add(PlatformSubscription(organization_id=tenant.organization.id, state="trialing", reminders_sent=[],
                                trial_started_at=now - timedelta(minutes=30), trial_ends_at=now - timedelta(minutes=15)))
    db.commit()


def _start(client, tenant, plan="starter"):
    r = client.post(f"{API}/subscription-checkout", json={"plan_code": plan}, headers=tenant.headers())
    assert r.status_code == 201, r.text
    return r.json()


def _attempt(db, attempt_id):
    with system_context():
        db.expire_all()
        return db.get(PlatformCheckoutAttempt, attempt_id)


def _pay(rzp, db, checkout_body, *, status="active", paid_count=1, payment_status="captured", amount=None,
         currency="INR", plan_id=None, notes=None, started=None):
    """Make Razorpay report this checkout's subscription (and a payment) in the given state."""
    attempt = _attempt(db, checkout_body["checkout_attempt_id"])
    sid = attempt.provider_subscription_id
    pid = f"pay_{uuid.uuid4().hex[:14]}"
    rzp.subs[sid] = {
        "id": sid, "status": status, "plan_id": plan_id or attempt.provider_plan_id, "quantity": 1,
        "paid_count": paid_count, "current_start": int((started or datetime.now(UTC) - timedelta(hours=1)).timestamp()),
        "notes": notes if notes is not None else {"checkout_attempt_id": attempt.id, "organization_id": attempt.organization_id},
    }
    rzp.payments[pid] = {"id": pid, "status": payment_status, "amount": attempt.amount_minor if amount is None else amount,
                         "currency": currency}
    return sid, pid


def _signature(pid, sid, secret=SECRET):
    return hmac.new(secret.encode(), f"{pid}|{sid}".encode(), hashlib.sha256).hexdigest()


def _verify(client, tenant, pid, sid, signature=None, headers=None):
    return client.post(VERIFY, headers=headers or tenant.headers(), json={
        "razorpay_payment_id": pid, "razorpay_subscription_id": sid,
        "razorpay_signature": signature or _signature(pid, sid)})


def _webhook(client, event, sid, pid=None, event_id=None, secret=WEBHOOK_SECRET, raw=None):
    body = {"entity": "event", "event": event, "contains": ["subscription"] + (["payment"] if pid else []),
            "created_at": int(datetime.now(UTC).timestamp()),
            "payload": {"subscription": {"entity": {"id": sid}}, **({"payment": {"entity": {"id": pid}}} if pid else {})}}
    data = raw if raw is not None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "X-Razorpay-Event-Id": event_id or f"evt_{uuid.uuid4().hex}",
               "X-Razorpay-Signature": hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()}
    return client.post(WEBHOOK, content=data, headers=headers)


def _modules(db, org_id):
    with tenant_context(org_id):
        return {r.module_key for r in db.scalars(select(OrganizationEntitlement).where(
            OrganizationEntitlement.organization_id == org_id)).all()}


def _org(db, org_id):
    with system_context():
        db.expire_all()
        return db.get(Organization, org_id)


def _write(client, tenant, headers=None):
    return client.post(f"{API}/customers", headers=headers or tenant.headers(),
                       json={"display_name": f"Acme {uuid.uuid4().hex[:6]}", "email": f"c{uuid.uuid4().hex[:6]}@x.test"})


def _ledger(db):
    with system_context():
        db.expire_all()
        return db.scalars(select(PlatformWebhookEvent).order_by(PlatformWebhookEvent.received_at)).all()


# --- the business rule: read-only until the paid plan is verified, then exactly that plan ----------


def test_verified_starter_purchase_unlocks_exactly_starter(client, db, tenant, rzp):
    _expired_trial(db, tenant)
    body = _start(client, tenant, "starter")
    assert _code(_write(client, tenant)) == "TRIAL_EXPIRED"  # checkout alone unlocks nothing
    assert _org(db, tenant.organization.id).module_access == "unrestricted"
    sid, pid = _pay(rzp, db, body)

    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active" and r.json()["plan_code"] == "starter"
    org = _org(db, tenant.organization.id)
    assert org.module_access == "entitled" and org.seat_limit == 3
    assert _modules(db, org.id) == STARTER_EXTRA  # nothing from Growth or Business
    assert _write(client, tenant).status_code == 201  # read-only lifted only now
    r = client.get(f"{API}/projects", headers=tenant.headers())
    assert r.status_code == 403 and _code(r) == "FEATURE_NOT_ENTITLED"
    sub = subs.get_subscription(db, org.id)
    assert sub.state == "active" and sub.plan_code == "starter" and sub.provider_subscription_id == sid
    assert sub.provider_paid_count == 1 and sub.provider_mode == "test"
    attempt = _attempt(db, body["checkout_attempt_id"])
    assert attempt.status == "completed" and attempt.provider_payment_id == pid
    me = client.get(f"{API}/auth/me", headers=tenant.headers()).json()
    assert me["subscription"]["state"] == "active" and me["trial"] is None


def test_growth_purchase_gets_growth_but_no_business_modules(client, db, tenant, rzp):
    body = _start(client, tenant, "growth")
    sid, pid = _pay(rzp, db, body)
    assert _verify(client, tenant, pid, sid).json()["status"] == "active"
    mods = _modules(db, tenant.organization.id)
    assert mods == GROWTH_EXTRA and not mods & BUSINESS_ONLY
    assert _org(db, tenant.organization.id).seat_limit == 5


def test_purchased_seat_limit_is_enforced(client, db, tenant, rzp):
    body = _start(client, tenant, "starter")
    sid, pid = _pay(rzp, db, body)
    _verify(client, tenant, pid, sid)
    from unittest.mock import patch

    with patch("backend.app.services.organization_service.send_email", return_value=True):
        for _ in range(2):
            assert client.post(f"{API}/team/invitations", headers=tenant.headers(),
                               json={"email": f"x{uuid.uuid4().hex[:6]}@t.test", "role": "viewer"}).status_code == 201
        r = client.post(f"{API}/team/invitations", headers=tenant.headers(),
                        json={"email": f"x{uuid.uuid4().hex[:6]}@t.test", "role": "viewer"})
    assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "SEAT_LIMIT_REACHED"


# --- callback verification ------------------------------------------------------------------------


def test_invalid_signature_changes_nothing(client, db, tenant, rzp):
    _expired_trial(db, tenant)
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    r = _verify(client, tenant, pid, sid, signature=_signature(pid, sid, secret="wrong-secret"))
    assert r.status_code == 400 and _code(r) == "PAYMENT_SIGNATURE_INVALID"
    r = _verify(client, tenant, pid, sid, signature=_signature(f"pay_{uuid.uuid4().hex[:14]}", sid))  # other payment
    assert r.status_code == 400
    assert rzp.fetches == [] and _attempt(db, body["checkout_attempt_id"]).status == "created"
    assert _org(db, tenant.organization.id).module_access == "unrestricted"
    assert _code(_write(client, tenant)) == "TRIAL_EXPIRED"


def test_subscription_ids_not_stored_for_this_organization_are_refused(client, db, tenant, rzp):
    from backend.tests.conftest import Tenant

    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    fake_sid = f"sub_{uuid.uuid4().hex[:14]}"
    r = _verify(client, tenant, pid, fake_sid)  # signed correctly for a subscription we never stored
    assert r.status_code == 404 and _code(r) == "CHECKOUT_NOT_FOUND"
    other = Tenant(db, uuid.uuid4().hex[:8])
    r = _verify(client, other, pid, sid)  # another organization presents this organization's subscription
    assert r.status_code == 404
    assert _org(db, other.organization.id).module_access == "unrestricted"
    assert _attempt(db, body["checkout_attempt_id"]).status == "created"


@pytest.mark.parametrize("change, detail", [
    ({"amount": 100}, "amount"), ({"currency": "USD"}, "currency"), ({"plan_id": "plan_SOMEOTHERPLAN1"}, "plan"),
    ({"notes": {"checkout_attempt_id": "x", "organization_id": "y"}}, "notes"),
])
def test_payment_that_does_not_match_the_checkout_is_not_applied(client, db, tenant, rzp, change, detail):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body, **change)
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 409 and _code(r) == "PAYMENT_NEEDS_REVIEW", detail
    assert _org(db, tenant.organization.id).module_access == "unrestricted"
    assert subs.get_subscription(db, tenant.organization.id) is None


def test_checkout_from_the_other_mode_is_not_applied(client, db, tenant, rzp, monkeypatch):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", "rzp_live_RoomanLiveDummy")
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 409 and _code(r) == "PAYMENT_NEEDS_REVIEW"
    assert subs.get_subscription(db, tenant.organization.id) is None


@pytest.mark.parametrize("state", [
    {"status": "authenticated", "paid_count": 0, "payment_status": "authorized"},  # mandate only
    {"status": "created", "paid_count": 0, "payment_status": "authorized"},  # first charge not done
    {"status": "active", "paid_count": 1, "payment_status": "authorized"},  # not captured yet
])
def test_authorization_without_a_captured_first_charge_is_pending(client, db, tenant, rzp, state):
    _expired_trial(db, tenant)
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body, **state)
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    attempt = _attempt(db, body["checkout_attempt_id"])
    assert attempt.status == "authorized" and attempt.authorized_at is not None
    assert _org(db, tenant.organization.id).module_access == "unrestricted"
    assert _code(_write(client, tenant)) == "TRIAL_EXPIRED"  # still read-only
    assert client.get(f"{API}/auth/me", headers=tenant.headers()).json()["subscription"] is None
    # A second checkout waits for this payment.
    r = client.post(f"{API}/subscription-checkout", json={"plan_code": "growth"}, headers=tenant.headers())
    assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "PAYMENT_IN_PROGRESS"

    # Razorpay confirms the charge later (webhook): now the plan starts.
    rzp.subs[sid].update(status="active", paid_count=1)
    rzp.payments[pid]["status"] = "captured"
    assert _webhook(client, "subscription.charged", sid, pid).json()["status"] == "processed"
    assert _write(client, tenant).status_code == 201
    assert _modules(db, tenant.organization.id) == STARTER_EXTRA


def test_failed_first_payment_is_not_paid(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body, status="created", paid_count=0, payment_status="failed")
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 200 and r.json()["status"] == "not_paid"
    assert subs.get_subscription(db, tenant.organization.id) is None


def test_razorpay_unavailable_changes_nothing_and_retry_works(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    rzp.unavailable = True
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 503 and _code(r) == "PAYMENT_CONFIRMATION_DELAYED"
    assert _attempt(db, body["checkout_attempt_id"]).status == "created"
    assert subs.get_subscription(db, tenant.organization.id) is None
    rzp.unavailable = False
    assert _verify(client, tenant, pid, sid).json()["status"] == "active"


def test_duplicate_callbacks_activate_once(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    assert _verify(client, tenant, pid, sid).json()["status"] == "active"
    fetches = len(rzp.fetches)
    assert _verify(client, tenant, pid, sid).json()["status"] == "active"
    assert len(rzp.fetches) == fetches  # already completed: nothing re-applied
    with system_context():
        activations = db.scalar(select(func.count()).select_from(PlatformAuditLog).where(
            PlatformAuditLog.organization_id == tenant.organization.id,
            PlatformAuditLog.action == platform_audit.PLATFORM_SUBSCRIPTION_ACTIVATED))
    assert activations == 1 and _modules(db, tenant.organization.id) == STARTER_EXTRA


def test_expired_checkout_is_paid_only_if_razorpay_confirms(client, db, tenant, rzp):
    body = _start(client, tenant)
    with system_context():
        a = db.get(PlatformCheckoutAttempt, body["checkout_attempt_id"])
        a.status, a.expires_at = "expired", datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    sid, pid = _pay(rzp, db, body, status="expired", paid_count=0, payment_status="failed")
    assert _verify(client, tenant, pid, sid).json()["status"] == "not_paid"
    assert subs.get_subscription(db, tenant.organization.id) is None


def test_only_the_owner_verifies_and_only_callback_fields_are_accepted(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    assert _verify(client, tenant, pid, sid, headers=tenant.headers_for_role(MemberRole.ADMIN)).status_code == 403
    r = client.post(VERIFY, headers=tenant.headers(), json={
        "razorpay_payment_id": pid, "razorpay_subscription_id": sid, "razorpay_signature": _signature(pid, sid),
        "status": "captured", "plan_code": "business"})
    assert r.status_code == 422
    assert subs.get_subscription(db, tenant.organization.id) is None


def test_plan_changed_or_unpublished_after_checkout_is_not_applied(client, db, tenant, rzp, monkeypatch):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    changed = _catalog(starter={"amount_minor": 99900}, growth="published")
    for module in (subs, checkout, payments):
        monkeypatch.setattr(module, "catalog", lambda: changed)
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 409 and _code(r) == "PAYMENT_NEEDS_REVIEW"
    assert subs.get_subscription(db, tenant.organization.id) is None


def test_suspended_organization_payment_is_held_for_review(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    with system_context():
        db.get(Organization, tenant.organization.id).status = OrganizationStatus.SUSPENDED
        db.commit()
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 403  # the suspended organization cannot use the API at all
    assert payments.sync_provider_subscription(db, sid, payment_id=pid).outcome == "needs_review"
    db.rollback()
    assert subs.get_subscription(db, tenant.organization.id) is None


# --- webhook authentication and the ledger ------------------------------------------------------------


def test_webhook_without_a_configured_secret_processes_nothing(client, db, tenant, rzp, monkeypatch):
    body = _start(client, tenant)  # checkout itself refuses to start without the webhook secret
    sid, pid = _pay(rzp, db, body)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_WEBHOOK_SECRET", "")
    r = _webhook(client, "subscription.activated", sid, pid, secret="anything")
    assert r.status_code == 503 and _code(r) == "WEBHOOK_NOT_CONFIGURED"
    assert _ledger(db) == [] and rzp.fetches == []


def test_webhook_signature_is_checked_over_the_raw_bytes(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    raw = (' { "event" :  "subscription.activated", "payload": {"subscription": {"entity": {"id": "%s"}},'
           ' "payment": {"entity": {"id": "%s"}}} } ' % (sid, pid)).encode()
    assert _webhook(client, "x", sid, raw=raw).json()["status"] == "processed"  # unusual spacing, still valid
    assert subs.get_subscription(db, tenant.organization.id).state == "active"


def test_invalid_webhook_signatures_are_rejected_before_anything(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    for secret in ("wrong-secret", SECRET):  # never the API secret
        r = _webhook(client, "subscription.activated", sid, pid, secret=secret)
        assert r.status_code == 400
    assert _ledger(db) == [] and rzp.fetches == [] and subs.get_subscription(db, tenant.organization.id) is None


def test_webhook_activates_when_the_browser_never_returned(client, db, tenant, rzp):
    _expired_trial(db, tenant)
    body = _start(client, tenant, "growth")
    sid, pid = _pay(rzp, db, body)
    r = _webhook(client, "subscription.activated", sid, pid, event_id="evt_ACTIVATED_1")
    assert r.status_code == 200 and r.json()["status"] == "processed"
    assert _modules(db, tenant.organization.id) == GROWTH_EXTRA
    [row] = _ledger(db)
    assert (row.event_id, row.event_type, row.status, row.outcome) == ("evt_ACTIVATED_1", "subscription.activated", "processed", "activated")
    assert row.organization_id == tenant.organization.id and row.provider_subscription_id == sid and row.mode == "test"

    # The same event again: acknowledged, nothing repeated.
    r = _webhook(client, "subscription.activated", sid, pid, event_id="evt_ACTIVATED_1")
    assert r.json()["status"] == "duplicate" and len(_ledger(db)) == 1
    # The browser callback arriving afterwards: still one activation.
    assert _verify(client, tenant, pid, sid).json()["status"] == "active"
    with system_context():
        assert db.scalar(select(func.count()).select_from(PlatformAuditLog).where(
            PlatformAuditLog.organization_id == tenant.organization.id,
            PlatformAuditLog.action == platform_audit.PLATFORM_SUBSCRIPTION_ACTIVATED)) == 1


def test_webhook_event_without_a_payment_waits_for_payment_evidence(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    assert _webhook(client, "subscription.authenticated", sid).json()["status"] == "processed"
    assert _attempt(db, body["checkout_attempt_id"]).status == "authorized"
    assert subs.get_subscription(db, tenant.organization.id) is None
    assert _webhook(client, "subscription.charged", sid, pid).json()["status"] == "processed"
    assert subs.get_subscription(db, tenant.organization.id).state == "active"


def test_webhook_retryable_failure_is_not_recorded(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    rzp.unavailable = True
    r = _webhook(client, "subscription.activated", sid, pid, event_id="evt_RETRY_1")
    assert r.status_code == 503 and _ledger(db) == []
    rzp.unavailable = False
    r = _webhook(client, "subscription.activated", sid, pid, event_id="evt_RETRY_1")  # Razorpay redelivers
    assert r.json()["status"] == "processed" and subs.get_subscription(db, tenant.organization.id).state == "active"


def test_unknown_or_unsupported_events_are_ignored(client, db, tenant, rzp):
    r = _webhook(client, "subscription.activated", f"sub_{uuid.uuid4().hex[:14]}")
    assert r.json()["status"] == "ignored"
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    for event in ("subscription.updated", "subscription.paused", "payment.captured"):
        assert _webhook(client, event, sid, pid).json()["status"] == "ignored"
    assert {(r.status, r.outcome) for r in _ledger(db)} == {("ignored", "unknown_subscription"), ("ignored", "unsupported_event")}
    assert subs.get_subscription(db, tenant.organization.id) is None


def test_mismatched_event_is_recorded_for_review(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body, amount=1)
    assert _webhook(client, "subscription.charged", sid, pid).json()["status"] == "needs_review"
    assert _ledger(db)[0].outcome == "mismatch" and subs.get_subscription(db, tenant.organization.id) is None


# --- renewals, failures, cancellations, ordering ---------------------------------------------------


def _active(client, db, tenant, rzp, plan="starter"):
    body = _start(client, tenant, plan)
    sid, pid = _pay(rzp, db, body)
    assert _verify(client, tenant, pid, sid).json()["status"] == "active"
    return sid


def test_each_paid_cycle_renews_exactly_once(client, db, tenant, rzp):
    sid = _active(client, db, tenant, rzp)
    end_1 = subs._aware(subs.get_subscription(db, tenant.organization.id).current_period_end)
    rzp.subs[sid]["paid_count"] = 2
    pid2 = f"pay_{uuid.uuid4().hex[:14]}"
    rzp.payments[pid2] = {"id": pid2, "status": "captured", "amount": 79900, "currency": "INR"}
    assert _webhook(client, "subscription.charged", sid, pid2).json()["status"] == "processed"
    db.expire_all()
    sub = subs.get_subscription(db, tenant.organization.id)
    assert subs._aware(sub.current_period_start) == end_1 and sub.provider_paid_count == 2
    end_2 = subs._aware(sub.current_period_end)
    # A second delivery (new event id) of the same charge, and an old 'authenticated' event: no change.
    _webhook(client, "subscription.charged", sid, pid2)
    _webhook(client, "subscription.authenticated", sid)
    db.expire_all()
    sub = subs.get_subscription(db, tenant.organization.id)
    assert subs._aware(sub.current_period_end) == end_2 and sub.provider_paid_count == 2 and sub.state == "active"


def test_failed_renewal_uses_grace_then_recovers(client, db, tenant, rzp):
    sid = _active(client, db, tenant, rzp)
    rzp.subs[sid]["status"] = "pending"
    assert _webhook(client, "subscription.pending", sid).json()["status"] == "processed"
    db.expire_all()
    sub = subs.get_subscription(db, tenant.organization.id)
    assert sub.state == "past_due"
    assert subs._aware(sub.grace_period_end) == subs._aware(sub.current_period_end) + timedelta(
        days=settings.PLATFORM_SUBSCRIPTION_GRACE_DAYS)
    assert _write(client, tenant).status_code == 201  # inside the grace
    rzp.subs[sid].update(status="active", paid_count=2)
    assert _webhook(client, "subscription.charged", sid).json()["status"] == "processed"
    db.expire_all()
    sub = subs.get_subscription(db, tenant.organization.id)
    assert sub.state == "active" and sub.grace_period_end is None and sub.provider_paid_count == 2


def test_an_older_failure_event_does_not_undo_a_newer_payment(client, db, tenant, rzp):
    sid = _active(client, db, tenant, rzp)
    rzp.subs[sid].update(status="active", paid_count=2)  # Razorpay's current state: paid
    _webhook(client, "subscription.pending", sid)  # delivered late
    db.expire_all()
    sub = subs.get_subscription(db, tenant.organization.id)
    assert sub.state == "active" and sub.provider_paid_count == 2


def test_cancellation_keeps_access_only_for_the_paid_period(client, db, tenant, rzp):
    sid = _active(client, db, tenant, rzp)
    rzp.subs[sid]["status"] = "cancelled"
    assert _webhook(client, "subscription.cancelled", sid).json()["status"] == "processed"
    db.expire_all()
    sub = subs.get_subscription(db, tenant.organization.id)
    assert sub.state == "active" and sub.cancel_at_period_end
    assert _write(client, tenant).status_code == 201  # still the paid period
    with system_context():
        row = db.get(PlatformSubscription, sub.id)
        row.current_period_start = datetime.now(UTC) - timedelta(days=31)
        row.current_period_end = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert _code(_write(client, tenant)) == "SUBSCRIPTION_INACTIVE"
    # A late 'charged' event cannot reactivate a cancelled subscription without a new paid cycle.
    _webhook(client, "subscription.charged", sid)
    assert _code(_write(client, tenant)) == "SUBSCRIPTION_INACTIVE"


def test_cancellation_while_past_due_ends_access(client, db, tenant, rzp):
    sid = _active(client, db, tenant, rzp)
    rzp.subs[sid]["status"] = "pending"
    _webhook(client, "subscription.pending", sid)
    with system_context():
        row = subs.get_subscription(db, tenant.organization.id)
        row.current_period_start = datetime.now(UTC) - timedelta(days=31)
        row.current_period_end = datetime.now(UTC) - timedelta(days=1)
        row.grace_period_end = datetime.now(UTC) + timedelta(days=6)
        db.commit()
    rzp.subs[sid]["status"] = "cancelled"
    assert _webhook(client, "subscription.cancelled", sid).json()["status"] == "processed"
    assert subs.get_subscription(db, tenant.organization.id).state == "cancelled"
    assert _code(_write(client, tenant)) == "SUBSCRIPTION_INACTIVE"


def test_payment_after_access_ended_is_held_for_review(client, db, tenant, rzp):
    sid = _active(client, db, tenant, rzp)
    with system_context():
        row = subs.get_subscription(db, tenant.organization.id)
        row.current_period_start = datetime.now(UTC) - timedelta(days=60)
        row.current_period_end = datetime.now(UTC) - timedelta(days=20)  # past period + grace
        db.commit()
    rzp.subs[sid]["paid_count"] = 2
    assert _webhook(client, "subscription.charged", sid).json()["status"] == "needs_review"
    assert _code(_write(client, tenant)) == "SUBSCRIPTION_INACTIVE"


def test_events_of_an_older_subscription_do_not_drive_the_current_plan(client, db, tenant, rzp):
    sid = _active(client, db, tenant, rzp)
    with system_context():
        row = subs.get_subscription(db, tenant.organization.id)
        row.provider_subscription_id = "sub_NEWERSUBSCRIPT"  # the organization moved on to another subscription
        db.commit()
    rzp.subs[sid]["status"] = "cancelled"
    assert _webhook(client, "subscription.cancelled", sid).json()["status"] == "ignored"
    assert not subs.get_subscription(db, tenant.organization.id).cancel_at_period_end


def test_one_organizations_events_never_touch_another(client, db, tenant, rzp):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    _expired_trial(db, other)
    sid = _active(client, db, tenant, rzp, plan="business")
    rzp.subs[sid].update(status="active", paid_count=2)
    _webhook(client, "subscription.charged", sid)
    assert subs.get_subscription(db, other.organization.id).state == "trialing"
    assert _org(db, other.organization.id).module_access == "unrestricted"
    assert _modules(db, other.organization.id) == set()
    assert _code(_write(client, other)) == "TRIAL_EXPIRED"


def test_roles_still_apply_after_activation(client, db, tenant, rzp):
    _active(client, db, tenant, rzp)
    r = _write(client, tenant, tenant.headers_for_role(MemberRole.VIEWER))
    assert r.status_code == 403 and _code(r) not in ("TRIAL_EXPIRED", "SUBSCRIPTION_INACTIVE")


# --- configuration ---------------------------------------------------------------------------------


@pytest.mark.parametrize("clash", ["PLATFORM_RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET", "RAZORPAY_KEY_SECRET"])
def test_platform_webhook_secret_must_be_its_own_value(clash):
    from pydantic import ValidationError

    from backend.app.core.config import Settings

    values = {"PLATFORM_RAZORPAY_KEY_ID": KEY_ID, "PLATFORM_RAZORPAY_KEY_SECRET": SECRET,
              "PLATFORM_RAZORPAY_WEBHOOK_SECRET": "shared-value-123"}
    values[clash] = "shared-value-123"
    if clash == "RAZORPAY_KEY_SECRET":
        values["RAZORPAY_KEY_ID"] = "rzp_test_TenantKeyDummy1"
    with pytest.raises(ValidationError, match="PLATFORM_RAZORPAY_WEBHOOK_SECRET must be its own value") as exc:
        Settings(_env_file=None, **values)
    assert "shared-value-123" not in str(exc.value)


def test_platform_webhook_secret_is_optional_and_masked():
    from backend.app.core.config import Settings

    assert Settings(_env_file=None).PLATFORM_RAZORPAY_WEBHOOK_SECRET == ""
    s = Settings(_env_file=None, PLATFORM_RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET)
    assert WEBHOOK_SECRET not in repr(s) and "PLATFORM_RAZORPAY_WEBHOOK_SECRET='***'" in repr(s)

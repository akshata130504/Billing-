"""Owner self-service cancellation of the Rooman plan (POST /plan-subscription/cancel).

Razorpay is never called: every provider function is a fake, and the SDK client fails the test if anything
reaches it. The fake cancel follows Razorpay's documented rules: one cancel per subscription (a second is
refused), cycle-end keeps the subscription active, immediate makes it cancelled.
"""
import logging
from datetime import timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.tenant_context import system_context
from backend.app.models import (
    MemberRole,
    PlatformCheckoutAttempt,
    PlatformPayment,
    PlatformNotification,
    PlatformPaymentReview,
    PlatformProviderPlan,
    PlatformSubscription,
    PlatformWebhookEvent,
)
from backend.app.services import (
    platform_checkout_service as checkout,
    platform_payment_service as payments,
    platform_razorpay as provider,
    platform_reconciliation_service as recon,
    platform_subscription_service as subs,
    razorpay_gateway,
)
from backend.tests.test_platform_checkout import KEY_ID, SECRET, _catalog
from backend.tests.test_platform_payment_verification import (
    WEBHOOK_SECRET,
    _pay,
    _start,
    _verify,
    _webhook,
    _write,
)
from backend.tests.test_platform_reconciliation import RazorpayWithInvoices

API = "/api/v1"
URL = f"{API}/plan-subscription/cancel"
UTC = timezone.utc


class CancellableRazorpay(RazorpayWithInvoices):
    def __init__(self):
        super().__init__()
        self.cancels, self.cancelled_here, self.behaviour = [], set(), "ok"

    def cancel_subscription(self, sid, *, at_cycle_end):
        self.cancels.append((sid, at_cycle_end))
        if sid in self.cancelled_here:
            raise provider.ProviderRejected("subscription is already cancelled")
        if self.behaviour == "reject":
            raise provider.ProviderRejected("another operation is in progress")
        if self.behaviour == "timeout":
            raise provider.ProviderUnavailable("timeout")
        if self.behaviour == "ok_without_effect":
            return {**self.subs[sid], "status": "active"}
        self.cancelled_here.add(sid)  # "ok" and "timeout_after_apply": Razorpay did cancel
        if not at_cycle_end:
            self.subs[sid]["status"] = "cancelled"
        if self.behaviour == "timeout_after_apply":
            raise provider.ProviderUnavailable("timeout")
        return dict(self.subs[sid])


@pytest.fixture(autouse=True)
def isolated(db, monkeypatch):
    with system_context():
        for model in (PlatformNotification, PlatformPaymentReview, PlatformPayment, PlatformWebhookEvent, PlatformCheckoutAttempt, PlatformProviderPlan, PlatformSubscription):
            db.query(model).delete()
        db.commit()
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", SECRET)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", False)

    def no_network(*a, **k):
        raise AssertionError("a test reached the real Razorpay client")

    monkeypatch.setattr(razorpay_gateway, "_get_client", no_network)
    cat = _catalog(starter="published", growth="published")
    for module in (subs, checkout, payments):
        monkeypatch.setattr(module, "catalog", lambda: cat)


@pytest.fixture
def rzp(monkeypatch):
    fake = CancellableRazorpay()
    for name in ("create_plan", "create_subscription", "find_plan", "find_subscription", "fetch_subscription",
                 "fetch_payment", "find_subscription_payment", "cancel_subscription",
                 "list_paid_subscription_invoices"):
        monkeypatch.setattr(provider, name, getattr(fake, name))
    return fake


@pytest.fixture
def paid(client, db, tenant, rzp):
    """An organization on an active Starter plan, verified through the normal callback path."""
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 200 and r.json()["status"] == "active", r.text
    rzp.invoices[sid] = pid
    return sid


def _cancel(client, tenant, mode, headers=None):
    return client.post(URL, json={"mode": mode}, headers=headers or tenant.headers())


def _code(r):
    return r.json()["error"]["code"]


def _sub(db, org_id):
    with system_context():
        db.expire_all()
        return db.scalars(select(PlatformSubscription).where(PlatformSubscription.organization_id == org_id)).first()


def _end(sub):
    return sub.current_period_end.replace(tzinfo=UTC)


# --- the two modes ---------------------------------------------------------------------------------------


def test_owner_cancels_at_period_end_and_keeps_access_until_then(client, db, tenant, rzp, paid):
    r = _cancel(client, tenant, "at_period_end")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "scheduled" and body["already"] is False
    sub = _sub(db, tenant.organization.id)
    assert body["effective_at"].startswith(_end(sub).isoformat()[:19])
    assert rzp.cancels == [(paid, True)]
    assert sub.state == "active" and sub.cancel_at_period_end is True
    assert _write(client, tenant).status_code == 201  # paid access continues
    me = client.get(f"{API}/auth/me", headers=tenant.headers()).json()["subscription"]
    assert me["state"] == "active" and me["cancel_at_period_end"] is True and me["writable"] is True


def test_owner_cancels_immediately_and_the_organization_becomes_read_only(client, db, tenant, rzp, paid):
    r = _cancel(client, tenant, "immediately")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled" and r.json()["already"] is False
    assert rzp.cancels == [(paid, False)]
    sub = _sub(db, tenant.organization.id)
    assert sub.state == "cancelled" and sub.cancelled_at is not None
    w = _write(client, tenant)
    assert w.status_code == 403 and _code(w) == "SUBSCRIPTION_INACTIVE"
    assert client.get(f"{API}/customers", headers=tenant.headers()).status_code == 200  # data stays viewable


def test_access_ends_at_the_period_end_after_a_scheduled_cancellation(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "at_period_end").status_code == 200
    end = _end(_sub(db, tenant.organization.id))
    assert subs.evaluate(_sub(db, tenant.organization.id), end - timedelta(seconds=1)).writable is True
    assert subs.evaluate(_sub(db, tenant.organization.id), end).state == "cancelled"  # derived, before any job ran
    rzp.subs[paid]["status"] = "cancelled"  # Razorpay ends it at the cycle end
    counts = recon.reconcile(db, now=end + timedelta(minutes=1))
    assert counts.get("settle_settled_cancelled") == 1, counts
    assert _sub(db, tenant.organization.id).state == "cancelled"


# --- who may cancel -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", [MemberRole.ADMIN, MemberRole.FINANCE, MemberRole.VIEWER])
def test_only_the_owner_can_cancel(client, db, tenant, rzp, paid, role):
    r = _cancel(client, tenant, "immediately", headers=tenant.headers_for_role(role))
    assert r.status_code == 403
    assert rzp.cancels == [] and _sub(db, tenant.organization.id).state == "active"


def test_unauthenticated_and_malformed_requests_are_refused(client, tenant, rzp, paid):
    assert client.post(URL, json={"mode": "immediately"}).status_code == 401
    for body in ({"mode": "later"}, {}, {"mode": "immediately", "refund": True}):
        assert client.post(URL, json=body, headers=tenant.headers()).status_code == 422, body
    assert rzp.cancels == []


def test_nothing_to_cancel_without_a_paid_plan(client, db, tenant, rzp):
    r = _cancel(client, tenant, "immediately")
    assert r.status_code == 409 and _code(r) == "NO_PAID_SUBSCRIPTION"
    assert rzp.cancels == []


# --- repeated, contradictory and concurrent requests ------------------------------------------------------


def test_repeating_a_request_sends_nothing_new(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "at_period_end").json()["already"] is False
    again = _cancel(client, tenant, "at_period_end")
    assert again.status_code == 200 and again.json() == {**again.json(), "status": "scheduled", "already": True}
    assert rzp.cancels == [(paid, True)]


def test_cancel_now_after_a_scheduled_cancellation_is_refused(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "at_period_end").status_code == 200
    r = _cancel(client, tenant, "immediately")
    assert r.status_code == 409 and _code(r) == "CANCELLATION_ALREADY_SCHEDULED"
    assert rzp.cancels == [(paid, True)]  # Razorpay accepts only one cancellation: never a second, contradictory one
    assert _sub(db, tenant.organization.id).state == "active"


def test_an_immediately_cancelled_plan_stays_cancelled(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "immediately").status_code == 200
    # Read-only now, so a further cancel request is refused before it reaches the service.
    again = _cancel(client, tenant, "immediately")
    assert again.status_code == 403 and _code(again) == "SUBSCRIPTION_INACTIVE"
    assert rzp.cancels == [(paid, False)]


# --- provider failures ------------------------------------------------------------------------------------


def test_a_timeout_changes_nothing(client, db, tenant, rzp, paid):
    rzp.behaviour = "timeout"
    r = _cancel(client, tenant, "immediately")
    assert r.status_code == 503 and _code(r) == "CANCELLATION_UNCONFIRMED"
    sub = _sub(db, tenant.organization.id)
    assert sub.state == "active" and sub.cancel_at_period_end is False


def test_a_retry_after_a_timeout_that_did_cancel_is_confirmed_from_razorpay(client, db, tenant, rzp, paid):
    rzp.behaviour = "timeout_after_apply"
    assert _code(_cancel(client, tenant, "immediately")) == "CANCELLATION_UNCONFIRMED"
    assert _sub(db, tenant.organization.id).state == "active"  # not trusted until confirmed
    rzp.behaviour = "ok"
    r = _cancel(client, tenant, "immediately")  # Razorpay refuses a second cancel; a fresh read shows it cancelled
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert _sub(db, tenant.organization.id).state == "cancelled"
    assert len(rzp.cancels) == 2


def test_a_scheduled_cancellation_lost_to_a_timeout_is_not_claimed_but_resolves_at_period_end(client, db, tenant, rzp, paid):
    rzp.behaviour = "timeout_after_apply"  # Razorpay scheduled it, but we never saw the answer
    assert _code(_cancel(client, tenant, "at_period_end")) == "CANCELLATION_UNCONFIRMED"
    rzp.behaviour = "ok"
    r = _cancel(client, tenant, "at_period_end")  # refused (already cancelled there) and still active: cannot confirm
    assert r.status_code == 409 and _code(r) == "CANCELLATION_REFUSED"
    sub = _sub(db, tenant.organization.id)
    assert sub.state == "active" and sub.cancel_at_period_end is False
    # At the cycle end Razorpay cancels and charges nothing: reconciliation ends access as for an unpaid renewal.
    rzp.subs[paid]["status"] = "cancelled"
    recon.reconcile(db, now=_end(sub) + timedelta(hours=1))
    assert _sub(db, tenant.organization.id).state == "cancelled"


def test_a_refusal_from_razorpay_changes_nothing(client, db, tenant, rzp, paid):
    rzp.behaviour = "reject"
    r = _cancel(client, tenant, "at_period_end")
    assert r.status_code == 409 and _code(r) == "CANCELLATION_REFUSED"
    assert _sub(db, tenant.organization.id).cancel_at_period_end is False


def test_a_success_answer_that_does_not_show_the_cancellation_is_not_believed(client, db, tenant, rzp, paid):
    rzp.behaviour = "ok_without_effect"
    r = _cancel(client, tenant, "immediately")
    assert r.status_code == 503 and _code(r) == "CANCELLATION_UNCONFIRMED"
    assert _sub(db, tenant.organization.id).state == "active"


def test_a_plan_of_the_other_key_mode_cannot_be_cancelled_here(client, db, tenant, rzp, paid, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", "rzp_live_RoomanLiveDummy")
    r = _cancel(client, tenant, "immediately")
    assert r.status_code == 409 and _code(r) == "CANCELLATION_NOT_AVAILABLE"
    assert rzp.cancels == []


# --- past due -----------------------------------------------------------------------------------------------


def test_past_due_can_only_be_cancelled_immediately(client, db, tenant, rzp, paid):
    rzp.subs[paid]["status"] = "halted"
    recon.reconcile(db)
    assert _sub(db, tenant.organization.id).state == "past_due"
    r = _cancel(client, tenant, "at_period_end")
    assert r.status_code == 409 and _code(r) == "NOT_IN_PAID_PERIOD"
    assert _cancel(client, tenant, "immediately").json()["status"] == "cancelled"
    assert rzp.cancels == [(paid, False)]


# --- webhooks and reconciliation stay consistent ------------------------------------------------------------


def test_a_delayed_cancelled_webhook_after_an_immediate_cancel_changes_nothing(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "immediately").status_code == 200
    cancelled_at = _sub(db, tenant.organization.id).cancelled_at
    r = _webhook(client, "subscription.cancelled", paid)
    assert r.status_code == 200 and r.json()["status"] == "processed"
    sub = _sub(db, tenant.organization.id)
    assert sub.state == "cancelled" and sub.cancelled_at == cancelled_at
    assert "subscription_no_change" not in recon.reconcile(db)  # cancelled rows are not re-read


def test_webhooks_and_reconciliation_keep_a_scheduled_cancellation_in_place(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "at_period_end").status_code == 200
    assert _webhook(client, "subscription.charged", paid).json()["status"] == "processed"  # Razorpay still active
    assert recon.reconcile(db).get("subscription_no_change") == 1
    sub = _sub(db, tenant.organization.id)
    assert sub.state == "active" and sub.cancel_at_period_end is True


def test_a_renewal_charged_despite_the_scheduled_cancellation_is_flagged_not_applied(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "at_period_end").status_code == 200
    end = _end(_sub(db, tenant.organization.id))
    rzp.subs[paid]["paid_count"] = 2
    counts = recon.reconcile(db, now=end - timedelta(hours=1))
    assert counts.get("subscription_needs_review") == 1, counts
    sub = _sub(db, tenant.organization.id)
    assert _end(sub) == end and sub.provider_paid_count == 1


# --- no undo, no resume, no restart -------------------------------------------------------------------------


def test_there_is_no_undo_or_resume_operation(client, tenant, rzp, paid):
    for path in ("/plan-subscription/undo-cancellation", "/plan-subscription/resume", "/plan-subscription/reactivate"):
        assert client.post(f"{API}{path}", json={}, headers=tenant.headers()).status_code in (404, 405), path
    assert not any(hasattr(provider, name) for name in ("resume_subscription", "undo_cancellation", "pause_subscription"))


def test_a_scheduled_cancellation_cannot_be_bypassed_by_buying_again(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "at_period_end").status_code == 200
    r = client.post(f"{API}/subscription-checkout", json={"plan_code": "growth"}, headers=tenant.headers())
    assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "SUBSCRIPTION_ALREADY_ACTIVE"


def test_a_cancelled_plan_is_only_restarted_by_a_new_verified_purchase(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "immediately").status_code == 200
    r = client.post(f"{API}/subscription-checkout", json={"plan_code": "growth"}, headers=tenant.headers())
    assert r.status_code == 201, r.text  # a brand-new checkout, verified like any other
    assert _sub(db, tenant.organization.id).state == "cancelled"  # nothing restarted by starting it


def test_logs_carry_no_secrets_or_personal_data(client, db, tenant, rzp, paid, caplog):
    caplog.set_level(logging.INFO)
    _cancel(client, tenant, "at_period_end")
    for value in (SECRET, WEBHOOK_SECRET, tenant.owner.email, tenant.owner.full_name):
        assert value not in caplog.text
    assert "Plan cancellation for organization" in caplog.text


# --- customer emails (platform_notifications, migration 0044) -----------------------------------------------------


def _emails(db, kind):
    from backend.app.models import PlatformNotification

    with system_context():
        db.expire_all()
        return db.scalars(select(PlatformNotification).where(PlatformNotification.kind == kind)).all()


def test_a_scheduled_cancellation_queues_one_scheduled_email_not_an_immediate_one(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "at_period_end").status_code == 200
    _cancel(client, tenant, "at_period_end")  # repeated request
    [row] = _emails(db, "cancellation_scheduled")
    assert row.status == "pending" and "scheduled to cancel" in row.subject
    assert _emails(db, "cancelled_immediately") == []


def test_an_immediate_cancellation_queues_one_immediate_email_not_a_scheduled_one(client, db, tenant, rzp, paid):
    assert _cancel(client, tenant, "immediately").status_code == 200
    _cancel(client, tenant, "immediately")  # repeated request
    [row] = _emails(db, "cancelled_immediately")
    assert "cancelled with immediate effect" in row.text_body
    assert _emails(db, "cancellation_scheduled") == []


def test_a_refused_cancellation_queues_no_email(client, db, tenant, rzp, paid):
    rzp.behaviour = "reject"
    _cancel(client, tenant, "immediately")
    assert _emails(db, "cancelled_immediately") == [] and _emails(db, "cancellation_scheduled") == []

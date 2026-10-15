"""Platform console views of Rooman's own plan billing (GET /platform/billing/*): read-only, stored state only.

Rows are written straight into the (test) database: no Razorpay call is involved anywhere.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.core.tenant_context import system_context
from backend.app.models import (
    PlatformCheckoutAttempt,
    PlatformPayment,
    PlatformNotification,
    PlatformPaymentReview,
    PlatformProviderPlan,
    PlatformSubscription,
    PlatformWebhookEvent,
)
from backend.app.models.payments import WebhookEvent
from backend.app.models.platform import PlatformRole
from backend.tests.test_platform_console import Staff

UTC = timezone.utc
NOW = datetime.now(UTC)
BILLING = "/billing"


@pytest.fixture(autouse=True)
def clean(db):
    with system_context():
        for model in (PlatformNotification, PlatformPaymentReview, PlatformPayment, PlatformWebhookEvent, PlatformCheckoutAttempt, PlatformProviderPlan, PlatformSubscription):
            db.query(model).delete()
        db.commit()


@pytest.fixture
def ops(db):
    return Staff(db, PlatformRole.PLATFORM_OPERATIONS)


def _org(db):
    from backend.tests.conftest import Tenant

    return Tenant(db, uuid.uuid4().hex[:8]).organization


def _sub(db, org, state="active", plan="starter", sid=None, cancel=False, period_end=None, **extra):
    row = PlatformSubscription(
        organization_id=org.id, state=state, reminders_sent=[], plan_code=None if state == "trialing" else plan,
        billing_interval=None if state == "trialing" else "month", billing_interval_count=None if state == "trialing" else 1,
        current_period_start=None if state == "trialing" else NOW - timedelta(days=5),
        current_period_end=None if state == "trialing" else (period_end or NOW + timedelta(days=25)),
        cancel_at_period_end=cancel, provider_subscription_id=sid, provider_mode="test" if sid else None,
        provider_paid_count=1 if sid else None,
        trial_started_at=NOW - timedelta(days=1) if state == "trialing" else None,
        trial_ends_at=NOW + timedelta(days=1) if state == "trialing" else None,
        **({"cancelled_at": NOW - timedelta(days=1)} if state == "cancelled" and "cancelled_at" not in extra else {}), **extra)
    db.add(row)
    db.commit()
    return row


def _attempt(db, org, status="created", sid=None, created=None, authorized_at=None, last_error=None, mode="test"):
    row = PlatformCheckoutAttempt(
        organization_id=org.id, plan_code="starter", catalog_version=2, fingerprint=uuid.uuid4().hex,
        amount_minor=79900, currency="INR", billing_interval="month", billing_interval_count=1, seat_limit=3,
        tax_treatment="exclusive", provider="razorpay", mode=mode, provider_plan_id="plan_X",
        provider_subscription_id=sid, status=status, expires_at=NOW + timedelta(minutes=30),
        authorized_at=authorized_at, last_error=last_error)
    db.add(row)
    db.commit()
    if created:
        row.created_at = created
        db.commit()
    return row


def _event(db, org=None, status="processed", event_type="subscription.charged", sid="sub_A", outcome="renewed",
           received=None):
    row = PlatformWebhookEvent(
        provider="razorpay", event_id=f"evt_{uuid.uuid4().hex}", event_type=event_type, mode="test",
        provider_subscription_id=sid, provider_payment_id="pay_A", organization_id=org.id if org else None,
        status=status, outcome=outcome, received_at=received or NOW)
    db.add(row)
    db.commit()
    return row


# --- authorization ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/subscriptions", "/checkout-attempts", "/webhook-events", "/review-queue"])
def test_operations_and_administrators_can_read(db, path):
    for role in (PlatformRole.PLATFORM_ADMINISTRATOR, PlatformRole.PLATFORM_OPERATIONS):
        r = Staff(db, role).get(f"{BILLING}{path}")
        assert r.status_code == 200, (role, r.text)


@pytest.mark.parametrize("path", ["/subscriptions", "/checkout-attempts", "/webhook-events", "/review-queue"])
def test_support_is_refused(db, path):
    r = Staff(db, PlatformRole.PLATFORM_SUPPORT).get(f"{BILLING}{path}")
    assert r.status_code == 403


@pytest.mark.parametrize("path", ["/subscriptions", "/checkout-attempts", "/webhook-events", "/review-queue"])
def test_tenant_users_and_anonymous_callers_are_refused(client, tenant, path):
    url = f"/api/v1/platform{BILLING}{path}"
    assert client.get(url).status_code in (401, 403)
    assert client.get(url, headers=tenant.headers()).status_code in (401, 403)  # a tenant token is not a platform session


def test_the_views_are_read_only(ops):
    for path in ("/subscriptions", "/checkout-attempts", "/webhook-events", "/review-queue"):
        assert ops.post(f"{BILLING}{path}").status_code == 405, path


# --- subscriptions ------------------------------------------------------------------------------------------


def test_subscriptions_show_stored_state_and_the_checked_out_amount(db, ops):
    a, b, c, d, e = (_org(db) for _ in range(5))
    _sub(db, a, sid="sub_active")
    _attempt(db, a, status="completed", sid="sub_active")
    _sub(db, b, sid="sub_cancel", cancel=True)
    _sub(db, c, state="past_due", sid="sub_pd", grace_period_end=NOW + timedelta(days=3))
    _sub(db, d, state="cancelled", sid="sub_x", cancelled_at=NOW - timedelta(days=1))
    _sub(db, e, state="trialing")
    body = ops.get(f"{BILLING}/subscriptions").json()
    assert body["total"] == 4  # default "paid": trials are not plan subscriptions
    rows = {r["organization_id"]: r for r in body["items"]}
    assert rows[a.id]["amount_minor"] == 79900 and rows[a.id]["currency"] == "INR"
    assert rows[a.id]["plan_name"] == "Starter" and rows[a.id]["effective_state"] == "active"
    assert rows[b.id]["cancel_at_period_end"] is True and rows[b.id]["amount_minor"] is None  # no checkout row: not invented
    assert rows[c.id]["effective_state"] == "past_due" and rows[c.id]["grace_period_end"]
    assert rows[d.id]["effective_state"] == "cancelled" and rows[d.id]["writable"] is False
    assert {r["organization_name"] for r in body["items"]} >= {a.name, b.name}


@pytest.mark.parametrize("status, expected", [
    ("active", {"sub_active"}), ("cancellation_scheduled", {"sub_cancel"}), ("past_due", {"sub_pd"}),
    ("cancelled", {"sub_x"}), ("expired", set()),
])
def test_subscription_filters(db, ops, status, expected):
    a, b, c, d = (_org(db) for _ in range(4))
    _sub(db, a, sid="sub_active")
    _sub(db, b, sid="sub_cancel", cancel=True)
    _sub(db, c, state="past_due", sid="sub_pd", grace_period_end=NOW + timedelta(days=3))
    _sub(db, d, state="cancelled", sid="sub_x")
    body = ops.get(f"{BILLING}/subscriptions", params={"status": status}).json()
    assert {r["provider_subscription_id"] for r in body["items"]} == expected


def test_an_ended_period_shows_its_effective_state(db, ops):
    org = _org(db)
    _sub(db, org, sid="sub_old", period_end=NOW - timedelta(days=1))  # stored active, period over, not settled yet
    [row] = ops.get(f"{BILLING}/subscriptions").json()["items"]
    assert row["state"] == "active" and row["effective_state"] == "past_due"


def test_organization_filter_by_id_or_name(db, ops):
    a, b = _org(db), _org(db)
    _sub(db, a, sid="sub_a")
    _sub(db, b, sid="sub_b")
    assert [r["organization_id"] for r in ops.get(f"{BILLING}/subscriptions", params={"organization": a.id}).json()["items"]] == [a.id]
    part = b.name.split()[-1]
    assert [r["organization_id"] for r in ops.get(f"{BILLING}/subscriptions", params={"organization": part}).json()["items"]] == [b.id]
    assert ops.get(f"{BILLING}/subscriptions", params={"organization": "no-such-org"}).json()["total"] == 0


def test_invalid_filters_are_rejected(ops):
    assert ops.get(f"{BILLING}/subscriptions", params={"status": "bogus"}).status_code == 422
    assert ops.get(f"{BILLING}/checkout-attempts", params={"mode": "staging"}).status_code == 422
    assert ops.get(f"{BILLING}/webhook-events", params={"page_size": 500}).status_code == 422


# --- checkout attempts --------------------------------------------------------------------------------------


def test_checkout_attempts_pagination_and_status_filters(db, ops):
    org = _org(db)
    for i in range(7):
        _attempt(db, org, status="failed", created=NOW - timedelta(minutes=i + 10), last_error="Razorpay refused")
    _attempt(db, org, status="created", sid="sub_open")
    page1 = ops.get(f"{BILLING}/checkout-attempts", params={"page_size": 5}).json()
    page2 = ops.get(f"{BILLING}/checkout-attempts", params={"page_size": 5, "page": 2}).json()
    assert (page1["total"], page1["total_pages"], len(page1["items"]), len(page2["items"])) == (8, 2, 5, 3)
    assert page1["items"][0]["status"] == "created"  # newest first
    assert not {r["id"] for r in page1["items"]} & {r["id"] for r in page2["items"]}
    assert ops.get(f"{BILLING}/checkout-attempts", params={"status": "open"}).json()["total"] == 1
    failed = ops.get(f"{BILLING}/checkout-attempts", params={"status": "failed"}).json()
    assert failed["total"] == 7 and failed["items"][0]["last_error"] == "Razorpay refused"


def test_checkout_attempts_mark_review_and_stuck_states(db, ops):
    a, b, c, d = (_org(db) for _ in range(4))  # one open checkout per organization
    _attempt(db, a, status="authorized", sid="sub_stuck", authorized_at=NOW - timedelta(hours=30))
    _attempt(db, b, status="authorized", sid="sub_fresh", authorized_at=NOW - timedelta(hours=1))
    _attempt(db, c, status="unknown")
    _attempt(db, d, status="created", sid="sub_flagged")
    _event(db, d, status="needs_review", sid="sub_flagged", outcome="mismatch")
    rows = {r["provider_subscription_id"] or r["status"]: r for r in ops.get(f"{BILLING}/checkout-attempts").json()["items"]}
    assert rows["sub_stuck"]["stuck"] is True and rows["sub_fresh"]["stuck"] is False
    assert rows["unknown"]["stuck"] is True
    assert rows["sub_flagged"]["webhook_review"] is True and rows["sub_fresh"]["webhook_review"] is False


def test_mode_filter(db, ops):
    _attempt(db, _org(db), mode="test", sid="sub_t")  # a created checkout always has its Razorpay id
    _attempt(db, _org(db), mode="live", sid="sub_l")
    assert [r["mode"] for r in ops.get(f"{BILLING}/checkout-attempts", params={"mode": "live"}).json()["items"]] == ["live"]


# --- webhook ledger ----------------------------------------------------------------------------------------


def test_an_empty_ledger_is_reported_as_empty(ops):
    body = ops.get(f"{BILLING}/webhook-events").json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 25, "total_pages": 0}


def test_webhook_ledger_filters_and_never_shows_tenant_webhooks_or_payloads(db, ops):
    org = _org(db)
    _event(db, org, status="processed", event_type="subscription.charged")
    _event(db, org, status="ignored", event_type="subscription.updated", outcome="unsupported_event")
    _event(db, org, status="needs_review", event_type="subscription.activated", outcome="mismatch")
    # A TENANT's Razorpay webhook (their own customers' payments) with a payload: never part of this view.
    db.add(WebhookEvent(provider="razorpay", event_id="evt_tenant_1", event_type="payment.captured", organization_id=org.id,
                        payload={"secret": "tenant-payload-must-not-leak"}, signature_valid=True))
    db.commit()
    r = ops.get(f"{BILLING}/webhook-events")
    assert r.json()["total"] == 3
    assert "tenant-payload-must-not-leak" not in r.text and "evt_tenant_1" not in r.text and "payload" not in r.text
    assert "signature" not in r.text
    assert [e["status"] for e in ops.get(f"{BILLING}/webhook-events", params={"status": "needs_review"}).json()["items"]] == ["needs_review"]
    by_type = ops.get(f"{BILLING}/webhook-events", params={"event_type": "subscription.updated"}).json()["items"]
    assert [e["outcome"] for e in by_type] == ["unsupported_event"]


# --- review queue ------------------------------------------------------------------------------------------


def test_review_queue_lists_only_durable_items_newest_first(db, ops):
    org = _org(db)
    _event(db, org, status="needs_review", outcome="mismatch", received=NOW - timedelta(hours=2), sid="sub_r1")
    _event(db, org, status="processed")  # not for review
    _attempt(db, _org(db), status="authorized", sid="sub_stuck", authorized_at=NOW - timedelta(hours=30))
    _attempt(db, _org(db), status="authorized", sid="sub_fresh", authorized_at=NOW - timedelta(hours=1))  # not yet
    _attempt(db, _org(db), status="unknown", last_error="ReadTimeout")
    body = ops.get(f"{BILLING}/review-queue").json()
    assert body["total"] == 3
    sources = [i["source"] for i in body["items"]]
    assert sorted(sources) == ["checkout_authorized_stuck", "checkout_unknown", "webhook_needs_review"]
    assert body["items"][0]["source"] == "checkout_unknown"  # detected most recently
    assert body["untracked_sources"] == []  # every review finding is stored since 0041
    assert all(i["explanation"] for i in body["items"])


def test_review_queue_paginates(db, ops):
    org = _org(db)
    for i in range(3):
        _event(db, org, status="needs_review", sid=f"sub_{i}", received=NOW - timedelta(minutes=i))
    page = ops.get(f"{BILLING}/review-queue", params={"page_size": 2, "page": 2}).json()
    assert (page["total"], page["total_pages"], [i["provider_subscription_id"] for i in page["items"]]) == (3, 2, ["sub_2"])


def test_no_sensitive_fields_in_any_view(db, ops):
    org = _org(db)
    _sub(db, org, sid="sub_s")
    _attempt(db, org, status="completed", sid="sub_s")
    _event(db, org, sid="sub_s")
    for path in ("/subscriptions", "/checkout-attempts", "/webhook-events", "/review-queue"):
        text = ops.get(f"{BILLING}{path}").text.lower()
        for word in ("secret", "signature", "payload", "key_id", "password", "email", "fingerprint", "reconcile_ref"):
            assert word not in text, (path, word)

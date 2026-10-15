"""Scheduled reconciliation of Rooman plan checkouts and subscriptions with Razorpay (missed webhooks).

Razorpay is never called: plan / subscription creation, fetches and the paid-invoice lookup are fakes, and
the SDK client fails the test if anything reaches it. Verification itself is the Stage 4 code, unchanged.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.tenant_context import system_context
from backend.app.models import PlatformCheckoutAttempt, PlatformPayment, PlatformNotification, PlatformPaymentReview, PlatformProviderPlan, PlatformSubscription, PlatformWebhookEvent
from backend.app.models.billing_cycles import SchedulerHeartbeat
from backend.app.services import (
    platform_checkout_service as checkout,
    platform_payment_service as payments,
    platform_razorpay as provider,
    platform_reconciliation_service as recon,
    platform_subscription_service as subs,
    razorpay_gateway,
    scheduler,
)
from backend.tests.test_platform_checkout import KEY_ID, SECRET, _catalog
from backend.tests.test_platform_payment_verification import (
    BUSINESS_ONLY,
    STARTER_EXTRA,
    WEBHOOK_SECRET,
    Razorpay,
    _attempt,
    _expired_trial,
    _modules,
    _org,
    _pay,
    _start,
    _webhook,
    _write,
)

UTC = timezone.utc
LIVE_KEY_ID = "rzp_live_RoomanLiveDummy"


class RazorpayWithInvoices(Razorpay):
    """Stage 4's fake plus the subscription's paid invoice (the payment Razorpay charged)."""

    def __init__(self):
        super().__init__()
        self.invoices, self.invoice_lookups = {}, []

    def list_paid_subscription_invoices(self, sid):
        if self.unavailable:
            raise provider.ProviderUnavailable("timeout")
        if sid in self.paid_invoices:
            return list(self.paid_invoices[sid])
        pid = self.invoices.get(sid)
        return [{"invoice_id": f"inv_{pid[4:]}", "payment_id": pid, "paid_at": None, "billing_start": None,
                 "billing_end": None}] if pid else []

    def find_subscription_payment(self, sid):
        self.invoice_lookups.append(sid)
        if self.unavailable:
            raise provider.ProviderUnavailable("timeout")
        return self.invoices.get(sid)


@pytest.fixture(autouse=True)
def isolated(db, monkeypatch):
    with system_context():
        # The job looks at every organization: start from no platform billing rows at all (test database).
        for model in (PlatformNotification, PlatformPaymentReview, PlatformPayment, PlatformWebhookEvent, PlatformCheckoutAttempt, PlatformProviderPlan, PlatformSubscription):
            db.query(model).delete()
        db.query(SchedulerHeartbeat).filter(SchedulerHeartbeat.job_name == scheduler.PLATFORM_RECONCILE_JOB_NAME).delete()
        db.commit()
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", SECRET)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", False)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_TenantKeyNeverUsed")  # tenant keys stay unused
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "tenant-secret-never-used")

    def no_network(*a, **k):
        raise AssertionError("a test reached the real Razorpay client")

    monkeypatch.setattr(razorpay_gateway, "_get_client", no_network)
    cat = _catalog(starter="published", growth="published", business="published")
    for module in (subs, checkout, payments):
        monkeypatch.setattr(module, "catalog", lambda: cat)


@pytest.fixture
def rzp(monkeypatch):
    fake = RazorpayWithInvoices()
    for name in ("create_plan", "create_subscription", "find_plan", "find_subscription", "fetch_subscription",
                 "fetch_payment", "find_subscription_payment", "list_paid_subscription_invoices"):
        monkeypatch.setattr(provider, name, getattr(fake, name))
    return fake


def _run(db, now=None):
    db.expire_all()
    return recon.run_reconciliation(db, now=now)


def _sub(db, org_id):
    with system_context():
        db.expire_all()
        return db.scalars(select(PlatformSubscription).where(PlatformSubscription.organization_id == org_id)).first()


def _paid_checkout(client, db, tenant, rzp, plan="starter", **state):
    """A checkout the customer completed at Razorpay, while no callback or webhook ever reached us."""
    body = _start(client, tenant, plan)
    sid, pid = _pay(rzp, db, body, **state)
    rzp.invoices[sid] = pid
    return body, sid, pid


def _activated(client, db, tenant, rzp, plan="starter"):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp, plan)
    assert _run(db)["checkout_activated"] == 1
    return body, sid, pid


# --- first payment ---------------------------------------------------------------------------------------


def test_a_paid_checkout_is_recovered_without_callback_or_webhook(client, db, tenant, rzp):
    _expired_trial(db, tenant)
    body, sid, pid = _paid_checkout(client, db, tenant, rzp)
    assert _write(client, tenant).json()["error"]["code"] == "TRIAL_EXPIRED"

    counts = _run(db)
    assert counts["checkout_activated"] == 1, counts
    org = _org(db, tenant.organization.id)
    assert org.module_access == "entitled" and org.seat_limit == 3
    assert _modules(db, org.id) == STARTER_EXTRA and not (_modules(db, org.id) & BUSINESS_ONLY)
    attempt = _attempt(db, body["checkout_attempt_id"])
    assert attempt.status == "completed" and attempt.provider_payment_id == pid
    sub = _sub(db, org.id)
    assert (sub.state, sub.plan_code, sub.provider_subscription_id, sub.provider_paid_count) == ("active", "starter", sid, 1)
    assert _write(client, tenant).status_code == 201


def test_rerunning_never_activates_or_extends_twice(client, db, tenant, rzp):
    _activated(client, db, tenant, rzp)
    period_end = _sub(db, tenant.organization.id).current_period_end
    for _ in range(3):
        counts = _run(db)
        assert "checkout_activated" not in counts and "subscription_renewed" not in counts, counts
    sub = _sub(db, tenant.organization.id)
    assert sub.current_period_end == period_end and sub.provider_paid_count == 1


def test_an_authorization_alone_never_grants_access(client, db, tenant, rzp):
    _expired_trial(db, tenant)
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body, status="authenticated", paid_count=0, payment_status="authorized")  # no paid invoice
    for _ in range(2):
        counts = _run(db)
        assert counts.get("checkout_pending") == 1, counts
    assert _attempt(db, body["checkout_attempt_id"]).status == "authorized"
    assert _org(db, tenant.organization.id).module_access == "unrestricted"
    assert _write(client, tenant).json()["error"]["code"] == "TRIAL_EXPIRED"
    # Razorpay later charges the first cycle: the next run starts the plan.
    sid, pid = _pay(rzp, db, body)
    rzp.invoices[sid] = pid
    assert _run(db)["checkout_activated"] == 1
    assert _modules(db, tenant.organization.id) == STARTER_EXTRA


def test_an_uncaptured_payment_stays_pending(client, db, tenant, rzp):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp, payment_status="authorized")
    assert _run(db).get("checkout_pending") == 1
    assert _attempt(db, body["checkout_attempt_id"]).status == "authorized"
    assert _sub(db, tenant.organization.id) is None


@pytest.mark.parametrize("change", [{"amount": 100}, {"currency": "USD"}])
def test_an_amount_or_currency_mismatch_is_flagged_never_approved(client, db, tenant, rzp, change):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp, **change)
    for _ in range(2):
        counts = _run(db)
        assert counts.get("checkout_mismatch") == 1, counts
    assert _attempt(db, body["checkout_attempt_id"]).status == "created"
    assert _sub(db, tenant.organization.id) is None and _modules(db, tenant.organization.id) == set()


def test_a_payment_for_another_checkout_is_flagged(client, db, tenant, rzp):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp, notes={"checkout_attempt_id": "someone-else"})
    assert _run(db).get("checkout_mismatch") == 1
    assert _sub(db, tenant.organization.id) is None


def test_an_unpaid_checkout_expires_and_a_late_payment_is_still_found(client, db, tenant, rzp):
    body = _start(client, tenant)
    sid, _ = _pay(rzp, db, body, status="created", paid_count=0, payment_status="failed")
    expires = _attempt(db, body["checkout_attempt_id"]).expires_at.replace(tzinfo=UTC)
    assert _run(db).get("checkout_not_paid") == 1  # inside its window: left open
    assert _attempt(db, body["checkout_attempt_id"]).status == "created"
    assert _run(db, now=expires + timedelta(minutes=1)).get("checkout_expired") == 1
    assert _attempt(db, body["checkout_attempt_id"]).status == "expired"
    # Paid at the very end; Razorpay reports it after the local expiry: still activated.
    sid, pid = _pay(rzp, db, body)
    rzp.invoices[sid] = pid
    assert _run(db, now=expires + timedelta(hours=1))["checkout_activated"] == 1
    assert _attempt(db, body["checkout_attempt_id"]).status == "completed"


def test_a_checkout_cancelled_at_razorpay_before_payment_fails(client, db, tenant, rzp):
    body = _start(client, tenant)
    _pay(rzp, db, body, status="expired", paid_count=0, payment_status="failed")
    assert _run(db).get("checkout_not_paid") == 1
    assert _attempt(db, body["checkout_attempt_id"]).status == "failed"
    assert "checkout_not_paid" not in _run(db)  # terminal: no longer re-checked


# --- later cycles ------------------------------------------------------------------------------------------


def test_a_missed_renewal_is_applied_once(client, db, tenant, rzp):
    _, sid, _ = _activated(client, db, tenant, rzp)
    first_end = _sub(db, tenant.organization.id).current_period_end
    rzp.subs[sid]["paid_count"] = 2
    assert _run(db)["subscription_renewed"] == 1
    sub = _sub(db, tenant.organization.id)
    assert sub.provider_paid_count == 2 and sub.current_period_end > first_end
    renewed_end = sub.current_period_end
    assert "subscription_renewed" not in _run(db)
    assert _sub(db, tenant.organization.id).current_period_end == renewed_end


def test_a_renewal_already_applied_by_the_webhook_is_not_repeated(client, db, tenant, rzp):
    _, sid, _ = _activated(client, db, tenant, rzp)
    rzp.subs[sid]["paid_count"] = 2
    assert _webhook(client, "subscription.charged", sid).json()["status"] == "processed"
    after_webhook = _sub(db, tenant.organization.id).current_period_end
    assert "subscription_renewed" not in _run(db)
    assert _sub(db, tenant.organization.id).current_period_end == after_webhook


def test_a_failed_renewal_marks_past_due_with_grace(client, db, tenant, rzp):
    _, sid, _ = _activated(client, db, tenant, rzp)
    rzp.subs[sid]["status"] = "halted"
    assert _run(db)["subscription_past_due"] == 1
    sub = _sub(db, tenant.organization.id)
    assert sub.state == "past_due" and sub.grace_period_end is not None
    assert _write(client, tenant).status_code == 201  # still within grace
    assert "subscription_past_due" not in _run(db)


def test_a_cancellation_at_razorpay_ends_access_at_period_end(client, db, tenant, rzp):
    _, sid, _ = _activated(client, db, tenant, rzp)
    rzp.subs[sid]["status"] = "cancelled"
    assert _run(db)["subscription_cancellation_scheduled"] == 1
    sub = _sub(db, tenant.organization.id)
    assert sub.state == "active" and sub.cancel_at_period_end is True
    assert "subscription_cancellation_scheduled" not in _run(db)
    # At the period end settle records the cancellation; nothing renews it.
    counts = _run(db, now=sub.current_period_end.replace(tzinfo=UTC) + timedelta(minutes=1))
    assert counts.get("settle_settled_cancelled") == 1, counts
    assert _sub(db, tenant.organization.id).state == "cancelled"


def test_a_cancelled_plan_is_never_resurrected_by_a_stale_read(client, db, tenant, rzp):
    _, sid, _ = _activated(client, db, tenant, rzp)
    subs.cancel_now(db, tenant.organization.id)
    db.commit()
    rzp.subs[sid]["paid_count"] = 5  # whatever Razorpay says now
    counts = _run(db)
    assert not any(k.startswith("subscription_") for k in counts), counts  # cancelled rows are not re-read
    assert _sub(db, tenant.organization.id).state == "cancelled"


def test_a_renewal_charged_at_period_end_is_applied_before_settle(client, db, tenant, rzp):
    _, sid, _ = _activated(client, db, tenant, rzp)
    period_end = _sub(db, tenant.organization.id).current_period_end.replace(tzinfo=UTC)
    rzp.subs[sid]["paid_count"] = 2
    counts = _run(db, now=period_end + timedelta(hours=1))
    assert counts["subscription_renewed"] == 1 and "settle_settled_past_due" not in counts, counts
    assert _sub(db, tenant.organization.id).state == "active"


def test_settle_records_past_due_then_expired_when_nothing_was_paid(client, db, tenant, rzp):
    _activated(client, db, tenant, rzp)
    period_end = _sub(db, tenant.organization.id).current_period_end.replace(tzinfo=UTC)
    assert _run(db, now=period_end + timedelta(hours=1)).get("settle_settled_past_due") == 1
    grace_end = _sub(db, tenant.organization.id).grace_period_end.replace(tzinfo=UTC)
    assert _run(db, now=grace_end + timedelta(minutes=1)).get("settle_settled_expired") == 1
    assert _sub(db, tenant.organization.id).state == "expired"


# --- failures and safety --------------------------------------------------------------------------------


def test_razorpay_unavailable_changes_nothing_and_is_retried(client, db, tenant, rzp):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp)
    rzp.unavailable = True
    counts = _run(db)
    assert counts.get("retry_later") == 1 and "checkout_activated" not in counts, counts
    assert _attempt(db, body["checkout_attempt_id"]).status == "created" and _sub(db, tenant.organization.id) is None
    rzp.unavailable = False
    assert _run(db)["checkout_activated"] == 1


def test_a_razorpay_timeout_while_fetching_is_retried(client, db, tenant, rzp, monkeypatch):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp)

    def timeout(_sid):
        raise provider.ProviderUnavailable("timeout")

    monkeypatch.setattr(provider, "fetch_subscription", timeout)
    assert _run(db).get("retry_later") == 1
    assert _attempt(db, body["checkout_attempt_id"]).status == "created"


def test_an_unknown_subscription_at_razorpay_is_flagged(client, db, tenant, rzp):
    body = _start(client, tenant)  # Razorpay has no record of it (the fake answers 4xx)
    assert _run(db).get("checkout_mismatch") == 1
    assert _attempt(db, body["checkout_attempt_id"]).status == "created"


def test_a_failing_item_does_not_stop_the_run(client, db, tenant, rzp, monkeypatch):
    from backend.tests.conftest import Tenant

    _, bad_sid, _ = _paid_checkout(client, db, tenant, rzp)
    other = Tenant(db, uuid.uuid4().hex[:8])
    _, good_sid, _ = _paid_checkout(client, db, other, rzp)
    real = payments.sync_provider_subscription

    def flaky(db_, sid, **kw):
        if sid == bad_sid:
            raise RuntimeError("boom")
        return real(db_, sid, **kw)

    monkeypatch.setattr(payments, "sync_provider_subscription", flaky)
    counts = _run(db)
    assert counts.get("errors") == 1 and counts.get("checkout_activated") == 1, counts
    assert _sub(db, other.organization.id).state == "active" and _sub(db, tenant.organization.id) is None


def test_rows_of_the_other_key_mode_are_not_touched(client, db, tenant, rzp, monkeypatch):
    _paid_checkout(client, db, tenant, rzp)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", LIVE_KEY_ID)
    rzp.fetches.clear()
    lookups_before = len(rzp.invoice_lookups)
    counts = _run(db)
    assert counts.get("other_mode_checkouts") == 1 and not any(k.startswith("checkout_") for k in counts), counts
    assert rzp.fetches == [] and len(rzp.invoice_lookups) == lookups_before  # nothing read with the other mode's keys


def test_without_platform_keys_only_settle_runs(client, db, tenant, rzp, monkeypatch):
    _activated(client, db, tenant, rzp)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", "")
    period_end = _sub(db, tenant.organization.id).current_period_end.replace(tzinfo=UTC)
    rzp.fetches.clear()
    counts = _run(db, now=period_end + timedelta(hours=1))
    assert counts.get("razorpay_not_configured") == 1 and counts.get("settle_settled_past_due") == 1, counts
    assert rzp.fetches == []


def test_a_second_concurrent_run_is_skipped(db, rzp, monkeypatch):
    monkeypatch.setattr(scheduler, "_acquire_run_lock", lambda db_, key=None: (False, None))
    assert recon.run_reconciliation(db) == {"skipped_locked": 1}
    assert rzp.fetches == [] and rzp.invoice_lookups == []


def test_each_run_records_a_heartbeat_with_its_counts(client, db, tenant, rzp):
    _paid_checkout(client, db, tenant, rzp)
    _run(db)
    with system_context():
        db.expire_all()
        row = db.get(SchedulerHeartbeat, scheduler.PLATFORM_RECONCILE_JOB_NAME)
    assert row is not None and row.total_runs == 1 and row.last_error_count == 0
    assert row.last_counts.get("checkout_activated") == 1
    assert row.job_name != scheduler.JOB_NAME  # its own row, not the billing job's


def test_logs_carry_no_secrets_or_personal_data(client, db, tenant, rzp, caplog):
    _paid_checkout(client, db, tenant, rzp, amount=1)  # a mismatch: the noisiest path
    caplog.set_level(logging.INFO)
    _run(db)
    text = caplog.text
    assert "Platform reconciliation" in text
    for value in (SECRET, WEBHOOK_SECRET, "tenant-secret-never-used", tenant.owner.email, tenant.owner.full_name):
        assert value not in text


def test_the_scheduler_registers_the_job_once_with_overlap_protection(monkeypatch):
    added = []

    class FakeScheduler:
        def __init__(self, **kw):
            pass

        def add_job(self, fn, **kw):
            added.append((fn, kw))

        def start(self):
            pass

        def shutdown(self, wait=False):
            pass

    import apscheduler.schedulers.background as background

    monkeypatch.setattr(background, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)
    monkeypatch.setattr(scheduler, "_scheduler", None)
    try:
        scheduler.start_scheduler()
    finally:
        scheduler.stop_scheduler()
    jobs = {kw["id"]: (fn, kw) for fn, kw in added}
    fn, kw = jobs[scheduler.PLATFORM_RECONCILE_JOB_NAME]
    assert fn is scheduler._platform_reconciliation_job
    assert kw["max_instances"] == 1 and kw["coalesce"] is True
    assert kw["minutes"] == settings.PLATFORM_RECONCILE_INTERVAL_MINUTES
    assert scheduler.JOB_NAME in jobs  # the billing job is still registered as before

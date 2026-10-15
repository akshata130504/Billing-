"""Rooman subscription lifecycle emails (platform_notifications, migration 0044).

Events come from the real lifecycle / verification code (callback, webhook, reconciliation, settle, cancellation).
Razorpay is never called (fakes) and no email is ever sent: `send_email` is replaced in every test that delivers.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.tenant_context import system_context
from backend.app.models import MemberRole, PlatformNotification, PlatformSubscription
from backend.app.services import (
    platform_notification_service as notifications,
    platform_reconciliation_service as recon,
    platform_subscription_service as subs,
)
from backend.app.services.email import EmailDeliveryError
from backend.tests.test_platform_payment_verification import _pay, _start, _verify, _webhook
from backend.tests.test_platform_receipts import _activated, _renewal_charged
from backend.tests.test_platform_reconciliation import isolated, rzp  # noqa: F401  (fixtures)

UTC = timezone.utc
N = notifications


def _rows(db, kind=None, org_id=None):
    with system_context():
        db.expire_all()
        stmt = select(PlatformNotification).order_by(PlatformNotification.created_at, PlatformNotification.recipient)
        if kind:
            stmt = stmt.where(PlatformNotification.kind == kind)
        if org_id:
            stmt = stmt.where(PlatformNotification.organization_id == org_id)
        return db.scalars(stmt).all()


def _sub(db, org_id):
    with system_context():
        db.expire_all()
        return db.scalars(select(PlatformSubscription).where(PlatformSubscription.organization_id == org_id)).first()


def _billing_email(db, tenant, address="Billing@Acme.example"):
    with system_context():
        tenant.organization.email = address
        db.commit()


class Outbox:
    """Stands in for SMTP: records every send; can fail on demand."""

    def __init__(self):
        self.sent, self.fail_with, self.result = [], None, True

    def __call__(self, to, subject, text_body, html_body=None, **kw):
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append({"to": to, "subject": subject, "text": text_body, "html": html_body})
        return self.result


@pytest.fixture
def smtp(monkeypatch):
    box = Outbox()
    monkeypatch.setattr(notifications, "send_email", box)
    return box


def _deliver(db, now=None):
    with system_context():
        return N.deliver_due(db, now=now)


def _past_due(db, org_id, now=None):
    with system_context():
        sub = subs.mark_past_due(db, org_id, now=now)
        db.commit()
        return sub


# --- 1. activation: only after verification, once ---------------------------------------------------------------


@pytest.mark.parametrize("via", ["callback", "webhook", "reconciliation"])
def test_a_verified_first_payment_queues_one_activation_email_per_recipient(client, db, tenant, rzp, via):
    _billing_email(db, tenant)
    body, sid, pid = _activated(client, db, tenant, rzp, via=via)
    rows = _rows(db, N.SUBSCRIPTION_ACTIVATED)
    assert sorted(r.recipient for r in rows) == ["billing@acme.example", tenant.owner.email.lower()]
    assert {r.event_key for r in rows} == {f"subscription_activated:checkout:{body['checkout_attempt_id']}"}
    assert all(r.status == "pending" and r.attempts == 0 for r in rows)
    # the same event reported again by every other path: nothing new
    _verify(client, tenant, pid, sid)
    _webhook(client, "subscription.charged", sid, pid)
    _webhook(client, "subscription.activated", sid, pid)
    recon.run_reconciliation(db)
    assert len(_rows(db)) == 2


def test_an_owner_who_is_also_the_billing_email_gets_one_email(client, db, tenant, rzp):
    _billing_email(db, tenant, tenant.owner.email.upper())
    _activated(client, db, tenant, rzp)
    assert [r.recipient for r in _rows(db)] == [tenant.owner.email.lower()]


def test_only_active_owners_and_the_billing_email_of_that_organization_receive_it(client, db, tenant, rzp):
    from backend.tests.conftest import Tenant

    tenant.add_member("admin", MemberRole.ADMIN)
    second_owner = tenant.add_member("owner2", MemberRole.OWNER)
    other = Tenant(db, uuid.uuid4().hex[:8])
    db.commit()
    _activated(client, db, tenant, rzp)
    recipients = {r.recipient for r in _rows(db)}
    assert recipients == {tenant.owner.email.lower(), second_owner.email.lower()}
    assert other.owner.email.lower() not in recipients and all(r.organization_id == tenant.organization.id for r in _rows(db))


@pytest.mark.parametrize("state", [
    {"status": "authenticated", "paid_count": 0, "payment_status": "authorized"},  # authorization only
    {"status": "active", "paid_count": 1, "payment_status": "authorized"},  # not captured
    {"status": "active", "paid_count": 1, "payment_status": "failed"},
    {"status": "pending", "paid_count": 0, "payment_status": "failed"},
    {"status": "active", "paid_count": 1, "amount": 100},  # mismatch -> review
    {"status": "active", "paid_count": 1, "currency": "USD"},  # mismatch -> review
])
def test_no_payment_success_email_without_a_verified_payment(client, db, tenant, rzp, state):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body, **state)
    rzp.invoices[sid] = pid
    _verify(client, tenant, pid, sid)
    _webhook(client, "subscription.charged", sid, pid)
    recon.run_reconciliation(db)
    assert _rows(db) == []


# --- 2. renewal: only from a new verified renewal receipt --------------------------------------------------------


def test_a_verified_renewal_receipt_queues_one_renewal_email(client, db, tenant, rzp):
    body, sid, pid = _activated(client, db, tenant, rzp)
    pid2, _ = _renewal_charged(rzp, sid, pid)
    _webhook(client, "subscription.charged", sid, pid2)
    _webhook(client, "subscription.charged", sid, pid2)  # redelivery
    recon.run_reconciliation(db)
    [row] = _rows(db, N.RENEWAL_PAYMENT_RECEIVED)
    assert row.event_key.startswith("renewal_payment_received:payment:") and "₹799.00" in row.text_body
    assert pid2 not in row.text_body and pid2 not in (row.html_body or "")


def test_a_renewal_that_is_charged_but_not_verified_sends_no_payment_email(client, db, tenant, rzp):
    body, sid, pid = _activated(client, db, tenant, rzp)
    _renewal_charged(rzp, sid, pid, amount=50000)  # wrong amount: no receipt, flagged for review
    recon.run_reconciliation(db)
    _renewal_charged(rzp, sid, pid, visible=False)  # paid count moved, payment not visible yet
    recon.run_reconciliation(db)
    assert _rows(db, N.RENEWAL_PAYMENT_RECEIVED) == []


# --- 3-7. past due, expiry, cancellations ----------------------------------------------------------------------


def test_past_due_email_names_the_grace_deadline_and_is_queued_once(client, db, tenant, rzp):
    _activated(client, db, tenant, rzp)
    org_id = tenant.organization.id
    sub = _past_due(db, org_id)
    with system_context():
        subs.settle(db, org_id)  # repeated scheduler work while still in grace
        db.commit()
    recon.run_reconciliation(db)
    rows = _rows(db, N.PAYMENT_PAST_DUE)
    assert len(rows) == 1 and rows[0].reference_at is not None
    assert "could not confirm" in rows[0].subject and "keeps full access until" in rows[0].text_body
    assert "failed" not in rows[0].text_body.lower() and "received" not in rows[0].text_body.lower()
    assert rows[0].event_key == f"payment_past_due:subscription:{sub.id}:{N._iso(sub.grace_period_end)}"


def test_razorpay_halting_the_subscription_queues_the_past_due_email(client, db, tenant, rzp):
    body, sid, pid = _activated(client, db, tenant, rzp)
    rzp.subs[sid]["status"] = "halted"
    _webhook(client, "subscription.halted", sid)
    recon.run_reconciliation(db)
    assert len(_rows(db, N.PAYMENT_PAST_DUE)) == 1


def test_grace_ending_queues_one_read_only_email_and_retires_the_past_due_one(client, db, tenant, rzp):
    _activated(client, db, tenant, rzp)
    org_id = tenant.organization.id
    sub = _sub(db, org_id)
    period_end = sub.current_period_end.replace(tzinfo=UTC)
    with system_context():  # the scheduler was away: period end and the whole grace passed in one settle
        subs.settle(db, org_id, now=period_end + subs.grace_period() + timedelta(minutes=1))
        db.commit()
        subs.settle(db, org_id, now=period_end + subs.grace_period() + timedelta(days=3))
        db.commit()
    [expired] = _rows(db, N.ACCESS_EXPIRED)
    [past_due] = _rows(db, N.PAYMENT_PAST_DUE)
    assert expired.status == "pending" and "read-only" in expired.subject
    assert past_due.status == "superseded"  # never sent: the expiry email says it all
    assert _rows(db, N.CANCELLATION_EFFECTIVE) == []


def test_scheduled_cancellation_then_its_end_are_two_distinct_emails_without_expiry(client, db, tenant, rzp):
    _activated(client, db, tenant, rzp)
    org_id = tenant.organization.id
    with system_context():
        sub = subs.schedule_cancellation(db, org_id)
        db.commit()
    [scheduled] = _rows(db, N.CANCELLATION_SCHEDULED)
    assert "scheduled to cancel" in scheduled.subject and "still active today" in scheduled.text_body
    period_end = sub.current_period_end.replace(tzinfo=UTC)
    with system_context():
        subs.settle(db, org_id, now=period_end + timedelta(minutes=1))
        db.commit()
        subs.settle(db, org_id, now=period_end + timedelta(days=30))
        db.commit()
    [ended] = _rows(db, N.CANCELLATION_EFFECTIVE)
    assert "ended as scheduled" in ended.subject
    assert _rows(db, N.CANCELLATION_SCHEDULED)[0].status == "superseded"  # not sent after the end
    assert _rows(db, N.ACCESS_EXPIRED) == [] and _rows(db, N.PAYMENT_PAST_DUE) == []


def test_immediate_cancellation_is_distinct_and_retires_a_pending_past_due_email(client, db, tenant, rzp):
    _activated(client, db, tenant, rzp)
    org_id = tenant.organization.id
    _past_due(db, org_id)
    with system_context():
        subs.cancel_now(db, org_id)
        db.commit()
    [cancelled] = _rows(db, N.CANCELLED_IMMEDIATELY)
    assert "cancelled with immediate effect" in cancelled.text_body and "scheduled" not in cancelled.subject
    assert _rows(db, N.PAYMENT_PAST_DUE)[0].status == "superseded"


# --- transaction timing ------------------------------------------------------------------------------------------


def test_a_rolled_back_change_queues_nothing(client, db, tenant, rzp):
    _activated(client, db, tenant, rzp)
    before = len(_rows(db))
    with system_context():
        subs.mark_past_due(db, tenant.organization.id)
        db.flush()
        assert len(db.scalars(select(PlatformNotification).where(PlatformNotification.kind == N.PAYMENT_PAST_DUE)).all()) == 1
        db.rollback()
    assert len(_rows(db)) == before and _rows(db, N.PAYMENT_PAST_DUE) == []


def test_nothing_is_sent_before_the_queueing_transaction_commits(client, db, tenant, rzp, smtp):
    _activated(client, db, tenant, rzp)
    _deliver(db)
    smtp.sent.clear()
    other = Session(bind=db.get_bind())
    try:
        with system_context():
            subs.mark_past_due(db, tenant.organization.id)
            db.flush()  # queued, not committed
            assert N.deliver_due(other) == {} and smtp.sent == []  # the sender cannot see it yet
            db.commit()
            other.rollback()
            assert N.deliver_due(other).get("sent") == 1
    finally:
        other.close()
    assert [m["subject"] for m in smtp.sent] == [_rows(db, N.PAYMENT_PAST_DUE)[0].subject]


# --- delivery, retries, staleness -------------------------------------------------------------------------------


def test_delivery_sends_each_pending_email_once(client, db, tenant, rzp, smtp):
    _billing_email(db, tenant)
    _activated(client, db, tenant, rzp)
    assert _deliver(db) == {"sent": 2}
    assert _deliver(db) == {} and len(smtp.sent) == 2
    assert all(r.status == "sent" and r.sent_at is not None and r.attempts == 1 for r in _rows(db))
    assert {m["to"] for m in smtp.sent} == {"billing@acme.example", tenant.owner.email.lower()}


def test_smtp_failures_back_off_retry_and_finally_fail_without_touching_the_subscription(
        client, db, tenant, rzp, smtp, monkeypatch):
    _activated(client, db, tenant, rzp)
    org_id = tenant.organization.id
    state = lambda: (lambda s: (s.state, s.plan_code, s.current_period_end, s.provider_paid_count))(_sub(db, org_id))  # noqa: E731
    before = state()
    for name in ("activate", "renew", "mark_past_due", "cancel_now", "settle", "schedule_cancellation"):
        monkeypatch.setattr(subs, name, lambda *a, **k: pytest.fail("delivery must not change the subscription"))
    smtp.fail_with = EmailDeliveryError("timeout", "TimeoutError")
    now = datetime.now(UTC)
    assert _deliver(db, now) == {"retry_scheduled": 1}
    [row] = _rows(db)
    assert (row.status, row.attempts, row.last_error) == ("pending", 1, "smtp_timeout")
    assert row.next_attempt_at.replace(tzinfo=UTC) == now + timedelta(seconds=N.BACKOFF_SECONDS[0])
    assert _deliver(db, now + timedelta(seconds=30)) == {}  # not due yet: no attempt
    smtp.fail_with = None
    assert _deliver(db, now + timedelta(seconds=61)) == {"sent": 1}
    assert _rows(db)[0].attempts == 2 and len(smtp.sent) == 1
    assert state() == before


def test_an_email_that_keeps_failing_is_marked_failed_after_the_last_attempt(client, db, tenant, rzp, smtp):
    _activated(client, db, tenant, rzp)
    smtp.fail_with = EmailDeliveryError("unreachable", "ConnectionRefusedError")
    now = datetime.now(UTC)
    for i in range(N.MAX_ATTEMPTS):
        _deliver(db, now + timedelta(hours=13 * i))  # past every backoff, within FACT_MAX_AGE
    [row] = _rows(db)
    assert (row.status, row.attempts, row.last_error, row.sent_at) == ("failed", N.MAX_ATTEMPTS, "smtp_unreachable", None)
    assert _deliver(db, now + timedelta(days=30)) == {}


def test_smtp_not_configured_is_retried_not_dropped(client, db, tenant, rzp, smtp):
    _activated(client, db, tenant, rzp)
    smtp.result = False  # send_email returns False when SMTP_HOST is empty
    assert _deliver(db) == {"retry_scheduled": 1}
    assert _rows(db)[0].last_error == "smtp_not_configured" and _rows(db)[0].status == "pending"


def test_a_past_due_email_is_not_sent_once_the_payment_recovered(client, db, tenant, rzp, smtp):
    body, sid, pid = _activated(client, db, tenant, rzp)
    _deliver(db)
    smtp.sent.clear()
    _past_due(db, tenant.organization.id)
    with system_context():
        subs.renew(db, tenant.organization.id)  # the renewal was confirmed before the email went out
        db.commit()
    assert _deliver(db) == {"superseded": 1} and smtp.sent == []
    assert _rows(db, N.PAYMENT_PAST_DUE)[0].last_error == "no_longer_applicable"


def test_old_fact_emails_are_not_sent_late(client, db, tenant, rzp, smtp):
    _activated(client, db, tenant, rzp)
    assert _deliver(db, datetime.now(UTC) + N.FACT_MAX_AGE + timedelta(hours=1)) == {"superseded": 1}
    assert smtp.sent == []


# --- content and schema guards ----------------------------------------------------------------------------------


def test_email_content_is_clear_and_carries_no_payment_identifiers(client, db, tenant, rzp, smtp):
    _billing_email(db, tenant)
    body, sid, pid = _activated(client, db, tenant, rzp)
    _deliver(db)
    owner_mail = next(m for m in smtp.sent if m["to"] == tenant.owner.email.lower())
    billing_mail = next(m for m in smtp.sent if m["to"] == "billing@acme.example")
    assert owner_mail["subject"].startswith("Payment confirmed") and "is active" in owner_mail["subject"]
    assert "₹799.00" in owner_mail["text"] and "not a GST tax invoice" in owner_mail["text"]
    assert "Test Mode" in owner_mail["text"] and "/settings/subscription" in owner_mail["text"]
    assert owner_mail["text"].startswith(f"Hello {tenant.owner.full_name},") and billing_mail["text"].startswith("Hello,")
    for mail in smtp.sent:
        blob = mail["subject"] + mail["text"] + (mail["html"] or "")
        assert sid not in blob and pid not in blob and body["checkout_attempt_id"] not in blob
        assert "rzp_" not in blob and "secret" not in blob.lower()


def test_event_keys_must_be_namespaced_by_kind_and_are_unique_per_recipient(db, tenant):
    now = datetime.now(UTC)
    row = dict(organization_id=tenant.organization.id, kind="payment_past_due", recipient="a@example.test",
               subject="s", text_body="t", status="pending", attempts=0, created_at=now, updated_at=now)
    with system_context():
        db.add(PlatformNotification(event_key="access_expired:subscription:x", **row))  # another kind's key
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(PlatformNotification(event_key="payment_past_due:subscription:x", **row))
        db.commit()
        db.add(PlatformNotification(event_key="payment_past_due:subscription:x", **row))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    with pytest.raises(ValueError):
        N._queue(db, kind="payment_past_due", key="subscription:x", org=tenant.organization, sub=None,
                 reference_at=None, build=lambda name: ("s", "t", None))


def test_the_scheduler_registers_the_delivery_job():
    from backend.app.services import scheduler

    assert scheduler.PLATFORM_NOTIFY_JOB_NAME == "platform_notifications"
    assert callable(scheduler._platform_notification_job)


# --- terminal-failure alerts ------------------------------------------------------------------------------------


class Alerts:
    """Stands in for core/alerts.send_alert; can raise like a broken alert service. Records the row's committed
    status (read through a separate session) at the moment of the alert."""

    def __init__(self, db):
        self.db, self.calls, self.fail = db, [], False

    def __call__(self, event, summary, details=None, severity="error", *, dedup_key=None):
        other = Session(bind=self.db.get_bind())
        try:
            committed = other.get(PlatformNotification, details["notification_id"]).status
        finally:
            other.close()
        self.calls.append({"event": event, "summary": summary, "details": dict(details), "severity": severity,
                           "dedup_key": dedup_key, "committed_status": committed})
        if self.fail:
            raise RuntimeError("alert webhook down")
        return True


@pytest.fixture
def alerts(db, monkeypatch):
    from backend.app.core import alerts as core_alerts

    fake = Alerts(db)
    monkeypatch.setattr(core_alerts, "send_alert", fake)
    return fake


def _exhaust(db, smtp, now):
    for i in range(N.MAX_ATTEMPTS):
        _deliver(db, now + timedelta(hours=13 * i))


def _audit_entries(db, notification_id):
    from backend.app.models.platform import PlatformAuditLog

    with system_context():
        db.expire_all()
        return db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.target_id == notification_id)).all()


def test_retrying_emails_do_not_alert(client, db, tenant, rzp, smtp, alerts):
    _activated(client, db, tenant, rzp)
    smtp.fail_with = EmailDeliveryError("timeout", "TimeoutError")
    now = datetime.now(UTC)
    for i in range(N.MAX_ATTEMPTS - 1):  # every attempt but the last
        _deliver(db, now + timedelta(hours=13 * i))
    [row] = _rows(db)
    assert row.status == "pending" and row.attempts == N.MAX_ATTEMPTS - 1
    assert alerts.calls == [] and _audit_entries(db, row.id) == []


def test_a_terminal_failure_alerts_once_after_commit_with_an_audit_entry(client, db, tenant, rzp, smtp, alerts):
    _activated(client, db, tenant, rzp)
    smtp.fail_with = EmailDeliveryError("auth", "SMTPAuthenticationError")
    now = datetime.now(UTC)
    _exhaust(db, smtp, now)
    [row] = _rows(db)
    assert row.status == "failed"
    [alert] = alerts.calls
    assert alert["event"] == "platform_notification.failed" and alert["severity"] == "error"
    assert alert["committed_status"] == "failed"  # sent only after the failed state was committed
    assert alert["details"] == {"notification_id": row.id, "kind": "subscription_activated",
                                "organization_id": tenant.organization.id, "attempts": N.MAX_ATTEMPTS,
                                "error_category": "smtp_auth"}
    assert alert["dedup_key"] == f"platform_notification.failed:{row.id}:{N.MAX_ATTEMPTS}"
    [entry] = _audit_entries(db, row.id)
    assert (entry.action, entry.result, entry.target_type, entry.organization_id) == (
        "PLATFORM_NOTIFICATION_FAILED", "failure", "platform_notification", tenant.organization.id)
    assert entry.details == {"kind": "subscription_activated", "organization_id": tenant.organization.id,
                             "attempts": N.MAX_ATTEMPTS, "error_category": "smtp_auth"}
    # later scheduler runs never alert again for it
    for days in (1, 2, 30):
        assert _deliver(db, now + timedelta(days=days)) == {}
    assert len(alerts.calls) == 1 and len(_audit_entries(db, row.id)) == 1


def test_each_failed_notification_alerts_separately(client, db, tenant, rzp, smtp, alerts):
    _billing_email(db, tenant)
    _activated(client, db, tenant, rzp)  # two recipients -> two notifications
    smtp.fail_with = EmailDeliveryError("unreachable", "ConnectionRefusedError")
    _exhaust(db, smtp, datetime.now(UTC))
    assert sorted(c["details"]["notification_id"] for c in alerts.calls) == sorted(r.id for r in _rows(db))


def test_alert_content_is_safe(client, db, tenant, rzp, smtp, alerts):
    _billing_email(db, tenant)
    body, sid, pid = _activated(client, db, tenant, rzp)
    smtp.fail_with = EmailDeliveryError("rejected", "SMTPRecipientsRefused 550 owner@x password=hunter2")
    _exhaust(db, smtp, datetime.now(UTC))
    rows = _rows(db)
    blob = repr(alerts.calls) + repr([e.details for r in rows for e in _audit_entries(db, r.id)])
    for private in [tenant.owner.email.lower(), "billing@acme.example", "hunter2", "SMTPRecipientsRefused", "550",
                    sid, pid, body["checkout_attempt_id"], rows[0].subject, "Hello"]:
        assert private not in blob, private
    assert {c["details"]["error_category"] for c in alerts.calls} == {"smtp_rejected"}


def test_only_allow_listed_error_categories_reach_alerts():
    assert N.safe_error_category("smtp_timeout") == "smtp_timeout"
    assert N.safe_error_category("error_ValueError") == "unclassified"  # no exception class names
    assert N.safe_error_category("smtp 535 password=x") == "unclassified"
    assert N.safe_error_category(None) == "unclassified"


def test_a_broken_alert_service_keeps_the_row_failed_and_the_scheduler_running(
        client, db, tenant, rzp, smtp, alerts, caplog):
    import logging

    _billing_email(db, tenant)
    _activated(client, db, tenant, rzp)
    alerts.fail = True
    smtp.fail_with = EmailDeliveryError("timeout", "TimeoutError")
    caplog.set_level(logging.INFO)
    now = datetime.now(UTC)
    for i in range(N.MAX_ATTEMPTS - 1):
        _deliver(db, now + timedelta(hours=13 * i))
    counts = _deliver(db, now + timedelta(hours=13 * (N.MAX_ATTEMPTS - 1)))  # both reach the limit in this run
    assert counts == {"failed": 2} and "errors" not in counts
    assert {r.status for r in _rows(db)} == {"failed"} and len(alerts.calls) == 2
    assert "failure alert could not be sent (RuntimeError)" in caplog.text
    assert "failed after 8 attempts: smtp_timeout" in caplog.text  # safe facts kept in the log
    assert tenant.owner.email.lower() not in caplog.text and "billing@acme.example" not in caplog.text


def test_the_email_delivery_view_matches_the_stored_failed_status(client, db, tenant, rzp, smtp, alerts):
    from backend.app.models.platform import PlatformRole
    from backend.tests.test_platform_console import Staff

    _activated(client, db, tenant, rzp)
    smtp.fail_with = EmailDeliveryError("timeout", "TimeoutError")
    _exhaust(db, smtp, datetime.now(UTC))
    [item] = Staff(db, PlatformRole.PLATFORM_OPERATIONS).get("/billing/notifications").json()["items"]
    assert (item["status"], item["attempts"], item["error_code"], item["next_attempt_at"]) == (
        "failed", N.MAX_ATTEMPTS, "smtp_timeout", None)

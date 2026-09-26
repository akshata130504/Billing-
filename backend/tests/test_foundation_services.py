"""Tests for Phase 1 foundation services: UnitOfWork, Idempotency, DurableJobs, Notifications."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from backend.app.models.events import DomainEventType, JobStatus, OutboxEvent, OutboxStatus
from backend.app.models.notifications import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationTemplate,
)
from backend.app.services.durable_job_service import (
    claim_due_jobs,
    complete_job,
    enqueue_job,
    fail_job,
)
from backend.app.services.idempotency_service import (
    check_idempotency,
    complete_idempotency,
)
from backend.app.services.notification_service import (
    create_or_update_template,
    dispatch_notification,
    get_active_template,
    render_template_string,
)
from backend.app.services.unit_of_work import UnitOfWork


def test_unit_of_work_registers_events_atomically(tenant, db):
    org_id = tenant.organization.id

    with UnitOfWork(db) as uow:
        uow.register_event(
            organization_id=org_id,
            event_type=DomainEventType.INVOICE_ISSUED,
            aggregate_type="invoice",
            aggregate_id="inv-12345",
            payload={"amount": "100.00", "currency": "INR"},
        )
        uow.register_event(
            organization_id=org_id,
            event_type=DomainEventType.PAYMENT_CAPTURED,
            aggregate_type="payment",
            aggregate_id="pay-99999",
            payload={"amount": "100.00"},
        )
        events = uow.pending_events
        assert len(events) == 2

    # Query outbox_events to ensure they persisted
    persisted = db.query(OutboxEvent).filter(OutboxEvent.organization_id == org_id).all()
    assert len(persisted) == 2
    types = {e.event_type for e in persisted}
    assert DomainEventType.INVOICE_ISSUED.value in types
    assert DomainEventType.PAYMENT_CAPTURED.value in types
    assert all(e.status == OutboxStatus.PENDING for e in persisted)


def test_idempotency_service(tenant, db):
    org_id = tenant.organization.id
    key = "idem-key-abc-123"
    path = "/api/v1/invoices"
    method = "POST"
    payload = {"customer_id": "cust-1", "amount": "500"}

    # 1. First check: should return is_cached=False (not processed yet)
    record, is_cached = check_idempotency(db, org_id, key, path, method, payload)
    assert is_cached is False
    assert record.status == "processing"

    # 2. Complete the idempotency record with status and response body
    complete_idempotency(
        db,
        organization_id=org_id,
        idempotency_key=key,
        status_code=201,
        response_body={"id": "inv-new-123", "amount": "500"},
    )

    # 3. Second check: should return cached record
    cached_record, is_cached_again = check_idempotency(db, org_id, key, path, method, payload)
    assert is_cached_again is True
    assert cached_record is not None
    assert cached_record.status == "completed"
    assert cached_record.status_code == 201
    assert cached_record.response_body["id"] == "inv-new-123"


def test_durable_jobs_lifecycle(tenant, db):
    org_id = tenant.organization.id

    # 1. Enqueue job
    job = enqueue_job(
        db,
        organization_id=org_id,
        job_type="dunning.retry_payment",
        payload={"invoice_id": "inv-dunning-1"},
        max_attempts=2,
    )
    assert job.status == JobStatus.PENDING
    assert job.attempts == 0

    # 2. Claim job
    claimed = claim_due_jobs(db, worker_id="worker-node-1", limit=5)
    assert len(claimed) >= 1
    target = next((j for j in claimed if j.id == job.id), None)
    assert target is not None
    assert target.status == JobStatus.RUNNING
    assert target.attempts == 1
    assert target.locked_by == "worker-node-1"

    # 3. Fail job (first attempt - should retry immediately in test)
    failed = fail_job(db, job.id, error_message="Gateway timeout", retry_delay_seconds=0)
    assert failed.status == JobStatus.PENDING
    assert failed.last_error == "Gateway timeout"

    # 4. Claim again and fail second time (should transition to DEAD since max_attempts=2)
    claimed2 = claim_due_jobs(db, worker_id="worker-node-2", limit=5)
    target2 = next((j for j in claimed2 if j.id == job.id), None)
    assert target2 is not None
    assert target2.attempts == 2

    dead_job = fail_job(db, job.id, error_message="Gateway persistent failure")
    assert dead_job.status == JobStatus.DEAD


def test_notification_service_and_templates(tenant, db):
    org_id = tenant.organization.id

    # 1. Template string rendering
    rendered = render_template_string(
        "Hello {{ customer_name }}, your invoice {{ invoice_number }} for {{ amount }} is ready.",
        {"customer_name": "Acme Corp", "invoice_number": "INV-0001", "amount": "₹500.00"},
    )
    assert rendered == "Hello Acme Corp, your invoice INV-0001 for ₹500.00 is ready."

    # 2. Create template
    tmpl = create_or_update_template(
        db,
        organization_id=org_id,
        code="invoice_issued",
        name="Invoice Issued Notice",
        channel=NotificationChannel.EMAIL,
        subject_template="Invoice {{ invoice_number }} has been generated",
        body_template="Dear {{ customer_name }}, please pay {{ amount }} by {{ due_date }}.",
    )
    assert tmpl.version == 1

    active = get_active_template(db, org_id, "invoice_issued")
    assert active is not None
    assert active.id == tmpl.id

    # 3. Dispatch notification
    delivery = dispatch_notification(
        db,
        organization_id=org_id,
        channel=NotificationChannel.EMAIL,
        recipient="finance@acme.example",
        template_code="invoice_issued",
        context={
            "invoice_number": "INV-0042",
            "customer_name": "Acme",
            "amount": "₹1,200",
            "due_date": "2026-10-01",
        },
    )
    # No SMTP configured anywhere: never reported as SENT.
    assert delivery.status == NotificationDeliveryStatus.FAILED
    assert delivery.error == "smtp_not_configured"
    assert delivery.subject == "Invoice INV-0042 has been generated"
    assert "Dear Acme, please pay ₹1,200 by 2026-10-01." in delivery.body


def test_email_notification_is_queued_then_sent_by_outbox(tenant, db, monkeypatch):
    from backend.app.core.config import settings
    from backend.app.services import email as email_module
    from backend.app.services.outbox_processor import process_pending_outbox

    org_id = tenant.organization.id
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.provider.example")
    sent = []

    def fake_send_email(**kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setattr(email_module, "send_email", fake_send_email)

    delivery = dispatch_notification(
        db,
        organization_id=org_id,
        channel=NotificationChannel.EMAIL,
        recipient="cust@acme.example",
        subject="Hello",
        body="<p>Hi <b>there</b></p>",
    )
    db.commit()
    assert delivery.status == NotificationDeliveryStatus.PENDING
    assert sent == []

    process_pending_outbox(db, organization_id=org_id)
    db.refresh(delivery)
    assert delivery.status == NotificationDeliveryStatus.SENT
    assert sent[0]["to"] == ["cust@acme.example"]
    assert sent[0]["html_body"] == "<p>Hi <b>there</b></p>"
    assert "Hi there" in sent[0]["text_body"]


def test_email_notification_smtp_errors_retry_then_fail(tenant, db, monkeypatch):
    from backend.app.core.config import settings
    from backend.app.services import email as email_module
    from backend.app.services.outbox_processor import process_pending_outbox

    org_id = tenant.organization.id
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.provider.example")

    def broken_send_email(**kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(email_module, "send_email", broken_send_email)
    delivery = dispatch_notification(
        db, organization_id=org_id, channel=NotificationChannel.EMAIL, recipient="x@acme.example", subject="S", body="B"
    )
    db.commit()
    process_pending_outbox(db, organization_id=org_id, max_attempts=1)
    db.refresh(delivery)
    assert delivery.status == NotificationDeliveryStatus.FAILED
    assert "connection refused" in delivery.error


def test_sms_and_blocked_webhook_notifications_are_not_marked_sent(tenant, db):
    org_id = tenant.organization.id
    sms = dispatch_notification(db, organization_id=org_id, channel=NotificationChannel.SMS, recipient="+911234567890", body="hi")
    assert sms.status == NotificationDeliveryStatus.FAILED
    assert sms.error == "sms_not_supported"
    hook = dispatch_notification(
        db, organization_id=org_id, channel=NotificationChannel.WEBHOOK, recipient="http://127.0.0.1/hook", body="{}"
    )
    assert hook.status == NotificationDeliveryStatus.FAILED
    assert hook.error == "webhook_destination_blocked"
    db.rollback()


def test_render_template_string_escapes_values_in_html_templates():
    html_out = render_template_string("<p>Dear {{ name }}</p>", {"name": "<script>x</script>"})
    assert html_out == "<p>Dear &lt;script&gt;x&lt;/script&gt;</p>"
    subject = render_template_string("Invoice for {{ name }}", {"name": "A & B"})
    assert subject == "Invoice for A & B"


def test_idempotency_key_reused_with_mismatched_payload_raises_conflict(tenant, db):
    from backend.app.core.exceptions import ConflictAppError

    org_id = tenant.organization.id
    key = "idem-key-mismatch-test"
    path = "/api/v1/payments"
    method = "POST"
    payload1 = {"amount": "100.00", "currency": "INR"}
    payload2 = {"amount": "200.00", "currency": "INR"}

    record, is_cached = check_idempotency(db, org_id, key, path, method, payload1)
    assert is_cached is False
    assert record.status == "processing"

    # Reusing same key with different payload must raise ConflictAppError
    with pytest.raises(ConflictAppError) as exc_info:
        check_idempotency(db, org_id, key, path, method, payload2)
    assert "mismatched request parameters" in str(exc_info.value)


def test_outbox_processor_claim_and_publish(tenant, db):
    from backend.app.services.outbox_processor import claim_and_publish_outbox_events, register_outbox_handler, clear_outbox_handlers
    from backend.app.models.events import OutboxEvent, OutboxStatus

    org_id = tenant.organization.id
    clear_outbox_handlers()

    handled_events = []
    def dummy_handler(session, event):
        handled_events.append(event.id)

    register_outbox_handler("test.event", dummy_handler)

    # Add 2 pending outbox events
    e1 = OutboxEvent(
        organization_id=org_id,
        event_type="test.event",
        aggregate_type="test",
        aggregate_id="agg-1",
        payload={"foo": "bar"},
        status=OutboxStatus.PENDING,
    )
    e2 = OutboxEvent(
        organization_id=org_id,
        event_type="test.event",
        aggregate_type="test",
        aggregate_id="agg-2",
        payload={"foo": "baz"},
        status=OutboxStatus.PENDING,
    )
    db.add_all([e1, e2])
    db.commit()

    published = claim_and_publish_outbox_events(db, organization_id=org_id, limit=10)
    assert published == 2
    assert len(handled_events) == 2

    # Verify statuses in DB
    db.refresh(e1)
    db.refresh(e2)
    assert e1.status == OutboxStatus.PUBLISHED
    assert e1.published_at is not None
    assert e2.status == OutboxStatus.PUBLISHED
    assert e2.published_at is not None
    clear_outbox_handlers()


def test_outbox_failed_event_backs_off_and_eventually_fails(tenant, db):
    from backend.app.services.outbox_processor import (
        clear_outbox_handlers,
        process_pending_outbox,
        register_outbox_handler,
    )

    org_id = tenant.organization.id
    clear_outbox_handlers()
    calls = []

    def flaky(session, event):
        calls.append(event.id)
        raise RuntimeError("downstream unavailable")

    register_outbox_handler("test.flaky", flaky)
    try:
        event = OutboxEvent(
            organization_id=org_id,
            event_type="test.flaky",
            aggregate_type="test",
            aggregate_id="agg-f",
            payload={},
            status=OutboxStatus.PENDING,
        )
        db.add(event)
        db.commit()

        assert process_pending_outbox(db, organization_id=org_id, max_attempts=2) == 0
        db.refresh(event)
        assert event.status == OutboxStatus.PENDING
        assert event.retry_count == 1
        assert "downstream unavailable" in event.last_error
        next_at = event.next_attempt_at if event.next_attempt_at.tzinfo else event.next_attempt_at.replace(tzinfo=timezone.utc)
        assert next_at > datetime.now(timezone.utc)

        # Backoff respected: not re-attempted immediately.
        process_pending_outbox(db, organization_id=org_id, max_attempts=2)
        assert len(calls) == 1

        event.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        process_pending_outbox(db, organization_id=org_id, max_attempts=2)
        db.refresh(event)
        assert event.status == OutboxStatus.FAILED
        assert event.retry_count == 2
    finally:
        clear_outbox_handlers()


def test_outbox_reclaims_events_stuck_in_processing(tenant, db):
    from backend.app.services.outbox_processor import process_pending_outbox

    org_id = tenant.organization.id
    stuck = OutboxEvent(
        organization_id=org_id,
        event_type="test.stuck",
        aggregate_type="test",
        aggregate_id="agg-s",
        payload={},
        status=OutboxStatus.PROCESSING,
        locked_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    fresh = OutboxEvent(
        organization_id=org_id,
        event_type="test.stuck",
        aggregate_type="test",
        aggregate_id="agg-p",
        payload={},
        status=OutboxStatus.PROCESSING,
        locked_at=datetime.now(timezone.utc),
    )
    db.add_all([stuck, fresh])
    db.commit()

    process_pending_outbox(db, organization_id=org_id)
    db.refresh(stuck)
    db.refresh(fresh)
    assert stuck.status == OutboxStatus.PUBLISHED
    assert fresh.status == OutboxStatus.PROCESSING  # still within its lease


def test_process_due_jobs_runs_only_registered_job_types(tenant, db):
    from backend.app.services.outbox_processor import clear_job_handlers, process_due_jobs, register_job_handler

    org_id = tenant.organization.id
    clear_job_handlers()
    handled = []
    known = enqueue_job(db, org_id, "cust.test.known", {"n": 1})
    unknown = enqueue_job(db, org_id, "cust.test.unknown", {"n": 2})
    db.commit()
    try:
        assert process_due_jobs(db) == 0  # nothing registered, nothing claimed
        register_job_handler("cust.test.known", lambda session, job: handled.append(job.payload["n"]))
        assert process_due_jobs(db) >= 1
        db.refresh(known)
        db.refresh(unknown)
        assert known.status == JobStatus.COMPLETED
        assert unknown.status == JobStatus.PENDING and unknown.attempts == 0
        assert handled == [1]
    finally:
        clear_job_handlers()

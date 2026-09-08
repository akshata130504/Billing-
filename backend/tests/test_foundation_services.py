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
    assert delivery.status == NotificationDeliveryStatus.SENT
    assert delivery.subject == "Invoice INV-0042 has been generated"
    assert "Dear Acme, please pay ₹1,200 by 2026-10-01." in delivery.body


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

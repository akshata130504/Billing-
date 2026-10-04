"""Scheduler honours organization lifecycle (platform phase 1, services/org_lifecycle.py).

For an ACTIVE organization every job behaves as before. For a SUSPENDED / PENDING_DELETION /
DELETED organization, or one with jobs_paused, the scheduler starts no billing work: no trial or
dunning charges, no renewal invoices, no scheduled plan changes, no overdue marking, no billing
emails, no recurring expenses, no outbox delivery or automation schedules. The check is made in
each work item's own transaction, so a change committed after the run started is honoured.
Inbound payment webhooks keep being recorded for any organization.
"""
import hashlib
import hmac
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text, update

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, engine
from backend.app.models import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    Invoice,
    InvoiceStatus,
    Organization,
    OrganizationStatus,
    Payment,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    utcnow,
)
from backend.app.models.dunning import DunningAttempt, DunningCase
from backend.app.models.events import OutboxEvent, OutboxStatus
from backend.app.models.expenses import Expense, RecurringExpense, RecurringExpenseFrequency, RecurringExpenseStatus
from backend.app.services import dunning_service, org_lifecycle, scheduler
from backend.app.services.gateways.base import GatewayChargeResult
from backend.app.services.gateways.registry import get_gateway_adapter, register_gateway_adapter
from backend.app.services.outbox_processor import clear_outbox_handlers, register_outbox_handler
from backend.app.services.scheduler import run_billing_jobs

INACTIVE = [
    OrganizationStatus.SUSPENDED,
    OrganizationStatus.PENDING_DELETION,
    OrganizationStatus.DELETED,
    # Never approved: must not be billed or emailed either.
    OrganizationStatus.PENDING_APPROVAL,
    OrganizationStatus.REJECTED,
]
TEST_EVENT = "lifecycle.test_event"


# --- harness ------------------------------------------------------------------------------------------


class _RecordingAdapter:
    """Stands in for Razorpay: records every unattended charge and approves it."""

    gateway_type = PaymentGateway.RAZORPAY

    def __init__(self):
        self.charges = []

    def charge(self, **kwargs):
        self.charges.append(kwargs)
        return GatewayChargeResult(success=True, gateway_payment_id=f"pay_{uuid.uuid4().hex[:14]}")

    def refund(self, **kwargs):  # pragma: no cover - not used
        raise NotImplementedError

    def verify_webhook(self, **kwargs):  # pragma: no cover - not used
        return True


@pytest.fixture
def gateway():
    real = get_gateway_adapter(PaymentGateway.RAZORPAY)
    fake = _RecordingAdapter()
    register_gateway_adapter(PaymentGateway.RAZORPAY, fake)
    try:
        yield fake
    finally:
        register_gateway_adapter(PaymentGateway.RAZORPAY, real)


@pytest.fixture
def outbox_seen():
    seen = []
    clear_outbox_handlers()
    register_outbox_handler(TEST_EVENT, lambda session, event: seen.append(event.id))
    try:
        yield seen
    finally:
        clear_outbox_handlers()


def _second_tenant(db):
    from backend.tests.conftest import Tenant

    return Tenant(db, uuid.uuid4().hex[:8])


def _set_org(org_id, *, status=None, jobs_paused=None):
    """Change the organization from a separate session, as another actor would."""
    values = {}
    if status is not None:
        values["status"] = status
    if jobs_paused is not None:
        values["jobs_paused"] = jobs_paused
    other = SessionLocal()
    try:
        if engine.dialect.name == "postgresql":
            # Never hang a test run: a status change that cannot get the row surfaces as an error.
            other.execute(text("SET LOCAL lock_timeout = '10s'"))
        other.execute(update(Organization).where(Organization.id == org_id).values(**values))
        other.commit()
    finally:
        other.close()


def _card(db, tenant, customer):
    pm = CustomerPaymentMethod(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        type="card",
        status=CustomerPaymentMethodStatus.ACTIVE,
        gateway="razorpay",
        gateway_token=f"tok_{uuid.uuid4().hex[:10]}",
        last4="4242",
        card_brand="visa",
        exp_month=12,
        exp_year=date.today().year + 3,
        is_default=True,
    )
    db.add(pm)
    db.commit()
    return pm


def _seed_due_work(db, tenant):
    """One of every kind of scheduler work, all due today, for this tenant."""
    from backend.app.core.tenant_context import system_context

    with system_context():
        return _seed_due_work_impl(db, tenant)


def _seed_due_work_impl(db, tenant):
    org_id = tenant.organization.id
    today = date.today()
    ids = {}

    # Trial that ended yesterday with a card on file -> converted + charged.
    trial_customer = tenant.customer()
    _, trial_plan = tenant.product_with_plan(unit_amount="1000.00", trial_days=14)
    trial = Subscription(
        organization_id=org_id, customer_id=trial_customer.id, plan_id=trial_plan.id, quantity=1,
        status=SubscriptionStatus.TRIALING, start_date=today - timedelta(days=15),
        trial_end=today - timedelta(days=1), current_period_start=today - timedelta(days=15),
        current_period_end=today - timedelta(days=1), subscription_number=f"SUB-T-{uuid.uuid4().hex[:6]}",
    )
    db.add(trial)
    db.commit()
    _card(db, tenant, trial_customer)
    ids["trial_sub"], ids["trial_customer"] = trial.id, trial_customer.id

    # Active subscription due for renewal today -> renewal invoice.
    renew_customer = tenant.customer()
    _, renew_plan = tenant.product_with_plan(unit_amount="2000.00", interval="monthly")
    renewal = Subscription(
        organization_id=org_id, customer_id=renew_customer.id, plan_id=renew_plan.id, quantity=1,
        status=SubscriptionStatus.ACTIVE, start_date=today - timedelta(days=30),
        current_period_start=today - timedelta(days=30), current_period_end=today, next_billing_date=today,
        subscription_number=f"SUB-R-{uuid.uuid4().hex[:6]}",
    )
    db.add(renewal)
    db.commit()
    ids["renewal_sub"] = renewal.id

    # Sent invoice past its due date -> marked overdue.
    overdue_customer = tenant.customer()
    overdue = Invoice(
        organization_id=org_id, customer_id=overdue_customer.id, invoice_number=f"INV-O-{uuid.uuid4().hex[:6]}",
        status=InvoiceStatus.SENT, issue_date=today - timedelta(days=40), due_date=today - timedelta(days=10),
        subtotal=Decimal("500.00"), total=Decimal("500.00"), amount_paid=Decimal("0.00"),
        amount_due=Decimal("500.00"), public_token=uuid.uuid4().hex,
    )
    db.add(overdue)
    db.commit()
    ids["overdue_invoice"] = overdue.id

    # Overdue invoice never reminded -> dunning reminder email.
    remind_customer = tenant.customer()
    remind = Invoice(
        organization_id=org_id, customer_id=remind_customer.id, invoice_number=f"INV-D-{uuid.uuid4().hex[:6]}",
        status=InvoiceStatus.OVERDUE, issue_date=today - timedelta(days=40), due_date=today - timedelta(days=10),
        subtotal=Decimal("300.00"), total=Decimal("300.00"), amount_paid=Decimal("0.00"),
        amount_due=Decimal("300.00"), public_token=uuid.uuid4().hex, reminder_count=0,
    )
    db.add(remind)
    db.commit()
    ids["reminder_invoice"] = remind.id

    # Dunning case due for a retry with a card -> charged.
    dun_customer = tenant.customer()
    _, dun_plan = tenant.product_with_plan(unit_amount="2500.00")
    dun_sub = Subscription(
        organization_id=org_id, subscription_number=f"SUB-D-{uuid.uuid4().hex[:6]}", customer_id=dun_customer.id,
        plan_id=dun_plan.id, status=SubscriptionStatus.ACTIVE, quantity=1, start_date=today,
        current_period_start=today, current_period_end=today + timedelta(days=30),
    )
    db.add(dun_sub)
    db.commit()
    dun_inv = tenant.invoice(dun_customer, amount="2500.00", status=InvoiceStatus.SENT)
    case = dunning_service.trigger_dunning_for_failed_payment(
        db=db, organization_id=org_id, invoice_id=dun_inv.id, customer_id=dun_customer.id,
        subscription_id=dun_sub.id, reason="card_declined", payment_method_type="card",
    )
    db.commit()
    _card(db, tenant, dun_customer)
    case.next_retry_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    ids["dunning_case"], ids["dunning_customer"] = case.id, dun_customer.id

    # Recurring expense due today -> expense created.
    rec = RecurringExpense(
        organization_id=org_id, name="Server backup", category="Infrastructure", amount=Decimal("80.00"),
        currency="INR", frequency=RecurringExpenseFrequency.MONTHLY, start_date=today, next_run=today,
        status=RecurringExpenseStatus.ACTIVE,
    )
    db.add(rec)
    db.commit()
    ids["recurring_expense"] = rec.id

    # Queued outbox event -> delivered.
    event = OutboxEvent(
        organization_id=org_id, event_type=TEST_EVENT, aggregate_type="test", aggregate_id=uuid.uuid4().hex[:12],
        payload={}, status=OutboxStatus.PENDING,
    )
    db.add(event)
    db.commit()
    ids["outbox_event"] = event.id

    # Due automation schedule -> executed (next_date advanced).
    from backend.app.models.customization import AutomationSchedule, ScheduleFrequency

    schedule = AutomationSchedule(
        organization_id=org_id, name="Due export", frequency=ScheduleFrequency.MONTHLY,
        target_action="export_reports", next_date=utcnow() - timedelta(minutes=5),
    )
    db.add(schedule)
    db.commit()
    ids["schedule"] = schedule.id
    return ids


def _charged_customers(gateway):
    return {c.get("customer_id") for c in gateway.charges}


def _state(db, ids):
    from backend.app.core.tenant_context import system_context

    with system_context():
        db.expire_all()
        from backend.app.models.customization import AutomationSchedule

        trial = db.get(Subscription, ids["trial_sub"])
        renewal = db.get(Subscription, ids["renewal_sub"])
        case = db.get(DunningCase, ids["dunning_case"])
        schedule = db.get(AutomationSchedule, ids["schedule"])
        event = db.get(OutboxEvent, ids["outbox_event"])
        return {
            "trial_status": trial.status,
            "renewal_next_billing": renewal.next_billing_date,
            "renewal_invoices": db.scalar(select(func.count()).select_from(Invoice).where(Invoice.subscription_id == renewal.id)),
            "overdue_status": db.get(Invoice, ids["overdue_invoice"]).status,
            "reminders": db.get(Invoice, ids["reminder_invoice"]).reminder_count,
            "dunning_status": case.status,
            "dunning_attempts": db.scalar(select(func.count()).select_from(DunningAttempt).where(DunningAttempt.case_id == case.id)),
            "dunning_charged": (case.attempt_count or 0) > 0,
            "expenses": db.scalar(select(func.count()).select_from(Expense).where(Expense.organization_id == renewal.organization_id)),
            "outbox_status": event.status,
            "outbox_retries": event.retry_count or 0,
            "schedule_next": _aware(schedule.next_date),
        }


def _aware(value):
    """SQLite returns naive UTC datetimes; compare everything as aware UTC."""
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def _assert_untouched(before, after, ids):
    """Nothing the scheduler would start for this organization happened."""
    assert after["trial_status"] == SubscriptionStatus.TRIALING
    assert after["renewal_next_billing"] == before["renewal_next_billing"]
    assert after["renewal_invoices"] == before["renewal_invoices"] == 0
    assert after["overdue_status"] == InvoiceStatus.SENT
    assert after["reminders"] == 0
    assert after["dunning_status"] == before["dunning_status"]
    assert after["dunning_attempts"] == before["dunning_attempts"]
    assert after["dunning_charged"] is False
    assert after["expenses"] == before["expenses"] == 0
    assert after["outbox_status"] == OutboxStatus.PENDING
    assert after["outbox_retries"] == 0
    assert after["schedule_next"] == before["schedule_next"]


def _assert_processed(after):
    """Everything due ran (existing ACTIVE behaviour)."""
    assert after["trial_status"] == SubscriptionStatus.ACTIVE
    assert after["renewal_next_billing"] > date.today()
    assert after["renewal_invoices"] >= 1
    assert after["overdue_status"] == InvoiceStatus.OVERDUE
    assert after["reminders"] == 1
    assert after["dunning_attempts"] >= 1
    assert after["dunning_charged"] is True
    assert after["expenses"] >= 1
    assert after["outbox_status"] == OutboxStatus.PUBLISHED
    assert after["schedule_next"] > datetime.now(timezone.utc)


# --- A: ACTIVE organizations behave as before --------------------------------------------------------


def test_new_organizations_are_active_and_not_paused(db, tenant):
    db.refresh(tenant.organization)
    assert tenant.organization.status == OrganizationStatus.ACTIVE
    assert tenant.organization.jobs_paused is False
    assert org_lifecycle.automation_allowed(db, tenant.organization.id) is True


def test_active_org_processed_normally_next_to_inactive_one(db, tenant, gateway, outbox_seen):
    active = _seed_due_work(db, tenant)
    other = _second_tenant(db)
    frozen = _seed_due_work(db, other)
    _set_org(other.organization.id, status=OrganizationStatus.SUSPENDED)
    frozen_before = _state(db, frozen)

    counts = run_billing_jobs(db, today=date.today())

    after_active = _state(db, active)
    _assert_processed(after_active)
    assert {active["trial_customer"], active["dunning_customer"]} <= _charged_customers(gateway)
    assert active["outbox_event"] in outbox_seen

    _assert_untouched(frozen_before, _state(db, frozen), frozen)
    assert not ({frozen["trial_customer"], frozen["dunning_customer"]} & _charged_customers(gateway))
    assert frozen["outbox_event"] not in outbox_seen
    assert counts["skipped_org_inactive"] >= 1
    assert counts["errors"] == 0


def test_active_org_alone_processed_exactly_as_before(db, tenant, gateway, outbox_seen):
    # (skipped_org_inactive is run-wide; other tests' suspended organizations share this database)
    ids = _seed_due_work(db, tenant)
    counts = run_billing_jobs(db, today=date.today())
    _assert_processed(_state(db, ids))
    assert {ids["trial_customer"], ids["dunning_customer"]} <= _charged_customers(gateway)
    assert ids["outbox_event"] in outbox_seen
    assert counts["errors"] == 0


# --- B / C: inactive or paused organizations start no billing work ---------------------------------------


@pytest.mark.parametrize("status", INACTIVE, ids=[s.value for s in INACTIVE])
def test_inactive_org_gets_no_billing_work(db, tenant, gateway, outbox_seen, status):
    ids = _seed_due_work(db, tenant)
    _set_org(tenant.organization.id, status=status)
    before = _state(db, ids)

    counts = run_billing_jobs(db, today=date.today())

    _assert_untouched(before, _state(db, ids), ids)
    assert gateway.charges == []
    assert outbox_seen == []
    assert counts["skipped_org_inactive"] >= 1
    assert counts["renewals"] == counts["trials_converted"] == counts["marked_overdue"] == 0
    assert counts["reminders_sent"] == counts["dunning_recovered"] == counts["recurring_expenses_processed"] == 0


def test_jobs_paused_active_org_gets_no_billing_work(db, tenant, gateway, outbox_seen):
    ids = _seed_due_work(db, tenant)
    _set_org(tenant.organization.id, jobs_paused=True)
    before = _state(db, ids)

    counts = run_billing_jobs(db, today=date.today())

    _assert_untouched(before, _state(db, ids), ids)
    assert gateway.charges == []
    assert outbox_seen == []
    assert counts["skipped_org_inactive"] >= 1


def test_paused_work_resumes_when_unpaused(db, tenant, gateway, outbox_seen):
    """Skipped work is left due, not consumed: it runs on the first run after unpausing."""
    ids = _seed_due_work(db, tenant)
    _set_org(tenant.organization.id, jobs_paused=True)
    run_billing_jobs(db, today=date.today())
    _set_org(tenant.organization.id, jobs_paused=False)

    run_billing_jobs(db, today=date.today())
    _assert_processed(_state(db, ids))


def test_scheduled_plan_change_not_applied_for_suspended_org(client, db, tenant):
    from backend.app.models.proration import SubscriptionChange, SubscriptionChangeStatus

    def schedule_change(t):
        customer = t.customer()
        _, plan1 = t.product_with_plan(unit_amount="1000.00")
        _, plan2 = t.product_with_plan(unit_amount="2000.00")
        sub = client.post("/api/v1/subscriptions", json={"customer_id": customer.id, "plan_id": plan1.id, "quantity": 1},
                          headers=t.headers()).json()
        change = client.post(f"/api/v1/subscriptions/{sub['id']}/changes",
                             json={"target_plan_id": plan2.id, "effective_type": "end_of_term"}, headers=t.headers())
        assert change.status_code == 201, change.text
        return change.json()["id"], date.fromisoformat(change.json()["effective_date"])

    active_change, effective = schedule_change(tenant)
    other = _second_tenant(db)
    frozen_change, _ = schedule_change(other)
    _set_org(other.organization.id, status=OrganizationStatus.SUSPENDED)

    run_billing_jobs(db, today=effective)

    from backend.app.core.tenant_context import system_context

    with system_context():
        db.expire_all()
        assert db.get(SubscriptionChange, active_change).status == SubscriptionChangeStatus.APPLIED
        assert db.get(SubscriptionChange, frozen_change).status == SubscriptionChangeStatus.SCHEDULED


# --- D: the check is made inside the work item's own transaction -------------------------------------------


def test_check_reads_the_database_not_a_stale_identity_map(db, tenant):
    org = db.get(Organization, tenant.organization.id)
    assert org.status == OrganizationStatus.ACTIVE  # cached in this session
    _set_org(org.id, status=OrganizationStatus.SUSPENDED)
    assert org.status == OrganizationStatus.ACTIVE  # the cached object is stale ...
    assert org_lifecycle.automation_allowed(db, org.id) is False  # ... the check is not


def test_suspension_after_the_run_started_stops_later_renewals(db, tenant, gateway, monkeypatch):
    """Candidates are selected at the start of the run; a suspension committed while the run is
    in progress must stop the renewal that has not been billed yet."""
    ids = _seed_due_work(db, tenant)
    real_load = scheduler._load_subscription
    suspended = {"done": False}

    def load_then_suspend(session, subscription_id):
        if subscription_id == ids["renewal_sub"] and not suspended["done"]:
            _set_org(tenant.organization.id, status=OrganizationStatus.SUSPENDED)
            suspended["done"] = True
        return real_load(session, subscription_id)

    monkeypatch.setattr(scheduler, "_load_subscription", load_then_suspend)
    counts = run_billing_jobs(db, today=date.today())

    assert suspended["done"]
    after = _state(db, ids)
    assert after["renewal_invoices"] == 0
    assert after["overdue_status"] == InvoiceStatus.SENT  # later steps see it too
    assert counts["skipped_org_inactive"] >= 1


def test_suspension_after_usage_finalization_still_stops_the_renewal(db, tenant, gateway, monkeypatch):
    """Usage finalization commits before the renewal (releasing the lock); the renewal re-checks
    afterwards. On PostgreSQL a suspension cannot land before that commit - the stand-in below
    commits exactly like meter_service._finalize_usage does."""
    ids = _seed_due_work(db, tenant)

    def finalize_then_suspend(session, sub):
        if sub.id == ids["renewal_sub"]:
            session.commit()
            _set_org(tenant.organization.id, status=OrganizationStatus.SUSPENDED)
        return False

    monkeypatch.setattr(scheduler, "_finalize_usage_before_renewal", finalize_then_suspend)
    run_billing_jobs(db, today=date.today())
    assert _state(db, ids)["renewal_invoices"] == 0


def test_dunning_guard_checked_per_case_before_charging(db, tenant, gateway):
    ids = _seed_due_work(db, tenant)
    from backend.app.core.tenant_context import system_context

    with system_context():
        attempts_before = db.scalar(
            select(func.count()).select_from(DunningAttempt).where(DunningAttempt.case_id == ids["dunning_case"])
        )
    calls = []

    def guard():
        calls.append(1)
        return False

    res = dunning_service.execute_dunning_retries(db, tenant.organization.id, guard=guard)
    db.commit()
    assert calls, "the guard must be consulted before a due case is processed"
    assert gateway.charges == []
    assert res["recovered_count"] == 0
    with system_context():
        db.expire_all()
        attempts_after = db.scalar(
            select(func.count()).select_from(DunningAttempt).where(DunningAttempt.case_id == ids["dunning_case"])
        )
        assert attempts_after == attempts_before
        assert db.get(DunningCase, ids["dunning_case"]).attempt_count == 0


def test_services_without_a_guard_are_unchanged(db, tenant, gateway):
    """API callers (retry now, trial evaluation) pass no guard: behaviour as before, even for a
    suspended organization - tenant-initiated actions are out of scope for phase 1."""
    ids = _seed_due_work(db, tenant)
    _set_org(tenant.organization.id, status=OrganizationStatus.SUSPENDED)
    res = dunning_service.execute_dunning_retries(db, tenant.organization.id)
    db.commit()
    assert ids["dunning_customer"] in _charged_customers(gateway)
    assert res["recovered_count"] == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="row locks need PostgreSQL (TEST_DATABASE_URL)")
def test_postgres_status_change_waits_for_the_billing_transaction(tenant):
    """While a billing transaction holds the check's lock, a concurrent suspension cannot commit;
    once it has committed, the next check sees it."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    org_id = tenant.organization.id
    billing = SessionLocal()
    suspender = SessionLocal()
    try:
        assert org_lifecycle.automation_allowed(billing, org_id) is True  # lock held from here
        suspender.execute(text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(OperationalError):
            suspender.execute(update(Organization).where(Organization.id == org_id).values(status=OrganizationStatus.SUSPENDED))
        suspender.rollback()
        # Ordinary tenant inserts that reference the organization are not blocked by the lock.
        suspender.execute(text("SET LOCAL lock_timeout = '300ms'"))
        suspender.add(
            OutboxEvent(
                organization_id=org_id, event_type="lock.probe", aggregate_type="t", aggregate_id="t",
                payload={}, status=OutboxStatus.PUBLISHED,
            )
        )
        suspender.flush()  # FK check takes FOR KEY SHARE on the organization: not blocked
        suspender.rollback()
        billing.commit()  # billing work done: lock released
        suspender.execute(update(Organization).where(Organization.id == org_id).values(status=OrganizationStatus.SUSPENDED))
        suspender.commit()
        assert org_lifecycle.automation_allowed(billing, org_id) is False
        billing.rollback()
    finally:
        billing.close()
        suspender.close()


# --- webhooks and isolation ---------------------------------------------------------------------------------


def test_payment_webhook_still_recorded_for_suspended_org(client, db, tenant, monkeypatch):
    secret = "lifecycle_webhook_secret"
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", secret)
    inv = tenant.invoice(tenant.customer(), amount="800.00")
    payment = Payment(
        organization_id=tenant.organization.id, payment_number=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        customer_id=inv.customer_id, amount=Decimal("800.00"), currency="INR", method=PaymentMethod.RAZORPAY,
        gateway=PaymentGateway.RAZORPAY, status=PaymentStatus.PENDING,
        gateway_order_id=f"order_{uuid.uuid4().hex[:14]}",
        gateway_payload={"notes": {"invoice_id": inv.id, "organization_id": tenant.organization.id}},
    )
    db.add(payment)
    db.commit()
    _set_org(tenant.organization.id, status=OrganizationStatus.SUSPENDED)

    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_captured_suspended", "order_id": payment.gateway_order_id, "amount": 80000, "currency": "INR"}}}}).encode()
    headers = {"Content-Type": "application/json", "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex}",
               "X-Razorpay-Signature": hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}
    resp = client.post("/api/v1/webhooks/razorpay", content=body, headers=headers)

    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.get(Payment, payment.id).status == PaymentStatus.SUCCEEDED
    assert db.get(Invoice, inv.id).status == InvoiceStatus.PAID


def test_one_orgs_state_never_affects_another(db, tenant):
    other = _second_tenant(db)
    _set_org(other.organization.id, status=OrganizationStatus.SUSPENDED, jobs_paused=True)
    assert org_lifecycle.automation_allowed(db, tenant.organization.id) is True
    assert org_lifecycle.automation_allowed(db, other.organization.id) is False
    assert org_lifecycle.automation_allowed(db, str(uuid.uuid4())) is False  # unknown organization
    assert org_lifecycle.automation_allowed(db, None) is False

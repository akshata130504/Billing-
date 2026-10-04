"""Organization-timezone correctness (Area 5) and scheduler alert hooks (Area 17).

Business days (overdue marking, renewals, recurring expenses, usage periods, automation
schedules, collections) follow the organization's timezone; instants stay in UTC. The clock
is frozen by monkeypatching ``timezones.utc_now`` - the single clock every helper reads.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from backend.app.core.tenant_context import system_context, tenant_context
from backend.app.models import Invoice, InvoiceStatus, Subscription, SubscriptionStatus
from backend.app.services import scheduler, timezones

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")
NY = ZoneInfo("America/New_York")

# 2026-03-31 20:00 UTC == 2026-04-01 01:30 IST == 2026-03-31 16:00 EDT.
FROZEN = datetime(2026, 3, 31, 20, 0, tzinfo=UTC)


@pytest.fixture()
def frozen(monkeypatch):
    def _freeze(at: datetime = FROZEN):
        monkeypatch.setattr(timezones, "utc_now", lambda: at)
        return at

    _freeze()
    return _freeze


def _org(name):
    return SimpleNamespace(timezone=name)


# --- helper correctness --------------------------------------------------------------------


def test_org_today_utc_kolkata_new_york_across_month_boundary(frozen):
    assert timezones.org_today("UTC") == date(2026, 3, 31)
    assert timezones.org_today(_org("Asia/Kolkata")) == date(2026, 4, 1)
    assert timezones.org_today(NY) == date(2026, 3, 31)
    now = timezones.org_now(_org("Asia/Kolkata"))
    assert now.tzinfo is not None and (now.hour, now.minute) == (1, 30)
    assert now == FROZEN  # same instant, different wall clock


def test_org_today_just_before_and_after_local_midnight(frozen):
    frozen(datetime(2026, 3, 31, 18, 29, 59, tzinfo=UTC))
    assert timezones.org_today("Asia/Kolkata") == date(2026, 3, 31)
    frozen(datetime(2026, 3, 31, 18, 30, tzinfo=UTC))
    assert timezones.org_today("Asia/Kolkata") == date(2026, 4, 1)


def test_resolve_tz_fallbacks():
    default = ZoneInfo(timezones.DEFAULT_TIMEZONE)
    assert timezones.resolve_tz(None) == default
    assert timezones.resolve_tz(_org(None)) == default
    assert timezones.resolve_tz(_org("Mars/Olympus_Mons")) == default
    assert timezones.resolve_tz("not a zone") == default
    assert timezones.resolve_tz("America/New_York") == NY
    assert timezones.resolve_tz(UTC) is UTC


def test_resolve_tz_falls_back_to_utc_when_default_is_unavailable(monkeypatch):
    monkeypatch.setattr(timezones, "DEFAULT_TIMEZONE", "Invalid/Zone")
    assert timezones.resolve_tz(_org("Bogus/Zone")) == UTC


def test_day_bounds_utc_kolkata():
    start, end = timezones.day_bounds_utc(_org("Asia/Kolkata"), date(2026, 4, 1))
    assert start == datetime(2026, 3, 31, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 4, 1, 18, 30, tzinfo=UTC)
    assert start <= FROZEN < end


def test_day_bounds_across_spring_forward_new_york():
    # 2026-03-08: clocks jump 02:00 EST -> 03:00 EDT, the local day is 23 hours long.
    start, end = timezones.day_bounds_utc(NY, date(2026, 3, 8))
    assert start == datetime(2026, 3, 8, 5, 0, tzinfo=UTC)  # 00:00 EST
    assert end == datetime(2026, 3, 9, 4, 0, tzinfo=UTC)  # 00:00 EDT
    assert end - start == timedelta(hours=23)


def test_day_bounds_across_fall_back_new_york():
    # 2026-11-01: clocks fall back 02:00 EDT -> 01:00 EST, the local day is 25 hours long.
    start, end = timezones.day_bounds_utc(NY, date(2026, 11, 1))
    assert start == datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 2, 5, 0, tzinfo=UTC)
    assert end - start == timedelta(hours=25)


def test_org_today_on_dst_days_new_york(frozen):
    frozen(datetime(2026, 3, 8, 4, 59, tzinfo=UTC))  # 23:59 EST on the 7th
    assert timezones.org_today(NY) == date(2026, 3, 7)
    frozen(datetime(2026, 3, 9, 3, 59, tzinfo=UTC))  # 23:59 EDT on the 8th
    assert timezones.org_today(NY) == date(2026, 3, 8)
    frozen(datetime(2026, 11, 2, 4, 59, tzinfo=UTC))  # 23:59 EST on 1 Nov
    assert timezones.org_today(NY) == date(2026, 11, 1)
    frozen(datetime(2026, 11, 2, 5, 0, tzinfo=UTC))
    assert timezones.org_today(NY) == date(2026, 11, 2)


def test_month_bounds_utc_and_local_date():
    start, end = timezones.month_bounds_utc("Asia/Kolkata", date(2026, 4, 17))
    assert start == datetime(2026, 3, 31, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 4, 30, 18, 30, tzinfo=UTC)
    # December rolls into the next year; March in New York spans the DST change.
    assert timezones.month_bounds_utc("UTC", date(2026, 12, 5))[1] == datetime(2027, 1, 1, tzinfo=UTC)
    ny_start, ny_end = timezones.month_bounds_utc(NY, date(2026, 3, 1))
    assert (ny_start, ny_end) == (datetime(2026, 3, 1, 5, tzinfo=UTC), datetime(2026, 4, 1, 4, tzinfo=UTC))
    # Naive instants are UTC.
    assert timezones.local_date(datetime(2026, 3, 31, 20, 0), "Asia/Kolkata") == date(2026, 4, 1)
    assert timezones.local_date(FROZEN, NY) == date(2026, 3, 31)


# --- scenario tests: files owned by this area ------------------------------------------------


def _tenant(db, tz_name):
    from backend.tests.conftest import Tenant

    t = Tenant(db, uuid.uuid4().hex[:8])
    t.organization.timezone = tz_name
    db.commit()
    return t


def _open_invoice(db, tenant, due):
    customer = tenant.customer()
    inv = Invoice(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        invoice_number=f"INV-TZ-{uuid.uuid4().hex[:6]}",
        status=InvoiceStatus.SENT,
        issue_date=due - timedelta(days=30),
        due_date=due,
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
        amount_paid=Decimal("0.00"),
        amount_due=Decimal("100.00"),
        public_token=uuid.uuid4().hex,
    )
    db.add(inv)
    db.commit()
    return inv


def test_scheduler_overdue_marking_uses_org_local_date(client, db, frozen):
    kolkata = _tenant(db, "Asia/Kolkata")
    new_york = _tenant(db, "America/New_York")
    inv_in = _open_invoice(db, kolkata, date(2026, 3, 31))
    inv_ny = _open_invoice(db, new_york, date(2026, 3, 31))

    scheduler.run_billing_jobs(db)

    db.refresh(inv_in)
    db.refresh(inv_ny)
    assert inv_in.status == InvoiceStatus.OVERDUE  # already 1 April in Kolkata
    assert inv_ny.status == InvoiceStatus.SENT  # still 31 March (due today) in New York


def test_scheduler_renewal_due_check_uses_org_local_date(client, db, frozen):
    results = {}
    for tz_name in ("Asia/Kolkata", "America/New_York"):
        t = _tenant(db, tz_name)
        customer = t.customer()
        _, plan = t.product_with_plan(unit_amount="500.00")
        sub = Subscription(
            organization_id=t.organization.id,
            customer_id=customer.id,
            plan_id=plan.id,
            quantity=1,
            status=SubscriptionStatus.ACTIVE,
            start_date=date(2026, 3, 1),
            current_period_start=date(2026, 3, 1),
            current_period_end=date(2026, 4, 1),
            next_billing_date=date(2026, 4, 1),
            subscription_number=f"SUB-TZ-{uuid.uuid4().hex[:6]}",
        )
        db.add(sub)
        db.commit()
        results[tz_name] = sub

    scheduler.run_billing_jobs(db)

    for sub in results.values():
        db.refresh(sub)
    assert results["Asia/Kolkata"].next_billing_date > date(2026, 4, 1)  # renewed on its 1 April
    assert results["America/New_York"].next_billing_date == date(2026, 4, 1)  # not due yet


def test_scheduler_recurring_expenses_use_org_local_date(client, db, frozen):
    from backend.app.models.expenses import Expense, RecurringExpense, RecurringExpenseFrequency, RecurringExpenseStatus

    recs = {}
    for tz_name in ("Asia/Kolkata", "America/New_York"):
        t = _tenant(db, tz_name)
        rec = RecurringExpense(
            organization_id=t.organization.id,
            name=f"Hosting {tz_name}",
            category="Infrastructure",
            amount=Decimal("10.00"),
            currency="USD",
            frequency=RecurringExpenseFrequency.MONTHLY,
            start_date=date(2026, 4, 1),
            next_run=date(2026, 4, 1),
            never_ends=True,
            status=RecurringExpenseStatus.ACTIVE,
        )
        db.add(rec)
        db.commit()
        recs[tz_name] = rec

    scheduler.run_billing_jobs(db)

    def expense_count(rec):
        with tenant_context(rec.organization_id):
            return len(db.scalars(select(Expense).where(Expense.organization_id == rec.organization_id)).all())

    assert expense_count(recs["Asia/Kolkata"]) == 1
    assert expense_count(recs["America/New_York"]) == 0
    db.refresh(recs["America/New_York"])
    assert recs["America/New_York"].next_run == date(2026, 4, 1)


def test_process_due_recurring_expenses_defaults_to_each_orgs_local_date(client, db, frozen):
    from backend.app.models.expenses import RecurringExpense, RecurringExpenseFrequency, RecurringExpenseStatus
    from backend.app.services.expense_service import process_due_recurring_expenses

    # the scheduler runs this under system_context() (run_billing_jobs)
    with system_context():
        t = _tenant(db, "America/New_York")
        rec = RecurringExpense(
            organization_id=t.organization.id,
            name="NY rent",
            category="Rent",
            amount=Decimal("5.00"),
            currency="USD",
            frequency=RecurringExpenseFrequency.MONTHLY,
            start_date=date(2026, 4, 1),
            next_run=date(2026, 4, 1),
            never_ends=True,
            status=RecurringExpenseStatus.ACTIVE,
        )
        db.add(rec)
        db.commit()
        assert process_due_recurring_expenses(db, organization_id=t.organization.id) == 0
        frozen(datetime(2026, 4, 1, 4, 0, tzinfo=UTC))  # 00:00 EDT on 1 April
        assert process_due_recurring_expenses(db, organization_id=t.organization.id) == 1


def test_collections_status_uses_org_local_date(client, db, frozen):
    from backend.app.models import CollectionStatus
    from backend.app.services import collection_service

    inv_in = _open_invoice(db, _tenant(db, "Asia/Kolkata"), date(2026, 3, 31))
    inv_ny = _open_invoice(db, _tenant(db, "America/New_York"), date(2026, 3, 31))
    assert collection_service.effective_status(inv_in, None) == CollectionStatus.OVERDUE
    assert collection_service.effective_status(inv_ny, None) == CollectionStatus.DUE_SOON
    data = collection_service.serialize_collection_invoice(inv_in, None)
    assert data["days_overdue"] == 1


def test_usage_period_boundaries_follow_org_timezone(client, db):
    from backend.app.models.meters import UsageEvent, UsageMeter
    from backend.app.services import meter_service
    # billing runs usage aggregation from the scheduler under system_context()
    with system_context():
        t = _tenant(db, "Asia/Kolkata")
        customer = t.customer()
        _, plan = t.product_with_plan()
        sub = Subscription(
            organization_id=t.organization.id,
            customer_id=customer.id,
            plan_id=plan.id,
            quantity=1,
            status=SubscriptionStatus.ACTIVE,
            start_date=date(2026, 3, 1),
            current_period_start=date(2026, 4, 1),
            current_period_end=date(2026, 5, 1),
            next_billing_date=date(2026, 5, 1),
            subscription_number=f"SUB-TZ-{uuid.uuid4().hex[:6]}",
        )
        meter = UsageMeter(organization_id=t.organization.id, code=f"m{uuid.uuid4().hex[:6]}", name="Calls", unit_name="call")
        db.add_all([sub, meter])
        db.flush()
        # 20:00 UTC on 31 March is 01:30 IST on 1 April: it belongs to the April period.
        db.add(
            UsageEvent(
                organization_id=t.organization.id,
                meter_id=meter.id,
                customer_id=customer.id,
                subscription_id=sub.id,
                quantity=Decimal("7"),
                timestamp=FROZEN,
                idempotency_key=uuid.uuid4().hex,
            )
        )
        db.commit()

        assert meter_service.subscription_has_usage(db, sub.id, date(2026, 4, 1), date(2026, 5, 1))
        assert not meter_service.subscription_has_usage(db, sub.id, date(2026, 3, 1), date(2026, 4, 1))
        qty = meter_service.aggregate_subscription_usage(
            db, t.organization.id, meter.id, sub.id, date(2026, 4, 1), date(2026, 5, 1)
        )
        assert qty == Decimal("7")


def test_automation_schedule_next_run_uses_org_timezone_and_dst():
    from backend.app.models.customization import ScheduleFrequency
    from backend.app.services.customization_service import compute_next_schedule_date

    # Daily 09:00 in New York keeps 09:00 local across spring-forward (14:00 UTC -> 13:00 UTC).
    before = datetime(2026, 3, 7, 14, 0, tzinfo=UTC)
    nxt = compute_next_schedule_date(ScheduleFrequency.DAILY, before, tz=NY)
    assert nxt == datetime(2026, 3, 8, 13, 0, tzinfo=UTC)
    assert nxt.astimezone(NY).hour == 9
    # ... and across fall-back (13:00 UTC -> 14:00 UTC).
    nxt = compute_next_schedule_date(ScheduleFrequency.DAILY, datetime(2026, 10, 31, 13, 0, tzinfo=UTC), tz=NY)
    assert nxt == datetime(2026, 11, 1, 14, 0, tzinfo=UTC)
    # Cron fields are local wall-clock time: 09:00 IST == 03:30 UTC.
    nxt = compute_next_schedule_date(ScheduleFrequency.DAILY, FROZEN, "0 9 * * *", tz=IST)
    assert nxt == datetime(2026, 4, 1, 3, 30, tzinfo=UTC)
    # Monthly rollover follows the local date: 20:00 UTC on 31 Jan is 1 Feb in Kolkata.
    nxt = compute_next_schedule_date(ScheduleFrequency.MONTHLY, datetime(2026, 1, 31, 20, 0, tzinfo=UTC), tz=IST)
    assert nxt == datetime(2026, 2, 28, 20, 0, tzinfo=UTC)  # 1 March 01:30 IST
    # Without a zone the old UTC behaviour is unchanged.
    assert compute_next_schedule_date(
        ScheduleFrequency.MONTHLY, datetime(2026, 1, 31, 9, 0, tzinfo=UTC)
    ) == datetime(2026, 2, 28, 9, 0, tzinfo=UTC)


def test_create_schedule_evaluates_cron_in_org_timezone(client, db):
    from backend.app.schemas.customization import AutomationScheduleCreate
    from backend.app.services import customization_service

    t = _tenant(db, "Asia/Kolkata")
    schedule = customization_service.create_schedule(
        db,
        t.organization.id,
        AutomationScheduleCreate(name="Morning report", target_action="export_reports", cron_expression="0 9 * * *"),
    )
    db.commit()
    nd = timezones.to_utc(schedule.next_date)
    assert (nd.hour, nd.minute) == (3, 30)
    assert nd.astimezone(IST).hour == 9


# --- Area 17: scheduler alert hooks ------------------------------------------------------------


@pytest.fixture()
def captured_alerts(monkeypatch):
    from backend.app.core import alerts

    sent = []

    def fake_send_alert(event, summary, details=None, severity="error", *, dedup_key=None):
        sent.append({"event": event, "summary": summary, "details": dict(details or {}), "severity": severity, "dedup_key": dedup_key})
        return True

    monkeypatch.setattr(alerts, "send_alert", fake_send_alert)
    return sent


def test_scheduler_step_failure_sends_alert(client, db, monkeypatch, captured_alerts):
    def boom(_db):
        raise RuntimeError("password=hunter2 should never leave the process")

    monkeypatch.setattr(scheduler, "_process_due_jobs", boom)
    counts = scheduler.run_billing_jobs(db)
    assert counts["errors"] >= 1
    step_alerts = [a for a in captured_alerts if a["event"] == "scheduler.step_failed"]
    hit = [a for a in step_alerts if a["details"].get("step") == "process_due_jobs"]
    assert hit, captured_alerts
    assert hit[0]["details"]["error_type"] == "RuntimeError"
    assert hit[0]["dedup_key"] == "scheduler.step_failed:process_due_jobs"
    assert "hunter2" not in repr(hit[0])  # only the exception type is sent


def test_scheduler_per_org_step_failure_alert_carries_org_id(client, db, monkeypatch, captured_alerts):
    from backend.app.services import expense_service

    t = _tenant(db, "UTC")

    def boom(db_, *, today=None, organization_id=None):
        raise ValueError("nope")

    monkeypatch.setattr(expense_service, "process_due_recurring_expenses", boom)
    scheduler.run_billing_jobs(db)
    orgs = {a["details"].get("organization_id") for a in captured_alerts if a["details"].get("step") == "recurring_expenses"}
    assert t.organization.id in orgs


def test_scheduler_run_failure_sends_alert_and_reraises(client, db, monkeypatch, captured_alerts):
    def explode(_db, _today):
        raise RuntimeError("db gone")

    monkeypatch.setattr(scheduler, "_run_billing_jobs_unlocked", explode)
    with pytest.raises(RuntimeError):
        scheduler.run_billing_jobs(db)
    run_alerts = [a for a in captured_alerts if a["event"] == "scheduler.run_failed"]
    assert len(run_alerts) == 1
    assert run_alerts[0]["details"] == {"job": "billing_jobs", "phase": "run", "error_type": "RuntimeError"}


def test_scheduler_alert_errors_never_break_the_run(client, db, monkeypatch):
    from backend.app.core import alerts

    def broken_alert(*a, **k):
        raise RuntimeError("alerting down")

    monkeypatch.setattr(alerts, "send_alert", broken_alert)
    monkeypatch.setattr(scheduler, "_process_due_jobs", lambda _db: (_ for _ in ()).throw(RuntimeError("x")))
    counts = scheduler.run_billing_jobs(db)
    assert counts["errors"] >= 1

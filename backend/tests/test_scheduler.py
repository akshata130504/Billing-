"""Characterization tests for background billing jobs and scheduler operations."""
from datetime import date, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select

from backend.app.models import (
    Invoice,
    InvoiceStatus,
    Subscription,
    SubscriptionStatus,
)
from backend.app.services.scheduler import run_billing_jobs


def test_scheduler_converts_ended_trial(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1000.00", trial_days=14)

    # Create trialing subscription that ended yesterday
    sub = Subscription(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        plan_id=plan.id,
        quantity=1,
        status=SubscriptionStatus.TRIALING,
        start_date=date.today() - timedelta(days=15),
        trial_end=date.today() - timedelta(days=1),
        current_period_start=date.today() - timedelta(days=15),
        current_period_end=date.today() - timedelta(days=1),
        subscription_number="SUB-TRIAL-001",
    )
    db.add(sub)
    db.commit()

    counts = run_billing_jobs(db, today=date.today())
    assert counts["trials_converted"] >= 1

    db.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.next_billing_date is not None


def test_scheduler_renews_active_subscription(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="2000.00", interval="monthly")

    # Subscription due for renewal today
    sub = Subscription(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        plan_id=plan.id,
        quantity=1,
        status=SubscriptionStatus.ACTIVE,
        start_date=date.today() - timedelta(days=30),
        current_period_start=date.today() - timedelta(days=30),
        current_period_end=date.today(),
        next_billing_date=date.today(),
        subscription_number="SUB-RENEW-001",
    )
    db.add(sub)
    db.commit()

    counts = run_billing_jobs(db, today=date.today())
    assert counts["renewals"] >= 1

    db.refresh(sub)
    assert sub.next_billing_date > date.today()


def test_scheduler_marks_overdue_invoices(client, tenant, auth_headers, db):
    customer = tenant.customer()
    inv = Invoice(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        invoice_number="INV-OVERDUE-001",
        status=InvoiceStatus.SENT,
        issue_date=date.today() - timedelta(days=40),
        due_date=date.today() - timedelta(days=10),
        total=Decimal("500.00"),
        amount_due=Decimal("500.00"),
        public_token="token-overdue-1",
    )
    db.add(inv)
    db.commit()

    counts = run_billing_jobs(db, today=date.today())
    assert counts["marked_overdue"] >= 1

    db.refresh(inv)
    assert inv.status == InvoiceStatus.OVERDUE


def test_admin_run_jobs_endpoint(client, tenant, auth_headers, db):
    # The HTTP trigger was removed (cross-tenant); the endpoint must stay gone and the
    # counts contract lives on run_billing_jobs itself.
    resp = client.post("/api/v1/admin/jobs/run", headers=auth_headers)
    assert resp.status_code in (404, 405)
    data = run_billing_jobs(db)
    assert "renewals" in data
    assert "trials_converted" in data
    assert "marked_overdue" in data
    assert "reminders_sent" in data
    assert "recurring_expenses_processed" in data


def test_scheduler_processes_due_recurring_expenses(client, tenant, auth_headers, db):
    """Ensure run_billing_jobs executes due recurring expenses."""
    from backend.app.models.expenses import Expense, RecurringExpense, RecurringExpenseFrequency, RecurringExpenseStatus

    today = date.today()
    rec = RecurringExpense(
        organization_id=tenant.organization.id,
        name="Scheduled Server Backup",
        category="Infrastructure",
        amount=Decimal("80.00"),
        currency="USD",
        frequency=RecurringExpenseFrequency.MONTHLY,
        start_date=today,
        next_run=today,
        never_ends=True,
        status=RecurringExpenseStatus.ACTIVE,
    )
    db.add(rec)
    db.commit()

    counts = run_billing_jobs(db, today=today)
    assert counts.get("recurring_expenses_processed", 0) >= 1

    exp = db.scalars(
        select(Expense).where(
            Expense.organization_id == tenant.organization.id,
            Expense.name == "Scheduled Server Backup",
        )
    ).first()
    assert exp is not None
    assert exp.amount == Decimal("80.00")



# --- production-readiness regressions ---------------------------------------------------------


def _api_sub(client, auth_headers, customer, plan):
    resp = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_end_of_term_change_applies_before_renewal_invoice(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    _, plan2 = tenant.product_with_plan(unit_amount="4000.00")
    sub_id = _api_sub(client, auth_headers, customer, plan1)
    resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        headers=auth_headers,
        json={"target_plan_id": plan2.id, "effective_type": "end_of_term"},
    )
    assert resp.status_code == 201, resp.text
    sub = db.get(Subscription, sub_id)
    period_end = sub.current_period_end

    run_billing_jobs(db, today=period_end)
    db.refresh(sub)
    assert sub.plan_id == plan2.id
    renewal = db.scalars(
        select(Invoice).where(Invoice.subscription_id == sub_id, Invoice.period_start == period_end)
    ).one()
    # The renewal is built AFTER the scheduled change, so it bills the new plan.
    assert renewal.subtotal == Decimal("4000.00")


def test_run_records_heartbeat(client, tenant, auth_headers, db):
    from backend.app.services.scheduler import get_scheduler_heartbeat

    counts = run_billing_jobs(db, today=date.today())
    hb = get_scheduler_heartbeat(db)
    assert hb is not None
    assert hb["last_finished_at"] is not None
    assert hb["last_error_count"] == counts["errors"]
    assert hb["total_runs"] >= 1
    assert "renewals" in hb["last_counts"]


def test_renewal_finalizes_usage_of_ending_period(client, tenant, auth_headers, db):
    from backend.app.models.meters import UsageAggregate

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="100.00")
    sub_id = _api_sub(client, auth_headers, customer, plan)
    client.post(
        "/api/v1/meters",
        json={"code": "sched_units", "name": "Sched Units", "unit_name": "unit", "aggregation_type": "sum", "unit_price": "2.00"},
        headers=auth_headers,
    )
    r = client.post(
        "/api/v1/meters/events",
        json={"meter_code": "sched_units", "customer_id": customer.id, "subscription_id": sub_id, "quantity": 7, "idempotency_key": "s-1"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    sub = db.get(Subscription, sub_id)
    period_start, period_end = sub.current_period_start, sub.current_period_end

    counts = run_billing_jobs(db, today=period_end)
    assert counts["usage_finalized"] >= 1
    agg = db.scalars(
        select(UsageAggregate).where(UsageAggregate.subscription_id == sub_id, UsageAggregate.period_start == period_start)
    ).one()
    assert agg.total_quantity == Decimal("7")
    assert agg.rated_amount == Decimal("14.00")
    db.refresh(sub)
    assert sub.current_period_start == period_end  # renewed after finalizing

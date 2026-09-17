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


def test_admin_run_jobs_endpoint(client, tenant, auth_headers):
    resp = client.post("/api/v1/admin/jobs/run", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
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


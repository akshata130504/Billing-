"""Tests for Expenses and Recurring Expenses persistence, CRUD, RBAC, batch import, and tenant isolation."""
from datetime import date
from decimal import Decimal
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.models import MemberRole


def test_create_expense_and_read(client: TestClient, tenant, auth_headers):
    customer = tenant.customer(display_name="Globex Corp")

    res = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={
            "name": "AWS Hosting Jan",
            "category": "Cloud Services",
            "date": date.today().isoformat(),
            "amount": 450.75,
            "currency": "USD",
            "billable": True,
            "customer_id": customer.id,
            "payment_method": "Corporate Card",
            "paid_by": "Engineering",
            "status": "recorded",
            "notes": "EC2 and S3 charges",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["name"] == "AWS Hosting Jan"
    assert data["category"] == "Cloud Services"
    assert Decimal(data["amount"]) == Decimal("450.75")
    assert data["currency"] == "USD"
    assert data["billable"] is True
    assert data["customer_id"] == customer.id
    assert data["customer_name"] == "Globex Corp"
    assert data["payment_method"] == "Corporate Card"

    # Read single
    get_res = client.get(f"/api/v1/expenses/{data['id']}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == data["id"]


def test_expense_list_filters_and_sorting(client: TestClient, tenant, auth_headers):
    client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={
            "name": "Flight Ticket",
            "category": "Travel",
            "date": date.today().isoformat(),
            "amount": 800.0,
            "billable": True,
        },
    )
    client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={
            "name": "Team Lunch",
            "category": "Meals",
            "date": date.today().isoformat(),
            "amount": 120.0,
            "billable": False,
        },
    )

    # Filter by category
    travel_res = client.get("/api/v1/expenses?category=Travel", headers=auth_headers)
    assert travel_res.status_code == 200
    travel_items = travel_res.json()
    assert len(travel_items) >= 1
    assert all(e["category"] == "Travel" for e in travel_items)

    # Filter by billable
    billable_res = client.get("/api/v1/expenses?billable=true", headers=auth_headers)
    assert billable_res.status_code == 200
    assert all(e["billable"] is True for e in billable_res.json())


def test_expense_update_and_delete(client: TestClient, tenant, auth_headers):
    exp = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={
            "name": "Old Monitor",
            "category": "Equipment",
            "date": date.today().isoformat(),
            "amount": 250.0,
        },
    ).json()

    # Update
    u_res = client.patch(
        f"/api/v1/expenses/{exp['id']}",
        headers=auth_headers,
        json={"name": "New 4K Monitor", "amount": 350.0},
    )
    assert u_res.status_code == 200
    assert u_res.json()["name"] == "New 4K Monitor"
    assert Decimal(u_res.json()["amount"]) == Decimal("350.00")

    # Delete
    d_res = client.delete(f"/api/v1/expenses/{exp['id']}", headers=auth_headers)
    assert d_res.status_code == 204

    # Verify 404
    assert client.get(f"/api/v1/expenses/{exp['id']}", headers=auth_headers).status_code == 404


def test_expense_batch_import(client: TestClient, tenant, auth_headers):
    batch_payload = {
        "expenses": [
            {
                "name": f"Imported Expense {i}",
                "category": "Software",
                "date": date.today().isoformat(),
                "amount": float(50 * i),
                "billable": False,
            }
            for i in range(1, 4)
        ]
    }
    res = client.post("/api/v1/expenses/batch", headers=auth_headers, json=batch_payload)
    assert res.status_code == 200
    assert res.json()["imported"] == 3


def test_expense_add_to_invoice(client: TestClient, tenant, auth_headers):
    exp = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={
            "name": "Billable Design Fee",
            "category": "Professional Services",
            "date": date.today().isoformat(),
            "amount": 500.0,
            "billable": True,
            "status": "recorded",
        },
    ).json()

    res = client.post(f"/api/v1/expenses/{exp['id']}/add-to-invoice", headers=auth_headers)
    assert res.status_code == 200
    updated = res.json()
    assert updated["status"] == "invoiced"
    assert updated["billable"] is True
    assert Decimal(updated["billable_amount"]) == Decimal("500.00")


def test_recurring_expense_lifecycle(client: TestClient, tenant, auth_headers):
    # Create recurring
    res = client.post(
        "/api/v1/expenses/recurring",
        headers=auth_headers,
        json={
            "name": "Figma Subscription",
            "category": "Software",
            "amount": 45.0,
            "currency": "USD",
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
            "never_ends": True,
            "status": "active",
        },
    )
    assert res.status_code == 201, res.text
    rec = res.json()
    assert rec["name"] == "Figma Subscription"
    assert rec["frequency"] == "monthly"
    assert rec["status"] == "active"

    # Toggle status
    toggle_res = client.post(f"/api/v1/expenses/recurring/{rec['id']}/toggle-status", headers=auth_headers)
    assert toggle_res.status_code == 200
    assert toggle_res.json()["status"] == "paused"

    # Recurring summary
    summ_res = client.get("/api/v1/expenses/recurring/summary", headers=auth_headers)
    assert summ_res.status_code == 200
    assert "active_profiles" in summ_res.json()

    # Delete recurring
    del_res = client.delete(f"/api/v1/expenses/recurring/{rec['id']}", headers=auth_headers)
    assert del_res.status_code == 204


def test_expense_tenant_isolation(client: TestClient, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other_tenant = Tenant(db, suffix=uuid.uuid4().hex[:6])
    other_headers = other_tenant.headers()

    e1 = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={
            "name": "Tenant 1 Confidential Expense",
            "category": "Other",
            "date": date.today().isoformat(),
            "amount": 999.0,
        },
    ).json()

    # Tenant 2 cannot see it
    assert client.get(f"/api/v1/expenses/{e1['id']}", headers=other_headers).status_code == 404

    # Tenant 2 cannot update it
    assert client.patch(f"/api/v1/expenses/{e1['id']}", headers=other_headers, json={"amount": 1.0}).status_code == 404

    # Tenant 2 cannot delete it
    assert client.delete(f"/api/v1/expenses/{e1['id']}", headers=other_headers).status_code == 404


def test_expense_rbac(client: TestClient, tenant):
    viewer_headers = tenant.headers_for_role(MemberRole.VIEWER)
    finance_headers = tenant.headers_for_role(MemberRole.FINANCE)
    admin_headers = tenant.headers_for_role(MemberRole.ADMIN)

    # Viewer cannot create
    v_res = client.post(
        "/api/v1/expenses",
        headers=viewer_headers,
        json={
            "name": "Unauthorized Expense",
            "category": "Other",
            "date": date.today().isoformat(),
            "amount": 100.0,
        },
    )
    assert v_res.status_code == 403

    # Finance can create
    f_res = client.post(
        "/api/v1/expenses",
        headers=finance_headers,
        json={
            "name": "Finance Expense",
            "category": "Travel",
            "date": date.today().isoformat(),
            "amount": 100.0,
        },
    )
    assert f_res.status_code == 201
    exp_id = f_res.json()["id"]

    # Finance cannot delete (requires Admin)
    assert client.delete(f"/api/v1/expenses/{exp_id}", headers=finance_headers).status_code == 403

    # Admin can delete
    assert client.delete(f"/api/v1/expenses/{exp_id}", headers=admin_headers).status_code == 204


def test_recurring_expense_monthly_execution_creates_expense(client: TestClient, tenant, auth_headers, db):
    """Test that a due monthly recurring expense creates exactly one Expense preserving all fields."""
    from backend.app.models.expenses import Expense, RecurringExpense, RecurringExpenseFrequency, RecurringExpenseStatus
    from backend.app.services.expense_service import process_due_recurring_expenses
    from backend.app.services.subscription_service import add_months

    customer = tenant.customer(display_name="Recurring Client")
    run_date = date.today()

    rec = RecurringExpense(
        organization_id=tenant.organization.id,
        name="Server Hosting Monthly",
        category="Infrastructure",
        description="Dedicated cloud server billing",
        amount=Decimal("129.99"),
        currency="USD",
        frequency=RecurringExpenseFrequency.MONTHLY,
        start_date=run_date,
        next_run=run_date,
        last_run=None,
        never_ends=True,
        billable=True,
        billable_amount=Decimal("150.00"),
        customer_id=customer.id,
        customer_name=customer.display_name,
        payment_method="Credit Card",
        paid_by="Company Card",
        status=RecurringExpenseStatus.ACTIVE,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    # Process due recurring expenses
    processed = process_due_recurring_expenses(db, today=run_date)
    assert processed == 1

    # Verify Expense record created with preserved fields
    expenses = list(db.scalars(select(Expense).where(Expense.organization_id == tenant.organization.id, Expense.name == "Server Hosting Monthly")).all())
    assert len(expenses) == 1
    exp = expenses[0]

    assert exp.amount == Decimal("129.99")
    assert exp.category == "Infrastructure"
    assert exp.currency == "USD"
    assert exp.billable is True
    assert exp.billable_amount == Decimal("150.00")
    assert exp.customer_id == customer.id
    assert exp.customer_name == customer.display_name
    assert exp.payment_method == "Credit Card"
    assert exp.paid_by == "Company Card"
    assert exp.date == run_date

    # Verify last_run and next_run
    db.refresh(rec)
    assert rec.last_run == run_date
    expected_next = add_months(run_date, 1, anchor_day=run_date.day)
    assert rec.next_run == expected_next


def test_recurring_expense_execution_idempotency(client: TestClient, tenant, auth_headers, db):
    """Running execution twice for the same occurrence must NOT create duplicate expenses."""
    from backend.app.models.expenses import Expense, RecurringExpense, RecurringExpenseFrequency, RecurringExpenseStatus
    from backend.app.services.expense_service import process_due_recurring_expenses

    run_date = date.today()
    rec = RecurringExpense(
        organization_id=tenant.organization.id,
        name="Monthly SaaS Seat",
        category="Software",
        amount=Decimal("25.00"),
        currency="USD",
        frequency=RecurringExpenseFrequency.MONTHLY,
        start_date=run_date,
        next_run=run_date,
        never_ends=True,
        status=RecurringExpenseStatus.ACTIVE,
    )
    db.add(rec)
    db.commit()

    # First execution
    count1 = process_due_recurring_expenses(db, today=run_date)
    assert count1 == 1

    # Second execution on same day
    count2 = process_due_recurring_expenses(db, today=run_date)
    assert count2 == 0

    # Total expenses created must remain exactly 1
    total_expenses = db.scalars(
        select(Expense).where(Expense.organization_id == tenant.organization.id, Expense.name == "Monthly SaaS Seat")
    ).all()
    assert len(list(total_expenses)) == 1


def test_recurring_expense_skipped_when_inactive_or_future(client: TestClient, tenant, auth_headers, db):
    """Inactive (paused/ended) or future recurring expenses must be skipped."""
    from backend.app.models.expenses import Expense, RecurringExpense, RecurringExpenseFrequency, RecurringExpenseStatus
    from backend.app.services.expense_service import process_due_recurring_expenses
    from datetime import timedelta

    today = date.today()

    # Inactive recurring expense with next_run <= today
    paused_rec = RecurringExpense(
        organization_id=tenant.organization.id,
        name="Paused Expense",
        category="Software",
        amount=Decimal("10.00"),
        currency="USD",
        frequency=RecurringExpenseFrequency.MONTHLY,
        start_date=today,
        next_run=today,
        never_ends=True,
        status=RecurringExpenseStatus.PAUSED,
    )
    # Future recurring expense with next_run > today
    future_rec = RecurringExpense(
        organization_id=tenant.organization.id,
        name="Future Expense",
        category="Software",
        amount=Decimal("20.00"),
        currency="USD",
        frequency=RecurringExpenseFrequency.MONTHLY,
        start_date=today + timedelta(days=10),
        next_run=today + timedelta(days=10),
        never_ends=True,
        status=RecurringExpenseStatus.ACTIVE,
    )
    db.add_all([paused_rec, future_rec])
    db.commit()

    processed = process_due_recurring_expenses(db, today=today)
    assert processed == 0

    paused_exp = db.scalars(select(Expense).where(Expense.name == "Paused Expense")).first()
    future_exp = db.scalars(select(Expense).where(Expense.name == "Future Expense")).first()
    assert paused_exp is None
    assert future_exp is None


def test_recurring_expense_tenant_isolation(client: TestClient, tenant, auth_headers, db):
    """Tenant isolation: Organization A's recurring expense creates Expense only for Organization A."""
    from backend.app.models.expenses import Expense, RecurringExpense, RecurringExpenseFrequency, RecurringExpenseStatus
    from backend.app.services.expense_service import process_due_recurring_expenses
    from backend.tests.conftest import Tenant

    tenant_b = Tenant(db, suffix=uuid.uuid4().hex[:6])

    rec = RecurringExpense(
        organization_id=tenant.organization.id,
        name="Tenant A Secret Recurring",
        category="R&D",
        amount=Decimal("999.00"),
        currency="USD",
        frequency=RecurringExpenseFrequency.MONTHLY,
        start_date=date.today(),
        next_run=date.today(),
        never_ends=True,
        status=RecurringExpenseStatus.ACTIVE,
    )
    db.add(rec)
    db.commit()

    process_due_recurring_expenses(db, today=date.today())

    # Tenant A sees the expense
    res_a = client.get("/api/v1/expenses", headers=auth_headers)
    assert res_a.status_code == 200
    a_names = [e["name"] for e in res_a.json()]
    assert "Tenant A Secret Recurring" in a_names

    # Tenant B must NOT see the expense
    res_b = client.get("/api/v1/expenses", headers=tenant_b.headers())
    assert res_b.status_code == 200
    b_names = [e["name"] for e in res_b.json()]
    assert "Tenant A Secret Recurring" not in b_names


def test_recurring_expense_weekly_and_yearly_frequencies(client: TestClient, tenant, auth_headers, db):
    """Weekly advances 7 days; yearly advances 12 months."""
    from backend.app.models.expenses import RecurringExpense, RecurringExpenseFrequency, RecurringExpenseStatus
    from backend.app.services.expense_service import process_due_recurring_expenses
    from backend.app.services.subscription_service import add_months
    from datetime import timedelta

    today = date.today()

    weekly_rec = RecurringExpense(
        organization_id=tenant.organization.id,
        name="Weekly Standup Coffee",
        category="Meals",
        amount=Decimal("15.00"),
        currency="USD",
        frequency=RecurringExpenseFrequency.WEEKLY,
        start_date=today,
        next_run=today,
        never_ends=True,
        status=RecurringExpenseStatus.ACTIVE,
    )
    yearly_rec = RecurringExpense(
        organization_id=tenant.organization.id,
        name="Annual Domain Registration",
        category="Infrastructure",
        amount=Decimal("50.00"),
        currency="USD",
        frequency=RecurringExpenseFrequency.YEARLY,
        start_date=today,
        next_run=today,
        never_ends=True,
        status=RecurringExpenseStatus.ACTIVE,
    )
    db.add_all([weekly_rec, yearly_rec])
    db.commit()

    processed = process_due_recurring_expenses(db, today=today)
    assert processed == 2

    db.refresh(weekly_rec)
    db.refresh(yearly_rec)

    assert weekly_rec.last_run == today
    assert weekly_rec.next_run == today + timedelta(days=7)

    assert yearly_rec.last_run == today
    assert yearly_rec.next_run == add_months(today, 12, anchor_day=today.day)


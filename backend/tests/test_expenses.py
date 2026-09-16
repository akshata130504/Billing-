"""Tests for Expenses and Recurring Expenses persistence, CRUD, RBAC, batch import, and tenant isolation."""
from datetime import date
from decimal import Decimal
import uuid

import pytest
from fastapi.testclient import TestClient

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

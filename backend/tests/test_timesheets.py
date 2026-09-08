"""Comprehensive Timesheets and Time Tracking Module tests."""
from datetime import date, timedelta
from decimal import Decimal
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.models import (
    Customer,
    Invoice,
    InvoiceStatus,
    MemberRole,
    TimeEntry,
    TimeEntryStatus,
)


def test_create_time_entry_billable_calculation(client: TestClient, tenant, auth_headers):
    customer = tenant.customer(display_name="Billable Client")

    res = client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "project_name": "API Integration",
            "date": date.today().isoformat(),
            "duration_hours": 6.5,
            "description": "Implemented OAuth2 backend endpoints",
            "billable": True,
            "billing_rate": 120.0,
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["customer_id"] == customer.id
    assert data["customer_name"] == "Billable Client"
    assert data["project_name"] == "API Integration"
    assert Decimal(data["duration_hours"]) == Decimal("6.50")
    assert data["billable"] is True
    assert Decimal(data["billing_rate"]) == Decimal("120.00")
    assert Decimal(data["billable_amount"]) == Decimal("780.00")  # 6.5 * 120
    assert data["status"] == "draft"


def test_create_non_billable_time_entry(client: TestClient, tenant, auth_headers):
    res = client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "project_name": "Internal Training",
            "date": date.today().isoformat(),
            "duration_hours": 3.0,
            "description": "Security compliance workshop",
            "billable": False,
            "billing_rate": 0,
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["billable"] is False
    assert Decimal(data["billable_amount"]) == Decimal("0.00")


def test_update_time_entry(client: TestClient, tenant, auth_headers):
    # Create
    create_res = client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "project_name": "Documentation",
            "date": date.today().isoformat(),
            "duration_hours": 2.0,
            "description": "Drafting initial guide",
            "billable": True,
            "billing_rate": 50.0,
        },
    )
    entry_id = create_res.json()["id"]

    # Update
    update_res = client.patch(
        f"/api/v1/timesheets/{entry_id}",
        headers=auth_headers,
        json={
            "duration_hours": 4.0,
            "billing_rate": 60.0,
            "description": "Completed technical API documentation",
        },
    )
    assert update_res.status_code == 200, update_res.text
    updated = update_res.json()
    assert Decimal(updated["duration_hours"]) == Decimal("4.00")
    assert Decimal(updated["billing_rate"]) == Decimal("60.00")
    assert Decimal(updated["billable_amount"]) == Decimal("240.00")  # 4 * 60


def test_delete_time_entry(client: TestClient, tenant, auth_headers):
    create_res = client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "project_name": "Temporary Task",
            "date": date.today().isoformat(),
            "duration_hours": 1.0,
            "description": "Accidental entry",
            "billable": False,
        },
    )
    entry_id = create_res.json()["id"]

    del_res = client.delete(f"/api/v1/timesheets/{entry_id}", headers=auth_headers)
    assert del_res.status_code == 204

    # Verify 404
    get_res = client.get(f"/api/v1/timesheets/{entry_id}", headers=auth_headers)
    assert get_res.status_code == 404


def test_timesheet_summary_and_weekly_matrix(client: TestClient, tenant, auth_headers):
    customer = tenant.customer(display_name="Weekly Client")
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # Create entries across days
    client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "project_name": "Project Alpha",
            "date": monday.isoformat(),
            "duration_hours": 8.0,
            "description": "Day 1 Architecture",
            "billable": True,
            "billing_rate": 100.0,
        },
    )
    client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "project_name": "Project Alpha",
            "date": (monday + timedelta(days=1)).isoformat(),
            "duration_hours": 7.0,
            "description": "Day 2 Implementation",
            "billable": True,
            "billing_rate": 100.0,
        },
    )

    # Summary
    sum_res = client.get("/api/v1/timesheets/summary", headers=auth_headers)
    assert sum_res.status_code == 200, sum_res.text
    summary = sum_res.json()
    assert Decimal(summary["total_hours"]) >= Decimal("15.00")
    assert Decimal(summary["billable_hours"]) >= Decimal("15.00")
    assert Decimal(summary["billable_amount"]) >= Decimal("1500.00")

    # Weekly matrix
    week_res = client.get(f"/api/v1/timesheets/weekly?week_start={monday.isoformat()}", headers=auth_headers)
    assert week_res.status_code == 200, week_res.text
    weekly = week_res.json()
    assert Decimal(weekly["total_hours"]) >= Decimal("15.00")
    assert len(weekly["rows"]) >= 1


def test_submit_approve_reject_workflow(client: TestClient, tenant, auth_headers):
    # Create draft
    create_res = client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "project_name": "QA Testing",
            "date": date.today().isoformat(),
            "duration_hours": 5.0,
            "description": "Regression test suite validation",
            "billable": True,
            "billing_rate": 80.0,
        },
    )
    entry_id = create_res.json()["id"]
    assert create_res.json()["status"] == "draft"

    # Submit
    sub_res = client.post(f"/api/v1/timesheets/{entry_id}/submit", headers=auth_headers)
    assert sub_res.status_code == 200
    assert sub_res.json()["status"] == "submitted"

    # Reject
    rej_res = client.post(
        f"/api/v1/timesheets/{entry_id}/reject",
        headers=auth_headers,
        json={"reason": "Please attach test reports"},
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"
    assert rej_res.json()["rejection_reason"] == "Please attach test reports"

    # Re-submit and approve
    sub_res2 = client.post(f"/api/v1/timesheets/{entry_id}/submit", headers=auth_headers)
    assert sub_res2.status_code == 200
    assert sub_res2.json()["status"] == "submitted"

    app_res = client.post(f"/api/v1/timesheets/{entry_id}/approve", headers=auth_headers)
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "approved"
    assert app_res.json()["approved_at"] is not None


def test_generate_invoice_from_timesheets(client: TestClient, tenant, auth_headers):
    customer = tenant.customer(display_name="Invoicing Corp")

    # Create 2 billable entries
    e1 = client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "project_name": "Dev Work",
            "date": date.today().isoformat(),
            "duration_hours": 10.0,
            "description": "Backend implementation",
            "billable": True,
            "billing_rate": 100.0,
        },
    ).json()

    e2 = client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "project_name": "Dev Work",
            "date": date.today().isoformat(),
            "duration_hours": 5.0,
            "description": "Frontend UI build",
            "billable": True,
            "billing_rate": 100.0,
        },
    ).json()

    # Generate invoice
    inv_res = client.post(
        "/api/v1/timesheets/generate-invoice",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "time_entry_ids": [e1["id"], e2["id"]],
            "notes": "Consulting work for period",
        },
    )
    assert inv_res.status_code == 200, inv_res.text
    inv_data = inv_res.json()

    assert inv_data["customer_id"] == customer.id
    assert inv_data["invoice_number"].startswith("INV-")
    assert Decimal(inv_data["subtotal"]) == Decimal("1500.00")  # (10*100) + (5*100)

    # Verify time entries are now marked BILLED with invoice_id
    get_e1 = client.get(f"/api/v1/timesheets/{e1['id']}", headers=auth_headers).json()
    assert get_e1["status"] == "billed"
    assert get_e1["invoice_id"] == inv_data["id"]

    # Verify billed entry cannot be deleted
    del_attempt = client.delete(f"/api/v1/timesheets/{e1['id']}", headers=auth_headers)
    assert del_attempt.status_code == 409  # InvalidStateError


def test_timesheet_tenant_isolation(client: TestClient, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other_tenant = Tenant(db, suffix=uuid.uuid4().hex[:6])
    other_auth_headers = other_tenant.headers()

    # Create entry in Tenant 1
    t1_entry = client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "project_name": "Tenant 1 Project",
            "date": date.today().isoformat(),
            "duration_hours": 4.0,
            "description": "Private work",
            "billable": True,
            "billing_rate": 100.0,
        },
    ).json()

    # Tenant 2 cannot see it
    res = client.get(f"/api/v1/timesheets/{t1_entry['id']}", headers=other_auth_headers)
    assert res.status_code == 404

    # Tenant 2 cannot update it
    u_res = client.patch(
        f"/api/v1/timesheets/{t1_entry['id']}",
        headers=other_auth_headers,
        json={"description": "Hacked description"},
    )
    assert u_res.status_code == 404

    # Tenant 2 cannot delete it
    d_res = client.delete(f"/api/v1/timesheets/{t1_entry['id']}", headers=other_auth_headers)
    assert d_res.status_code == 404

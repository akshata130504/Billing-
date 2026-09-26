"""Tests for Projects persistence, CRUD, RBAC, and tenant isolation."""
from datetime import date
from decimal import Decimal
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.models import MemberRole


def test_create_project_and_read(client: TestClient, tenant, auth_headers):
    customer = tenant.customer(display_name="Acme Corp")

    res = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={
            "name": "Cloud Migration",
            "customer_id": customer.id,
            "description": "Migrating servers to AWS",
            "status": "active",
            "start_date": date.today().isoformat(),
            "billing_method": "time_and_material",
            "budget": 25000.0,
            "project_manager": "Jane Doe",
            "notes": "Kickoff on Monday",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["name"] == "Cloud Migration"
    assert data["customer_id"] == customer.id
    assert data["customer_name"] == "Acme Corp"
    assert data["status"] == "active"
    assert data["billing_method"] == "time_and_material"
    assert Decimal(data["budget"]) == Decimal("25000.00")
    assert data["project_manager"] == "Jane Doe"

    # Read project detail
    detail_res = client.get(f"/api/v1/projects/{data['id']}", headers=auth_headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == data["id"]
    assert "timesheets" in detail
    assert "expense_list" in detail


def test_project_list_and_search(client: TestClient, tenant, auth_headers):
    client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Alpha Portal", "status": "active", "budget": 10000.0},
    )
    client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Beta Mobile App", "status": "completed", "budget": 15000.0},
    )

    # Search
    search_res = client.get("/api/v1/projects?search=Alpha", headers=auth_headers)
    assert search_res.status_code == 200
    items = search_res.json()
    assert len(items) == 1
    assert items[0]["name"] == "Alpha Portal"

    # Filter status
    filter_res = client.get("/api/v1/projects?status=completed", headers=auth_headers)
    assert filter_res.status_code == 200
    completed_items = filter_res.json()
    assert any(p["name"] == "Beta Mobile App" for p in completed_items)


def test_project_update_and_delete(client: TestClient, tenant, auth_headers):
    proj = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Temporary Project", "status": "draft", "budget": 5000.0},
    ).json()

    # Update
    update_res = client.patch(
        f"/api/v1/projects/{proj['id']}",
        headers=auth_headers,
        json={"status": "active", "budget": 7500.0},
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["status"] == "active"
    assert Decimal(updated["budget"]) == Decimal("7500.00")

    # Delete
    del_res = client.delete(f"/api/v1/projects/{proj['id']}", headers=auth_headers)
    assert del_res.status_code == 204

    # Verify 404
    get_res = client.get(f"/api/v1/projects/{proj['id']}", headers=auth_headers)
    assert get_res.status_code == 404


def test_project_summary_kpis(client: TestClient, tenant, auth_headers):
    res = client.get("/api/v1/projects/summary", headers=auth_headers)
    assert res.status_code == 200
    kpis = res.json()
    assert "total_projects" in kpis
    assert "active_projects" in kpis
    assert "total_budget" in kpis


def test_project_tenant_isolation(client: TestClient, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other_tenant = Tenant(db, suffix=uuid.uuid4().hex[:6])
    other_headers = other_tenant.headers()

    # Create project in tenant 1
    p1 = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Confidential Tenant 1 Project"},
    ).json()

    # Tenant 2 cannot see it
    res = client.get(f"/api/v1/projects/{p1['id']}", headers=other_headers)
    assert res.status_code == 404

    # Tenant 2 cannot update it
    u_res = client.patch(
        f"/api/v1/projects/{p1['id']}",
        headers=other_headers,
        json={"name": "Hacked"},
    )
    assert u_res.status_code == 404

    # Tenant 2 cannot delete it
    d_res = client.delete(f"/api/v1/projects/{p1['id']}", headers=other_headers)
    assert d_res.status_code == 404


def test_project_rbac(client: TestClient, tenant):
    viewer_headers = tenant.headers_for_role(MemberRole.VIEWER)
    finance_headers = tenant.headers_for_role(MemberRole.FINANCE)
    admin_headers = tenant.headers_for_role(MemberRole.ADMIN)

    # Viewer cannot create
    v_create = client.post(
        "/api/v1/projects",
        headers=viewer_headers,
        json={"name": "Unauthorized Project"},
    )
    assert v_create.status_code == 403

    # Finance can create
    f_create = client.post(
        "/api/v1/projects",
        headers=finance_headers,
        json={"name": "Finance Created Project"},
    )
    assert f_create.status_code == 201
    proj_id = f_create.json()["id"]

    # Viewer can view
    v_view = client.get(f"/api/v1/projects/{proj_id}", headers=viewer_headers)
    assert v_view.status_code == 200

    # Finance cannot delete (requires Admin)
    f_del = client.delete(f"/api/v1/projects/{proj_id}", headers=finance_headers)
    assert f_del.status_code == 403

    # Admin can delete
    a_del = client.delete(f"/api/v1/projects/{proj_id}", headers=admin_headers)
    assert a_del.status_code == 204


def test_project_rejects_unknown_customer(client: TestClient, tenant, auth_headers):
    res = client.post("/api/v1/projects", headers=auth_headers, json={"name": "Ghost", "customer_id": "missing"})
    assert res.status_code == 404


def test_project_invoice_is_real_and_listed_on_detail(client: TestClient, tenant, auth_headers):
    customer = tenant.customer(display_name="Milestone Client")
    project = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Portal Build", "customer_id": customer.id, "budget": 100000},
    ).json()

    res = client.post(
        f"/api/v1/projects/{project['id']}/invoices",
        headers=auth_headers,
        json={"amount": "25000", "description": "Milestone 1", "tax_rate_pct": "18"},
    )
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["invoiceNumber"].startswith("INV-")
    assert created["status"] == "draft"
    assert created["amount"] == 29500.0

    inv = client.get(f"/api/v1/invoices/{created['id']}", headers=auth_headers).json()
    assert inv["customer"]["id"] == customer.id
    assert inv["items"][0]["description"] == "Milestone 1"

    detail = client.get(f"/api/v1/projects/{project['id']}", headers=auth_headers).json()
    assert [i["id"] for i in detail["invoices"]] == [created["id"]]
    assert any(t["type"] == "Invoice" for t in detail["transactions"])
    assert Decimal(str(detail["billed"])) == Decimal("25000.00")

    # A project without a customer cannot be invoiced
    orphan = client.post("/api/v1/projects", headers=auth_headers, json={"name": "Internal"}).json()
    res = client.post(f"/api/v1/projects/{orphan['id']}/invoices", headers=auth_headers, json={"amount": "10"})
    assert res.status_code == 422


def test_time_entry_logged_on_project_inherits_customer(client: TestClient, tenant, auth_headers):
    customer = tenant.customer()
    project = client.post(
        "/api/v1/projects", headers=auth_headers, json={"name": "T&M", "customer_id": customer.id}
    ).json()
    entry = client.post(
        "/api/v1/timesheets",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "date": date.today().isoformat(),
            "duration_hours": 2,
            "description": "Work",
            "billing_rate": 50,
        },
    )
    assert entry.status_code in (200, 201), entry.text
    assert entry.json()["customer_id"] == customer.id
    assert entry.json()["project_name"] == "T&M"

"""BUG-23: a time entry's project_id must name a project of the same tenant and customer."""
from datetime import date
import uuid

from fastapi.testclient import TestClient


def _project(client: TestClient, headers: dict, name: str, customer_id: str | None = None) -> dict:
    body = {"name": name}
    if customer_id:
        body["customer_id"] = customer_id
    res = client.post("/api/v1/projects", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _entry(**over) -> dict:
    return {"date": date.today().isoformat(), "duration_hours": 1, "description": "Work", "billing_rate": 10, **over}


def test_entry_linked_to_project_of_the_customer(client: TestClient, tenant, auth_headers):
    customer = tenant.customer()
    project = _project(client, auth_headers, "Portal", customer.id)
    res = client.post("/api/v1/timesheets", headers=auth_headers, json=_entry(customer_id=customer.id, project_id=project["id"]))
    assert res.status_code == 201, res.text
    assert res.json()["project_id"] == project["id"]
    assert res.json()["project_name"] == "Portal"


def test_unknown_project_is_rejected(client: TestClient, tenant, auth_headers):
    res = client.post("/api/v1/timesheets", headers=auth_headers, json=_entry(project_id=str(uuid.uuid4())))
    assert res.status_code == 404, res.text


def test_project_of_another_tenant_is_rejected(client: TestClient, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, suffix=uuid.uuid4().hex[:6])
    foreign = _project(client, other.headers(), "Foreign")
    res = client.post("/api/v1/timesheets", headers=auth_headers, json=_entry(project_id=foreign["id"]))
    assert res.status_code == 404, res.text
    entry = client.post("/api/v1/timesheets", headers=auth_headers, json=_entry()).json()
    res = client.patch(f"/api/v1/timesheets/{entry['id']}", headers=auth_headers, json={"project_id": foreign["id"]})
    assert res.status_code == 404, res.text


def test_project_of_another_customer_is_rejected(client: TestClient, tenant, auth_headers):
    mine = tenant.customer()
    theirs = tenant.customer()
    project = _project(client, auth_headers, "Theirs", theirs.id)
    res = client.post("/api/v1/timesheets", headers=auth_headers, json=_entry(customer_id=mine.id, project_id=project["id"]))
    assert res.status_code == 422, res.text

    entry = client.post("/api/v1/timesheets", headers=auth_headers, json=_entry(customer_id=mine.id)).json()
    res = client.patch(f"/api/v1/timesheets/{entry['id']}", headers=auth_headers, json={"project_id": project["id"]})
    assert res.status_code == 422, res.text


def test_update_links_a_project_and_clears_it(client: TestClient, tenant, auth_headers):
    customer = tenant.customer()
    project = _project(client, auth_headers, "Retainer", customer.id)
    entry = client.post("/api/v1/timesheets", headers=auth_headers, json=_entry(customer_id=customer.id)).json()
    res = client.patch(f"/api/v1/timesheets/{entry['id']}", headers=auth_headers, json={"project_id": project["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["project_id"] == project["id"]
    res = client.patch(f"/api/v1/timesheets/{entry['id']}", headers=auth_headers, json={"project_id": ""})
    assert res.status_code == 200, res.text
    assert res.json()["project_id"] is None

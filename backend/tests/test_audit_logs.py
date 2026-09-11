"""Audit log listing and export tests."""
import csv
import io
import json
from datetime import date, timedelta

from backend.app.models import MemberRole

BASE = "/api/v1/audit-logs"
CUSTOMERS = "/api/v1/customers"


def _seed(client, headers):
    created = client.post(CUSTOMERS, json={"display_name": "Audit Target"}, headers=headers).json()
    client.patch(f"{CUSTOMERS}/{created['id']}", json={"notes": "changed"}, headers=headers)
    return created


def test_list_requires_admin_and_filters(client, tenant, auth_headers):
    finance = tenant.headers_for_role(MemberRole.FINANCE)
    created = _seed(client, finance)

    assert client.get(BASE, headers=finance).status_code == 403

    resp = client.get(BASE, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0]["action"] == "CUSTOMER_UPDATED"  # newest first
    entry = body["items"][0]
    assert entry["actor"]["email"].startswith("finance-")
    assert entry["actor_label"]
    assert entry["entity_type"] == "customer"
    assert entry["entity_id"] == created["id"]
    assert entry["entity_label"] == "Audit Target"
    assert entry["status"] == "success"
    assert entry["before_state"]["notes"] is None
    assert entry["after_state"]["notes"] == "changed"
    assert entry["created_at"].endswith("Z")

    assert client.get(BASE, headers=auth_headers, params={"action": "CUSTOMER_CREATED"}).json()["total"] == 1
    assert client.get(BASE, headers=auth_headers, params={"entity_type": "quote"}).json()["total"] == 0
    assert client.get(BASE, headers=auth_headers, params={"search": "audit target"}).json()["total"] == 2
    assert client.get(BASE, headers=auth_headers, params={"actor_user_id": tenant.owner.id}).json()["total"] == 0
    # Date filters mean calendar dates in the organization's timezone, not the
    # server's. On a UTC CI runner these differ from date.today() for 5.5 hours
    # a day, which is exactly the bug the timezone handling fixes.
    from backend.app.services import timezones

    today = timezones.today_in(timezones.tz_for(tenant.organization))
    assert client.get(BASE, headers=auth_headers, params={"date_from": today.isoformat(), "date_to": today.isoformat()}).json()["total"] == 2
    assert client.get(BASE, headers=auth_headers, params={"date_to": (today - timedelta(days=1)).isoformat()}).json()["total"] == 0


def test_tenant_isolation(client, tenant, auth_headers, db):
    import uuid

    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    _seed(client, other.headers())
    assert client.get(BASE, headers=auth_headers).json()["total"] == 0
    assert client.get(BASE, headers=other.headers()).json()["total"] == 2


def test_export_csv_and_json(client, tenant, auth_headers):
    created = _seed(client, auth_headers)

    resp = client.get(f"{BASE}/export", headers=auth_headers, params={"format": "csv"})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"].startswith("attachment;")
    assert ".csv" in resp.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert rows[0][:5] == ["id", "created_at", "actor", "actor_label", "action"]
    assert len(rows) == 3
    assert rows[1][4] == "CUSTOMER_UPDATED"
    assert json.loads(rows[1][10])["notes"] == "changed"

    resp = client.get(f"{BASE}/export", headers=auth_headers, params={"format": "json", "action": "CUSTOMER_CREATED"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert ".json" in resp.headers["content-disposition"]
    data = resp.json()
    assert len(data) == 1
    assert data[0]["action"] == "CUSTOMER_CREATED"
    assert data[0]["entity_id"] == created["id"]
    assert data[0]["after_state"]["display_name"] == "Audit Target"

    assert client.get(f"{BASE}/export", headers=auth_headers, params={"format": "xml"}).status_code == 422
    assert client.get(f"{BASE}/export", headers=tenant.headers_for_role(MemberRole.FINANCE)).status_code == 403

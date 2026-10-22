"""Characterisation tests for the timesheets API (modularization P0, module "timesheets").

They pin today's observable behaviour of /api/v1/timesheets - response shapes (checked against the
OpenAPI snapshot), list visibility and ordering, ownership rules, not-found handling, tenant
isolation, role checks and the OpenAPI contract - so that moving the timesheets code into its own
module can be shown to change nothing. Billing maths, the submit/approve/reject workflow and
invoice generation are covered by test_timesheets.py and are not repeated here. Where today's
behaviour is surprising it is recorded as-is and marked "current behaviour".
"""
import json
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.models import MemberRole, ROLE_RANK

BASE = "/api/v1/timesheets"
SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "timesheets_openapi.json"
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
WEEK = {"week_start": (date.today() - timedelta(days=date.today().weekday())).isoformat()}


def _snapshot_fields(schema: str) -> set:
    return set(json.loads(SNAPSHOT.read_text(encoding="utf-8"))["schemas"][schema]["properties"])


def _entry(client, headers, **body):
    body = {"date": YESTERDAY, "duration_hours": "1.5", "description": f"Work {uuid.uuid4().hex[:6]}", **body}
    res = client.post(BASE, headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


# --- Response shapes, listing --------------------------------------------------------------------


def test_entry_summary_and_weekly_return_the_snapshotted_shapes(client: TestClient, tenant, auth_headers):
    entry = _entry(client, auth_headers)
    assert set(entry) <= _snapshot_fields("TimeEntryRead") and {"id", "date", "status"} <= set(entry)
    assert set(client.get(f"{BASE}/{entry['id']}", headers=auth_headers).json()) <= _snapshot_fields("TimeEntryRead")
    assert set(client.get(f"{BASE}/summary", headers=auth_headers).json()) <= _snapshot_fields("TimeEntrySummaryKPIs")
    weekly = client.get(f"{BASE}/weekly", headers=auth_headers, params=WEEK)
    assert set(weekly.json()) <= _snapshot_fields("WeeklyTimesheetResponse")
    assert client.get(f"{BASE}/weekly", headers=auth_headers).status_code == 422  # week_start is required


def test_list_is_a_plain_array_newest_date_first(client: TestClient, tenant, auth_headers):
    older = _entry(client, auth_headers, date=(date.today() - timedelta(days=3)).isoformat())
    newer = _entry(client, auth_headers)
    body = client.get(BASE, headers=auth_headers).json()
    assert isinstance(body, list)
    assert [row["id"] for row in body] == [newer["id"], older["id"]]


def test_any_member_lists_every_entry_of_the_organization(client: TestClient, tenant, auth_headers):
    # current behaviour: the list is not restricted to the caller's own entries (open decision:
    # akshatatrathodrooman/Rooman-Billing-Modular#11; a change there must update this test)
    owners_entry = _entry(client, auth_headers)
    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    assert owners_entry["id"] in [row["id"] for row in client.get(BASE, headers=viewer).json()]


# --- Ownership -----------------------------------------------------------------------------------


def test_members_below_finance_cannot_change_someone_elses_entry(client: TestClient, tenant, auth_headers):
    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    for method, suffix, body in [("PATCH", "", {"description": "x"}), ("DELETE", "", None), ("POST", "/submit", None)]:
        entry = _entry(client, auth_headers)
        res = client.request(method, f"{BASE}/{entry['id']}{suffix}", headers=viewer, json=body)
        assert res.status_code == 403, (method, suffix, res.status_code)


def test_finance_can_change_someone_elses_entry(client: TestClient, tenant, auth_headers):
    entry = _entry(client, auth_headers)
    finance = tenant.headers_for_role(MemberRole.FINANCE)
    res = client.patch(f"{BASE}/{entry['id']}", headers=finance, json={"description": "Corrected by finance"})
    assert res.status_code == 200
    assert res.json()["description"] == "Corrected by finance"


# --- Not found, credentials, tenant isolation ---------------------------------------------------

ID_ROUTES = [("GET", ""), ("PATCH", ""), ("DELETE", ""), ("POST", "/submit"), ("POST", "/approve"), ("POST", "/reject")]


def test_unknown_entry_is_404_on_every_route(client: TestClient, tenant, auth_headers):
    missing = str(uuid.uuid4())
    for method, suffix in ID_ROUTES:
        body = {} if method in ("PATCH", "POST") else None
        res = client.request(method, f"{BASE}/{missing}{suffix}", headers=auth_headers, json=body)
        assert res.status_code == 404, (method, suffix, res.status_code, res.text)


def test_requests_without_credentials_are_rejected(client: TestClient):
    anonymous = TestClient(client.app)  # own cookie jar: nothing carried over from other tests
    missing = str(uuid.uuid4())
    routes = [("GET", ""), ("GET", "/summary"), ("GET", "/weekly"), ("POST", ""), ("POST", "/generate-invoice")]
    routes += [(method, f"/{missing}{suffix}") for method, suffix in ID_ROUTES]
    for method, suffix in routes:
        res = anonymous.request(method, f"{BASE}{suffix}", json={} if method in ("POST", "PATCH") else None)
        assert res.status_code == 401, (method, suffix, res.status_code)


def test_another_tenant_cannot_reach_an_entry(client: TestClient, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    foreign = _entry(client, other.headers())
    for method, suffix in ID_ROUTES:
        body = {} if method in ("PATCH", "POST") else None
        res = client.request(method, f"{BASE}/{foreign['id']}{suffix}", headers=auth_headers, json=body)
        assert res.status_code == 404, (method, suffix, res.status_code)
    assert client.get(BASE, headers=auth_headers).json() == []
    assert client.get(f"{BASE}/{foreign['id']}", headers=other.headers()).json()["description"] == foreign["description"]


# --- Role matrix --------------------------------------------------------------------------------

ROLES = [MemberRole.VIEWER, MemberRole.FINANCE, MemberRole.ADMIN, MemberRole.OWNER]
EXACT = {  # route -> (minimum role, success status); each role acts on its own entry
    "list": (MemberRole.VIEWER, 200), "summary": (MemberRole.VIEWER, 200), "weekly": (MemberRole.VIEWER, 200),
    "create": (MemberRole.VIEWER, 201), "get": (MemberRole.VIEWER, 200), "update": (MemberRole.VIEWER, 200),
    "delete": (MemberRole.VIEWER, 204), "submit": (MemberRole.VIEWER, 200),
    # approve/reject act on an entry submitted by the organization owner (nobody approves their own)
    "approve": (MemberRole.FINANCE, 200), "reject": (MemberRole.FINANCE, 200),
}


@pytest.mark.parametrize("route", sorted(EXACT))
def test_role_matrix(client: TestClient, tenant, auth_headers, route):
    minimum, ok = EXACT[route]
    for role in ROLES:
        headers = tenant.headers_for_role(role)
        if route in ("approve", "reject"):
            eid = _entry(client, auth_headers)["id"]
            assert client.post(f"{BASE}/{eid}/submit", headers=auth_headers).status_code == 200
        else:
            eid = _entry(client, headers)["id"]
        res = {
            "list": lambda: client.get(BASE, headers=headers),
            "summary": lambda: client.get(f"{BASE}/summary", headers=headers),
            "weekly": lambda: client.get(f"{BASE}/weekly", headers=headers, params=WEEK),
            "create": lambda: client.post(BASE, headers=headers, json={
                "date": YESTERDAY, "duration_hours": "1", "description": "role check"}),
            "get": lambda: client.get(f"{BASE}/{eid}", headers=headers),
            "update": lambda: client.patch(f"{BASE}/{eid}", headers=headers, json={"description": role.value}),
            "delete": lambda: client.delete(f"{BASE}/{eid}", headers=headers),
            "submit": lambda: client.post(f"{BASE}/{eid}/submit", headers=headers),
            "approve": lambda: client.post(f"{BASE}/{eid}/approve", headers=headers),
            "reject": lambda: client.post(f"{BASE}/{eid}/reject", headers=headers, json={"reason": "role check"}),
        }[route]()
        expected = ok if ROLE_RANK[role] >= ROLE_RANK[minimum] else 403
        assert res.status_code == expected, (route, role.value, res.status_code, res.text)


def test_generate_invoice_role_boundary(client: TestClient, tenant, auth_headers):
    # The answer for an allowed role depends on the entries' state; only the permission boundary is pinned.
    customer = tenant.customer()
    for role in ROLES:
        res = client.post(f"{BASE}/generate-invoice", headers=tenant.headers_for_role(role), json={
            "customer_id": customer.id, "time_entry_ids": [str(uuid.uuid4())]})
        if ROLE_RANK[role] >= ROLE_RANK[MemberRole.FINANCE]:
            assert res.status_code not in (401, 403) and res.status_code < 500, (role.value, res.status_code)
        else:
            assert res.status_code == 403, (role.value, res.status_code)


# --- OpenAPI contract ---------------------------------------------------------------------------


def _timesheets_openapi(app) -> dict:
    spec = app.openapi()
    paths = {
        p: ops for p, ops in (
            (p, {m: op for m, op in v.items() if "Timesheets" in op.get("tags", [])})
            for p, v in spec["paths"].items() if p == BASE or p.startswith(BASE + "/")
        ) if ops
    }
    schemas = spec.get("components", {}).get("schemas", {})
    wanted, pending = set(), [paths]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[-1]
                if name not in wanted:
                    wanted.add(name)
                    pending.append(schemas[name])
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return {"paths": paths, "schemas": {name: schemas[name] for name in sorted(wanted)}}


def test_timesheets_openapi_contract_is_unchanged(client: TestClient):
    current = _timesheets_openapi(client.app)
    if os.environ.get("UPDATE_TIMESHEETS_OPENAPI_SNAPSHOT") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert sorted(current["paths"]) == sorted(expected["paths"])
    assert current == expected, (
        "The /timesheets API contract changed. If intended, regenerate with "
        "UPDATE_TIMESHEETS_OPENAPI_SNAPSHOT=1 and review the diff."
    )

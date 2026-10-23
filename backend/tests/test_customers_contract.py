"""Characterisation tests for the customers API (modularization P0, module "customers").

They pin today's observable behaviour of /api/v1/customers - response shapes (checked against the
OpenAPI snapshot), pagination, not-found handling, tenant isolation, role checks and the OpenAPI
contract - so that moving the customers code into its own module can be shown to change nothing.
Business rules (numbering, contacts, stats, delete guards, portal invitations) are covered by
test_customers.py and test_customer_portal_invitation.py and are not repeated here.
"""
import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.models import MemberRole, ROLE_RANK

BASE = "/api/v1/customers"
SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "customers_openapi.json"
PAGE_KEYS = {"items", "total", "page", "page_size", "total_pages"}


def _snapshot_fields(schema: str) -> set:
    return set(json.loads(SNAPSHOT.read_text(encoding="utf-8"))["schemas"][schema]["properties"])


def _create(client, headers, **body):
    body.setdefault("display_name", f"Customer {uuid.uuid4().hex[:6]}")
    res = client.post(BASE, headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


# --- Response shapes ---------------------------------------------------------------------------


def test_create_read_and_list_return_the_snapshotted_shape(client: TestClient, tenant, auth_headers):
    created = _create(client, auth_headers, email=f"{uuid.uuid4().hex[:6]}@example.test")
    customer_fields = _snapshot_fields("CustomerOut")
    assert set(created) <= customer_fields and {"id", "customer_number", "display_name"} <= set(created)

    detail = client.get(f"{BASE}/{created['id']}", headers=auth_headers).json()
    assert set(detail) <= customer_fields
    assert detail["stats"] is not None  # current behaviour: only the detail route carries stats
    assert set(detail["stats"]) <= _snapshot_fields("CustomerStats")

    listing = client.get(BASE, headers=auth_headers).json()
    assert set(listing) == PAGE_KEYS
    assert [row["id"] for row in listing["items"]] == [created["id"]]


@pytest.mark.parametrize("child", ["invoices", "payments", "subscriptions"])
def test_child_lists_are_paginated_envelopes(client: TestClient, tenant, auth_headers, child):
    customer = _create(client, auth_headers)
    body = client.get(f"{BASE}/{customer['id']}/{child}", headers=auth_headers).json()
    assert set(body) == PAGE_KEYS
    assert (body["items"], body["total"], body["page"]) == ([], 0, 1)


def test_portal_access_status_shape(client: TestClient, tenant, auth_headers):
    customer = _create(client, auth_headers)
    res = client.get(f"{BASE}/{customer['id']}/portal-access", headers=auth_headers)
    assert res.status_code == 200
    assert set(res.json()) <= _snapshot_fields("CustomerPortalAccessStatusOut")


def test_list_search_and_pagination(client: TestClient, tenant, auth_headers):
    for name in ("Zeta Traders", "Alpha Foods", "Alpha Labs"):
        _create(client, auth_headers, display_name=name)
    found = client.get(BASE, headers=auth_headers, params={"search": "alpha"}).json()
    assert sorted(row["display_name"] for row in found["items"]) == ["Alpha Foods", "Alpha Labs"]
    paged = client.get(BASE, headers=auth_headers, params={"page": 2, "page_size": 2}).json()
    assert (paged["total"], paged["page"], paged["page_size"], paged["total_pages"], len(paged["items"])) == (3, 2, 2, 2, 1)


# --- Not found, credentials, tenant isolation ---------------------------------------------------

ID_ROUTES = [
    ("GET", ""), ("PATCH", ""), ("DELETE", ""), ("PUT", "/contacts"), ("GET", "/invoices"), ("GET", "/payments"),
    ("GET", "/subscriptions"), ("GET", "/portal-access"), ("POST", "/portal-invite"), ("POST", "/portal-revoke"),
    ("POST", "/portal-reactivate"),
]


def _body(method, suffix):
    if suffix == "/contacts":
        return []
    return {} if method in ("POST", "PATCH", "PUT") else None


def test_unknown_customer_is_404_on_every_route(client: TestClient, tenant, auth_headers):
    missing = str(uuid.uuid4())
    for method, suffix in ID_ROUTES:
        res = client.request(method, f"{BASE}/{missing}{suffix}", headers=auth_headers, json=_body(method, suffix))
        assert res.status_code == 404, (method, suffix, res.status_code, res.text)


def test_requests_without_credentials_are_rejected(client: TestClient):
    anonymous = TestClient(client.app)  # own cookie jar: nothing carried over from other tests
    missing = str(uuid.uuid4())
    for method, suffix in [("GET", None), ("POST", None), *ID_ROUTES]:
        url = BASE if suffix is None else f"{BASE}/{missing}{suffix}"
        res = anonymous.request(method, url, json=_body(method, suffix or ""))
        assert res.status_code == 401, (method, url, res.status_code)


def test_another_tenant_cannot_reach_a_customer(client: TestClient, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    foreign = other.customer(display_name="Foreign Customer")
    for method, suffix in ID_ROUTES:
        res = client.request(method, f"{BASE}/{foreign.id}{suffix}", headers=auth_headers, json=_body(method, suffix))
        assert res.status_code == 404, (method, suffix, res.status_code)
    assert client.get(BASE, headers=auth_headers).json()["total"] == 0
    db.refresh(foreign)
    assert foreign.display_name == "Foreign Customer"


# --- Role matrix --------------------------------------------------------------------------------

ROLES = [MemberRole.VIEWER, MemberRole.FINANCE, MemberRole.ADMIN, MemberRole.OWNER]
EXACT = {  # route -> (minimum role, success status)
    "list": (MemberRole.VIEWER, 200), "get": (MemberRole.VIEWER, 200), "create": (MemberRole.FINANCE, 201),
    "update": (MemberRole.FINANCE, 200), "delete": (MemberRole.ADMIN, 204), "contacts": (MemberRole.FINANCE, 200),
    "invoices": (MemberRole.VIEWER, 200), "payments": (MemberRole.VIEWER, 200),
    "subscriptions": (MemberRole.VIEWER, 200), "portal-access": (MemberRole.VIEWER, 200),
}
# Portal actions answer according to the customer's portal state; only the permission boundary is pinned.
BOUNDARY = {"portal-invite": MemberRole.FINANCE, "portal-revoke": MemberRole.FINANCE, "portal-reactivate": MemberRole.FINANCE}


def _call(client, headers, route, cid):
    return {
        "list": lambda: client.get(BASE, headers=headers),
        "get": lambda: client.get(f"{BASE}/{cid}", headers=headers),
        "create": lambda: client.post(BASE, headers=headers, json={"display_name": f"Role {uuid.uuid4().hex[:6]}"}),
        "update": lambda: client.patch(f"{BASE}/{cid}", headers=headers, json={"notes": "role check"}),
        "delete": lambda: client.delete(f"{BASE}/{cid}", headers=headers),
        "contacts": lambda: client.put(f"{BASE}/{cid}/contacts", headers=headers, json=[]),
        "invoices": lambda: client.get(f"{BASE}/{cid}/invoices", headers=headers),
        "payments": lambda: client.get(f"{BASE}/{cid}/payments", headers=headers),
        "subscriptions": lambda: client.get(f"{BASE}/{cid}/subscriptions", headers=headers),
        "portal-access": lambda: client.get(f"{BASE}/{cid}/portal-access", headers=headers),
        "portal-invite": lambda: client.post(f"{BASE}/{cid}/portal-invite", headers=headers, json={}),
        "portal-revoke": lambda: client.post(f"{BASE}/{cid}/portal-revoke", headers=headers),
        "portal-reactivate": lambda: client.post(f"{BASE}/{cid}/portal-reactivate", headers=headers),
    }[route]()


@pytest.mark.parametrize("route", sorted(EXACT))
def test_role_matrix(client: TestClient, tenant, auth_headers, route):
    minimum, ok = EXACT[route]
    for role in ROLES:
        cid = _create(client, auth_headers)["id"]
        res = _call(client, tenant.headers_for_role(role), route, cid)
        expected = ok if ROLE_RANK[role] >= ROLE_RANK[minimum] else 403
        assert res.status_code == expected, (route, role.value, res.status_code, res.text)


@pytest.mark.parametrize("route", sorted(BOUNDARY))
def test_role_boundary_for_portal_actions(client: TestClient, tenant, auth_headers, route):
    for role in ROLES:
        cid = _create(client, auth_headers, email=f"{uuid.uuid4().hex[:8]}@example.test")["id"]
        res = _call(client, tenant.headers_for_role(role), route, cid)
        if ROLE_RANK[role] >= ROLE_RANK[BOUNDARY[route]]:
            assert res.status_code not in (401, 403) and res.status_code < 500, (route, role.value, res.status_code)
        else:
            assert res.status_code == 403, (route, role.value, res.status_code)


# --- OpenAPI contract ---------------------------------------------------------------------------


def _customers_openapi(app) -> dict:
    # Only operations tagged "Customers": /customers/{id}/payment-methods belongs to Payment Methods.
    spec = app.openapi()
    paths = {
        p: ops for p, ops in (
            (p, {m: op for m, op in v.items() if "Customers" in op.get("tags", [])})
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


def test_customers_openapi_contract_is_unchanged(client: TestClient):
    current = _customers_openapi(client.app)
    if os.environ.get("UPDATE_CUSTOMERS_OPENAPI_SNAPSHOT") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert sorted(current["paths"]) == sorted(expected["paths"])
    assert current == expected, (
        "The /customers API contract changed. If intended, regenerate with "
        "UPDATE_CUSTOMERS_OPENAPI_SNAPSHOT=1 and review the diff."
    )

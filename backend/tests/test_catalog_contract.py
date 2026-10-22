"""Characterisation tests for the products and plans API (modularization P0, module "products").

They pin today's observable behaviour of /api/v1/products and /api/v1/plans - response shapes,
pagination, filters and sorting, not-found handling, tenant isolation, role checks and the OpenAPI
contract - so that moving the catalog code into its own module can be shown to change nothing.
Create/update/delete rules (SKU and code uniqueness, delete guards, locked plan fields) are already
covered by test_catalog.py and are not repeated here.
"""
import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.models import MemberRole, ROLE_RANK

PRODUCTS = "/api/v1/products"
PLANS = "/api/v1/plans"
SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "catalog_openapi.json"

PAGE_KEYS = {"items", "total", "page", "page_size", "total_pages"}
PRODUCT_KEYS = {
    "id", "name", "sku", "description", "type", "unit", "hsn_sac_code", "tax_rate_pct", "is_active", "plans",
    "created_at", "updated_at",
}
PLAN_KEYS = {
    "id", "product_id", "name", "code", "description", "billing_interval", "interval_count", "pricing_model",
    "unit_amount", "currency", "setup_fee", "trial_days", "is_active", "active_subscriptions", "created_at",
    "updated_at",
}


def _product(client, headers, **body):
    body.setdefault("name", f"Product {uuid.uuid4().hex[:6]}")
    res = client.post(PRODUCTS, headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _plan(client, headers, product_id, **body):
    body = {
        "product_id": product_id, "name": f"Plan {uuid.uuid4().hex[:6]}", "code": f"P-{uuid.uuid4().hex[:8]}",
        "billing_interval": "monthly", "pricing_model": "flat", "unit_amount": "100", **body,
    }
    res = client.post(PLANS, headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


# --- Response shapes ---------------------------------------------------------------------------


def test_product_and_plan_shapes(client: TestClient, tenant, auth_headers):
    product = _product(client, auth_headers)
    plan = _plan(client, auth_headers, product["id"])
    assert set(product) == PRODUCT_KEYS
    assert set(plan) == PLAN_KEYS

    detail = client.get(f"{PRODUCTS}/{product['id']}", headers=auth_headers).json()
    assert set(detail) == PRODUCT_KEYS
    assert [set(p) for p in detail["plans"]] == [PLAN_KEYS]
    assert set(client.get(f"{PLANS}/{plan['id']}", headers=auth_headers).json()) == PLAN_KEYS

    # current behaviour: money and rates are strings with two decimals
    assert (plan["unit_amount"], plan["setup_fee"]) == ("100.00", "0.00")
    assert isinstance(product["tax_rate_pct"], str)


def test_lists_are_paginated_envelopes(client: TestClient, tenant, auth_headers):
    product = _product(client, auth_headers)
    _plan(client, auth_headers, product["id"])
    for url in (PRODUCTS, PLANS):
        body = client.get(url, headers=auth_headers).json()
        assert set(body) == PAGE_KEYS
        assert (body["total"], body["page"], body["page_size"], body["total_pages"]) == (1, 1, 20, 1)
        assert len(body["items"]) == 1


def test_products_default_to_name_order_and_accept_a_sort(client: TestClient, tenant, auth_headers):
    for name in ("Charlie", "alpha", "Bravo"):
        _product(client, auth_headers, name=name)
    names = lambda **q: [p["name"] for p in client.get(PRODUCTS, headers=auth_headers, params=q).json()["items"]]  # noqa: E731
    default = names()
    assert sorted(default, key=str.lower) == sorted(["Charlie", "alpha", "Bravo"], key=str.lower)
    assert names(sort="-name") == list(reversed(names(sort="name")))
    assert names(sort="not_a_field") == default  # unknown sort keys fall back to the default


def test_page_and_page_size(client: TestClient, tenant, auth_headers):
    for i in range(3):
        _product(client, auth_headers, name=f"Paged {i}")
    body = client.get(PRODUCTS, headers=auth_headers, params={"page": 2, "page_size": 2}).json()
    assert (body["total"], body["page"], body["page_size"], body["total_pages"], len(body["items"])) == (3, 2, 2, 2, 1)
    assert client.get(PRODUCTS, headers=auth_headers, params={"page": 0}).status_code == 422


def test_plan_filters(client: TestClient, tenant, auth_headers):
    first, second = _product(client, auth_headers), _product(client, auth_headers)
    monthly = _plan(client, auth_headers, first["id"])
    yearly = _plan(client, auth_headers, first["id"], billing_interval="yearly", is_active=False)
    other = _plan(client, auth_headers, second["id"])
    ids = lambda **q: {p["id"] for p in client.get(PLANS, headers=auth_headers, params=q).json()["items"]}  # noqa: E731
    assert ids() == {monthly["id"], yearly["id"], other["id"]}
    assert ids(product_id=first["id"]) == {monthly["id"], yearly["id"]}
    assert ids(billing_interval="yearly") == {yearly["id"]}
    assert ids(is_active="false") == {yearly["id"]}


# --- Not found, credentials, tenant isolation ---------------------------------------------------


def test_unknown_ids_are_404_on_every_route(client: TestClient, tenant, auth_headers):
    missing = str(uuid.uuid4())
    for method, url, body in [
        ("GET", f"{PRODUCTS}/{missing}", None), ("PATCH", f"{PRODUCTS}/{missing}", {"name": "x"}),
        ("DELETE", f"{PRODUCTS}/{missing}", None), ("GET", f"{PLANS}/{missing}", None),
        ("PATCH", f"{PLANS}/{missing}", {"name": "x"}), ("DELETE", f"{PLANS}/{missing}", None),
    ]:
        assert client.request(method, url, headers=auth_headers, json=body).status_code == 404, (method, url)


def test_requests_without_credentials_are_rejected(client: TestClient):
    anonymous = TestClient(client.app)  # own cookie jar: nothing carried over from other tests
    missing = str(uuid.uuid4())
    for method, url in [
        ("GET", PRODUCTS), ("POST", PRODUCTS), ("GET", f"{PRODUCTS}/{missing}"), ("PATCH", f"{PRODUCTS}/{missing}"),
        ("DELETE", f"{PRODUCTS}/{missing}"), ("GET", PLANS), ("POST", PLANS), ("GET", f"{PLANS}/{missing}"),
        ("PATCH", f"{PLANS}/{missing}"), ("DELETE", f"{PLANS}/{missing}"),
    ]:
        res = anonymous.request(method, url, json={} if method in ("POST", "PATCH") else None)
        assert res.status_code == 401, (method, url, res.status_code)


def test_another_tenant_cannot_see_or_change_products_or_plans(client: TestClient, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    product, plan = other.product_with_plan()
    for method, url, body in [
        ("PATCH", f"{PRODUCTS}/{product.id}", {"name": "taken over"}), ("DELETE", f"{PRODUCTS}/{product.id}", None),
        ("PATCH", f"{PLANS}/{plan.id}", {"name": "taken over"}), ("DELETE", f"{PLANS}/{plan.id}", None),
    ]:
        assert client.request(method, url, headers=auth_headers, json=body).status_code == 404, (method, url)
    assert client.get(PLANS, headers=auth_headers).json()["total"] == 0
    assert client.get(PLANS, headers=auth_headers, params={"product_id": product.id}).json()["total"] == 0
    # a plan cannot be attached to another tenant's product
    res = client.post(PLANS, headers=auth_headers, json={
        "product_id": product.id, "name": "x", "code": f"X-{uuid.uuid4().hex[:6]}",
        "billing_interval": "monthly", "pricing_model": "flat", "unit_amount": "1",
    })
    assert res.status_code == 404
    db.refresh(product)
    db.refresh(plan)
    assert (product.name, plan.name) != ("taken over", "taken over")


# --- Role matrix --------------------------------------------------------------------------------

ROLES = [MemberRole.VIEWER, MemberRole.FINANCE, MemberRole.ADMIN, MemberRole.OWNER]


@pytest.mark.parametrize(
    "route, minimum, ok",
    [
        ("list products", MemberRole.VIEWER, 200),
        ("get product", MemberRole.VIEWER, 200),
        ("create product", MemberRole.FINANCE, 201),
        ("update product", MemberRole.FINANCE, 200),
        ("delete product", MemberRole.ADMIN, 204),
        ("list plans", MemberRole.VIEWER, 200),
        ("get plan", MemberRole.VIEWER, 200),
        ("create plan", MemberRole.FINANCE, 201),
        ("update plan", MemberRole.FINANCE, 200),
        ("delete plan", MemberRole.ADMIN, 204),
    ],
)
def test_role_matrix(client: TestClient, tenant, auth_headers, route, minimum, ok):
    for role in ROLES:
        headers = tenant.headers_for_role(role)
        product = _product(client, auth_headers)
        plan = _plan(client, auth_headers, product["id"])
        pid, plid = product["id"], plan["id"]
        res = {
            "list products": lambda: client.get(PRODUCTS, headers=headers),
            "get product": lambda: client.get(f"{PRODUCTS}/{pid}", headers=headers),
            "create product": lambda: client.post(PRODUCTS, headers=headers, json={"name": f"By {role.value}"}),
            "update product": lambda: client.patch(f"{PRODUCTS}/{pid}", headers=headers, json={"description": role.value}),
            "delete product": lambda: client.delete(f"{PRODUCTS}/{pid}", headers=headers),
            "list plans": lambda: client.get(PLANS, headers=headers),
            "get plan": lambda: client.get(f"{PLANS}/{plid}", headers=headers),
            "create plan": lambda: client.post(PLANS, headers=headers, json={
                "product_id": pid, "name": "By role", "code": f"R-{uuid.uuid4().hex[:8]}",
                "billing_interval": "monthly", "pricing_model": "flat", "unit_amount": "1",
            }),
            "update plan": lambda: client.patch(f"{PLANS}/{plid}", headers=headers, json={"description": role.value}),
            "delete plan": lambda: client.delete(f"{PLANS}/{plid}", headers=headers),
        }[route]()
        expected = ok if ROLE_RANK[role] >= ROLE_RANK[minimum] else 403
        assert res.status_code == expected, (route, role.value, res.status_code, res.text)


# --- OpenAPI contract ---------------------------------------------------------------------------


def _catalog_openapi(app) -> dict:
    spec = app.openapi()
    paths = {
        p: v for p, v in spec["paths"].items()
        if any(p == base or p.startswith(base + "/") for base in (PRODUCTS, PLANS))
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


def test_catalog_openapi_contract_is_unchanged(client: TestClient):
    current = _catalog_openapi(client.app)
    if os.environ.get("UPDATE_CATALOG_OPENAPI_SNAPSHOT") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert sorted(current["paths"]) == sorted(expected["paths"])
    assert current == expected, (
        "The /products or /plans API contract changed. If intended, regenerate with "
        "UPDATE_CATALOG_OPENAPI_SNAPSHOT=1 and review the diff."
    )

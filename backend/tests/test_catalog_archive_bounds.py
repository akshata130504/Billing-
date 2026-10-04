"""Archived offerings are read-only (unarchive restores them); numeric bounds on prices/quantities."""
import uuid

import pytest

from backend.app.models import MemberRole, Plan, Product
from backend.tests.test_offering_subscriptions import OFFERINGS, SUBS, _offering, _subscribe

CPQ_SIMULATE = "/api/v1/cpq/simulate"
MAX_PRICE = "999999999999.99"


def _payload(**overrides):
    data = {
        "name": f"Bound {uuid.uuid4().hex[:6]}",
        "sku": f"BD-{uuid.uuid4().hex[:8].upper()}",
        "type": "plan",
        "unit": "seat",
        "currency": "INR",
        "pricing_model": "per_unit",
        "base_price": "100.00",
        "tax_rate_pct": "18.00",
        "billing_frequency": "monthly",
    }
    data.update(overrides)
    return data


def _archive(client, headers, offering_id):
    assert client.delete(f"{OFFERINGS}/{offering_id}", headers=headers).status_code == 204


# --- archived offerings -----------------------------------------------------------------


def test_patch_archived_offering_rejected_and_row_unchanged(client, auth_headers):
    offering = _offering(client, auth_headers, base_price="500.00")
    _archive(client, auth_headers, offering["id"])
    for body in ({"name": "Renamed"}, {"base_price": "1.00"}, {"is_active": False}, {"name": "X", "is_active": True}):
        res = client.patch(f"{OFFERINGS}/{offering['id']}", json=body, headers=auth_headers)
        assert res.status_code in (409, 422), (body, res.text)
        assert "Archived offerings cannot be edited" in res.json()["error"]["message"]
    got = client.get(f"{OFFERINGS}/{offering['id']}", headers=auth_headers).json()
    assert got["name"] == offering["name"]
    assert got["base_price"] == offering["base_price"]
    assert got["is_active"] is False


def test_legacy_activate_toggle_still_reactivates_archived_offering(client, auth_headers):
    offering = _offering(client, auth_headers)
    _archive(client, auth_headers, offering["id"])
    res = client.patch(f"{OFFERINGS}/{offering['id']}", json={"is_active": True}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["is_active"] is True


def test_unarchive_restores_offering_and_linked_plan(client, tenant, auth_headers, db):
    offering = _offering(client, auth_headers)
    customer = tenant.customer()
    first = _subscribe(client, auth_headers, customer.id, offering_id=offering["id"])
    assert first.status_code == 201, first.text
    _archive(client, auth_headers, offering["id"])
    db.expire_all()
    plan = db.query(Plan).filter(Plan.offering_id == offering["id"]).one()
    assert plan.is_active is False
    # Archived: not subscribable.
    assert _subscribe(client, auth_headers, tenant.customer().id, offering_id=offering["id"]).status_code == 422

    res = client.post(f"{OFFERINGS}/{offering['id']}/unarchive", headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["is_active"] is True
    db.expire_all()
    assert db.query(Plan).filter(Plan.offering_id == offering["id"]).one().is_active is True
    assert db.query(Product).filter(Product.offering_id == offering["id"]).one() is not None
    assert _subscribe(client, auth_headers, tenant.customer().id, offering_id=offering["id"]).status_code == 201
    # Editable again.
    assert client.patch(f"{OFFERINGS}/{offering['id']}", json={"name": "Back"}, headers=auth_headers).status_code == 200


def test_unarchive_active_offering_is_noop(client, auth_headers):
    offering = _offering(client, auth_headers)
    res = client.post(f"{OFFERINGS}/{offering['id']}/unarchive", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["is_active"] is True
    assert res.json()["name"] == offering["name"]


def test_unarchive_requires_admin(client, tenant, auth_headers):
    offering = _offering(client, auth_headers)
    _archive(client, auth_headers, offering["id"])
    for role in (MemberRole.FINANCE, MemberRole.VIEWER):
        res = client.post(f"{OFFERINGS}/{offering['id']}/unarchive", headers=tenant.headers_for_role(role))
        assert res.status_code == 403, (role, res.text)
    assert client.get(f"{OFFERINGS}/{offering['id']}", headers=auth_headers).json()["is_active"] is False


def test_unarchive_cross_tenant_is_404(client, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    foreign = _offering(client, other.headers())
    _archive(client, other.headers(), foreign["id"])
    res = client.post(f"{OFFERINGS}/{foreign['id']}/unarchive", headers=auth_headers)
    assert res.status_code == 404
    assert client.get(f"{OFFERINGS}/{foreign['id']}", headers=other.headers()).json()["is_active"] is False


def test_active_offering_still_editable(client, auth_headers):
    offering = _offering(client, auth_headers)
    res = client.patch(f"{OFFERINGS}/{offering['id']}", json={"name": "Edited", "base_price": "42.00"}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Edited"


def test_archived_unlinked_plan_only_reactivates(client, tenant, auth_headers, db):
    _, plan = tenant.product_with_plan()
    plan.is_active = False
    db.commit()
    res = client.patch(f"/api/v1/plans/{plan.id}", json={"name": "Nope"}, headers=auth_headers)
    assert res.status_code == 409, res.text
    res = client.patch(f"/api/v1/plans/{plan.id}", json={"is_active": True}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["is_active"] is True
    assert client.patch(f"/api/v1/plans/{plan.id}", json={"name": "Yes"}, headers=auth_headers).status_code == 200


# --- numeric bounds ---------------------------------------------------------------------


@pytest.mark.parametrize("value", ["10000000000000", "100000000000000000000", "1e20", "1000000000000.00"])
def test_base_price_above_maximum_rejected(client, auth_headers, value):
    res = client.post(OFFERINGS, json=_payload(base_price=value), headers=auth_headers)
    assert res.status_code == 422, res.text


def test_base_price_maximum_accepted_and_update_bound(client, auth_headers):
    res = client.post(OFFERINGS, json=_payload(base_price=MAX_PRICE), headers=auth_headers)
    assert res.status_code == 201, res.text
    assert res.json()["base_price"] == MAX_PRICE
    bad = client.patch(f"{OFFERINGS}/{res.json()['id']}", json={"base_price": "1e20"}, headers=auth_headers)
    assert bad.status_code == 422


def test_tier_prices_and_quantities_bounded(client, auth_headers):
    huge = [{"min_qty": 1, "max_qty": 10, "unit_price": "1e20"}]
    assert client.post(OFFERINGS, json=_payload(pricing_model="volume", pricing_tiers=huge), headers=auth_headers).status_code == 422
    pkg = [{"min_qty": 1, "max_qty": 10, "unit_price": 1, "package_qty": 1, "package_price": "1e20"}]
    assert client.post(OFFERINGS, json=_payload(pricing_model="package", pricing_tiers=pkg), headers=auth_headers).status_code == 422
    qty = [{"min_qty": 1, "max_qty": "1e20", "unit_price": 1}]
    assert client.post(OFFERINGS, json=_payload(pricing_model="volume", pricing_tiers=qty), headers=auth_headers).status_code == 422
    ok = [{"min_qty": 1, "max_qty": 10, "unit_price": MAX_PRICE}]
    assert client.post(OFFERINGS, json=_payload(pricing_model="volume", pricing_tiers=ok), headers=auth_headers).status_code == 201


def test_simulate_quantity_above_one_million_rejected(client, auth_headers):
    offering = _offering(client, auth_headers)
    body = {"items": [{"offering_id": offering["id"], "quantity": 1_000_001}]}
    assert client.post(CPQ_SIMULATE, json=body, headers=auth_headers).status_code == 422
    body["items"][0]["quantity"] = 1_000_000
    assert client.post(CPQ_SIMULATE, json=body, headers=auth_headers).status_code == 200

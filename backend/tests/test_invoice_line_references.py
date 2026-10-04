"""Invoice line catalog references (offering_id / product_id / plan_id) are validated."""
import uuid

import pytest

from backend.app.models import Plan
from backend.tests.test_invoices import BASE, _create_draft_invoice
from backend.tests.test_offering_subscriptions import _offering, _subscribe


def _line(**refs):
    return {"description": "Line", "quantity": "1", "unit_price": "100.00", "tax_rate_pct": "18", **refs}


def _post(client, headers, customer, *items):
    return client.post(BASE, json={"customer_id": customer.id, "items": list(items)}, headers=headers)


def _fields(res):
    body = res.json()["error"]
    return (body.get("details") or {}).get("fields") or body.get("fields") or {}


def test_valid_references_and_custom_lines_stored(client, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan()
    offering = _offering(client, auth_headers)
    res = _post(
        client, auth_headers, customer,
        _line(plan_id=plan.id),
        _line(product_id=product.id),
        _line(offering_id=offering["id"]),
        _line(),
    )
    assert res.status_code == 201, res.text
    items = res.json()["items"]
    assert items[0]["plan_id"] == plan.id
    assert items[1]["product_id"] == product.id
    assert items[2]["offering_id"] == offering["id"]
    assert items[3]["plan_id"] is None and items[3]["product_id"] is None


def test_cross_tenant_and_unknown_ids_rejected_with_field_path(client, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    customer = tenant.customer()
    other = Tenant(db, uuid.uuid4().hex[:8])
    foreign_product, foreign_plan = other.product_with_plan()
    foreign_offering = _offering(client, other.headers())

    res = _post(client, auth_headers, customer, _line(), _line(), _line(plan_id=foreign_plan.id))
    assert res.status_code == 422, res.text
    assert "items[2].plan_id" in _fields(res)

    res = _post(client, auth_headers, customer, _line(product_id=foreign_product.id))
    assert res.status_code == 422 and "items[0].product_id" in _fields(res)

    res = _post(client, auth_headers, customer, _line(offering_id=foreign_offering["id"]))
    assert res.status_code == 422 and "items[0].offering_id" in _fields(res)

    # Unknown ids look exactly like another tenant's ids.
    unknown = _post(client, auth_headers, customer, _line(offering_id=str(uuid.uuid4())))
    assert unknown.status_code == 422
    assert _fields(unknown) == {"items[0].offering_id": "unknown reference"}
    assert _post(client, auth_headers, customer, _line(plan_id=str(uuid.uuid4()))).status_code == 422
    assert _post(client, auth_headers, customer, _line(product_id=str(uuid.uuid4()))).status_code == 422


def test_plan_and_product_on_one_line_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan()
    res = _post(client, auth_headers, customer, _line(plan_id=plan.id, product_id=product.id))
    assert res.status_code == 422, res.text
    assert "items[0].plan_id" in _fields(res)


def test_plan_belonging_to_another_offering_rejected(client, tenant, auth_headers, db):
    customer = tenant.customer()
    linked_offering = _offering(client, auth_headers)
    assert _subscribe(client, auth_headers, customer.id, offering_id=linked_offering["id"]).status_code == 201
    linked_plan = db.query(Plan).filter(Plan.offering_id == linked_offering["id"]).one()
    other_offering = _offering(client, auth_headers)

    bad = _post(client, auth_headers, tenant.customer(), _line(plan_id=linked_plan.id, offering_id=other_offering["id"]))
    assert bad.status_code == 422, bad.text
    # The legitimate case (the plan IS the offering's link) is accepted.
    ok = _post(client, auth_headers, tenant.customer(), _line(plan_id=linked_plan.id, offering_id=linked_offering["id"]))
    assert ok.status_code == 201, ok.text


def test_update_path_validates_references(client, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    customer = tenant.customer()
    product, plan = tenant.product_with_plan()
    invoice = _create_draft_invoice(client, auth_headers, customer)
    other = Tenant(db, uuid.uuid4().hex[:8])
    foreign_product, foreign_plan = other.product_with_plan()
    url = f"{BASE}/{invoice['id']}"

    assert client.patch(url, json={"items": [_line(plan_id=foreign_plan.id)]}, headers=auth_headers).status_code == 422
    assert client.patch(url, json={"items": [_line(product_id=foreign_product.id)]}, headers=auth_headers).status_code == 422
    both = client.patch(url, json={"items": [_line(plan_id=plan.id, product_id=product.id)]}, headers=auth_headers)
    assert both.status_code == 422
    assert "items[0].plan_id" in _fields(both)
    # Nothing was changed by the rejected updates.
    unchanged = client.get(url, headers=auth_headers).json()
    assert len(unchanged["items"]) == len(invoice["items"])

    ok = client.patch(url, json={"items": [_line(plan_id=plan.id), _line()]}, headers=auth_headers)
    assert ok.status_code == 200, ok.text
    assert ok.json()["items"][0]["plan_id"] == plan.id


@pytest.mark.parametrize("empty", ["", None])
def test_empty_reference_strings_are_treated_as_absent(client, tenant, auth_headers, empty):
    customer = tenant.customer()
    res = _post(client, auth_headers, customer, _line(plan_id=empty, offering_id=empty, product_id=empty))
    assert res.status_code == 201, res.text

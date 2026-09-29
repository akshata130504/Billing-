"""Quote line references are validated strictly against the columns they are stored in.

quote_items.plan_id / product_id are foreign keys to plans / products. A catalog offering id
sent in plan_id used to pass validation and then fail on the foreign key at flush (a 500);
it must be a clear 422 that points the caller at offering_id.
"""
from backend.tests.conftest import Tenant
from backend.tests.test_quote_to_subscription import OFFERINGS, QUOTES, _offering

LINE = {"description": "Line", "quantity": "1", "unit_price": "100.00", "tax_rate_pct": "0"}


def _post(client, headers, customer, **line):
    return client.post(QUOTES, json={"customer_id": customer.id, "items": [{**LINE, **line}]}, headers=headers)


def test_offering_id_in_plan_id_is_a_clear_422(client, tenant, auth_headers):
    customer = tenant.customer()
    offering = _offering(client, auth_headers)
    res = _post(client, auth_headers, customer, plan_id=offering["id"])
    assert res.status_code == 422, res.text
    body = res.text
    assert "offering_id" in body
    assert f"items.plan_id.{offering['id']}" in body


def test_offering_id_in_product_id_is_a_clear_422(client, tenant, auth_headers):
    customer = tenant.customer()
    offering = _offering(client, auth_headers)
    res = _post(client, auth_headers, customer, product_id=offering["id"])
    assert res.status_code == 422, res.text
    assert "offering_id" in res.text


def test_unknown_and_foreign_plan_ids_are_rejected(client, tenant, auth_headers, db):
    customer = tenant.customer()
    res = _post(client, auth_headers, customer, plan_id="00000000-0000-0000-0000-000000000000")
    assert res.status_code == 422, res.text
    assert "unknown plan" in res.text

    other = Tenant(db, "qlr-other")
    _, foreign_plan = other.product_with_plan()
    res = _post(client, auth_headers, customer, plan_id=foreign_plan.id)
    assert res.status_code == 422, res.text


def test_offering_id_must_belong_to_the_org(client, tenant, auth_headers, db):
    customer = tenant.customer()
    other = Tenant(db, "qlr-off")
    foreign = _offering(client, other.headers())
    res = _post(client, auth_headers, customer, offering_id=foreign["id"])
    assert res.status_code == 422, res.text
    assert "unknown offering" in res.text


def test_valid_plan_and_offering_references_are_accepted(client, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan()
    offering = _offering(client, auth_headers)
    res = client.post(
        QUOTES,
        json={
            "customer_id": customer.id,
            "items": [
                {**LINE, "plan_id": plan.id, "product_id": product.id},
                {**LINE, "offering_id": offering["id"]},
            ],
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    items = res.json()["items"]
    assert items[0]["plan_id"] == plan.id
    assert items[1]["offering_id"] == offering["id"]
    assert OFFERINGS  # shared endpoint constant is importable

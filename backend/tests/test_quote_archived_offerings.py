"""Archived offerings on quotes.

Business rule: an archived offering (offerings.is_active = false) must not be used on a NEW quote
line, but a quote that already carries it keeps working. The server cannot trust the UI, so
create/update validate it. On update the client says which stored lines it keeps by echoing their
`id`; a removed and re-added line has no id and is therefore a new use.
"""
from decimal import Decimal

from backend.tests.conftest import Tenant
from backend.tests.test_quote_to_subscription import OFFERINGS, QUOTES, _offering

PRICING_SIMULATE = "/api/v1/pricing/simulate"


def _product(client, headers):
    return _offering(client, headers, type="product", billing_frequency="one_time")


def _line(offering, qty="1", line_id=None):
    line = {
        "offering_id": offering["id"],
        "description": offering["name"],
        "quantity": qty,
        "unit_price": "800.00",
        "tax_rate_pct": "18",
    }
    if line_id is not None:
        line["id"] = line_id
    return line


def _archive(client, headers, offering):
    res = client.delete(f"{OFFERINGS}/{offering['id']}", headers=headers)
    assert res.status_code == 204, res.text


def _post(client, headers, customer, items):
    return client.post(QUOTES, json={"customer_id": customer.id, "items": items}, headers=headers)


def _patch(client, headers, quote_id, **body):
    return client.patch(f"{QUOTES}/{quote_id}", json=body, headers=headers)


def _get(client, headers, quote_id):
    res = client.get(f"{QUOTES}/{quote_id}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _line_id(quote, offering):
    return next(i["id"] for i in quote["items"] if i["offering_id"] == offering["id"])


def _quote_with_archived_line(client, tenant, headers):
    """A quote created while its offering was active; the offering is archived afterwards."""
    customer = tenant.customer()
    archived, active = _product(client, headers), _product(client, headers)
    created = _post(client, headers, customer, [_line(archived), _line(active)])
    assert created.status_code == 201, created.text
    _archive(client, headers, archived)
    quote = _get(client, headers, created.json()["id"])
    return quote, archived, active, customer


# --- schema compatibility ---------------------------------------------------------------------------------


def test_quote_schemas_still_accept_shared_line_item_objects():
    from backend.app.schemas.common_refs import LineItemIn
    from backend.app.schemas.quotes import QuoteCreate, QuoteLineItemIn, QuoteUpdate

    shared = LineItemIn(description="Shared", quantity="1", unit_price="10", tax_rate_pct="0")
    created = QuoteCreate(customer_id="c1", items=[shared])
    updated = QuoteUpdate(items=[shared])
    assert updated.items is not None
    assert isinstance(created.items[0], QuoteLineItemIn) and created.items[0].id is None
    assert isinstance(updated.items[0], QuoteLineItemIn) and updated.items[0].id is None
    # The shared contract itself is untouched: it still has no `id` field.
    assert "id" not in LineItemIn.model_fields


# --- 1/2: new quotes ----------------------------------------------------------------------------


def test_new_quote_with_archived_offering_is_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    archived = _product(client, auth_headers)
    _archive(client, auth_headers, archived)
    res = _post(client, auth_headers, customer, [_line(archived)])
    assert res.status_code == 422, res.text
    assert f"items.offering_id.{archived['id']}" in res.text
    assert "archived" in res.text


def test_new_quote_with_active_offering_still_succeeds(client, tenant, auth_headers):
    customer = tenant.customer()
    active = _product(client, auth_headers)
    res = _post(client, auth_headers, customer, [_line(active)])
    assert res.status_code == 201, res.text
    assert res.json()["items"][0]["offering_id"] == active["id"]


def test_ids_on_a_new_quote_never_grant_an_archived_offering(client, tenant, auth_headers):
    customer = tenant.customer()
    archived = _product(client, auth_headers)
    _archive(client, auth_headers, archived)
    res = _post(client, auth_headers, customer, [_line(archived, line_id="00000000-0000-0000-0000-000000000000")])
    assert res.status_code == 422, res.text


def test_ids_on_a_new_quote_are_ignored_for_active_offerings(client, tenant, auth_headers):
    customer = tenant.customer()
    active = _product(client, auth_headers)
    res = _post(client, auth_headers, customer, [_line(active, line_id="not-a-real-line")])
    assert res.status_code == 201, res.text


# --- 3-6: existing quotes keep working ---------------------------------------------------------------


def test_existing_quote_is_still_readable_after_its_offering_is_archived(client, tenant, auth_headers):
    quote, archived, active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    assert {i["offering_id"] for i in quote["items"]} == {archived["id"], active["id"]}


def test_retaining_an_archived_line_with_its_id_is_accepted(client, tenant, auth_headers):
    quote, archived, active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    items = [_line(archived, line_id=_line_id(quote, archived)), _line(active, line_id=_line_id(quote, active))]
    res = _patch(client, auth_headers, quote["id"], items=items)
    assert res.status_code == 200, res.text
    assert {i["offering_id"] for i in res.json()["items"]} == {archived["id"], active["id"]}


def test_quantity_change_on_a_retained_archived_line_is_accepted(client, tenant, auth_headers):
    quote, archived, active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    items = [_line(archived, qty="5", line_id=_line_id(quote, archived)), _line(active)]
    res = _patch(client, auth_headers, quote["id"], items=items)
    assert res.status_code == 200, res.text
    by_offering = {i["offering_id"]: i for i in res.json()["items"]}
    assert Decimal(by_offering[archived["id"]]["quantity"]) == Decimal("5")


def test_title_only_patch_without_items_is_unchanged(client, tenant, auth_headers):
    quote, archived, _active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    res = _patch(client, auth_headers, quote["id"], title="Renamed")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["title"] == "Renamed"
    assert archived["id"] in {i["offering_id"] for i in body["items"]}


def test_discount_only_patch_without_items_is_unchanged(client, tenant, auth_headers):
    quote, archived, _active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    res = _patch(client, auth_headers, quote["id"], discount_pct="5")
    assert res.status_code == 200, res.text
    assert archived["id"] in {i["offering_id"] for i in res.json()["items"]}


# --- 7-9, 13: new uses on an existing quote -----------------------------------------------------------


def test_adding_a_different_archived_offering_to_an_existing_quote_is_rejected(client, tenant, auth_headers):
    quote, archived, active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    other = _product(client, auth_headers)
    _archive(client, auth_headers, other)
    items = [_line(archived, line_id=_line_id(quote, archived)), _line(active), _line(other)]
    res = _patch(client, auth_headers, quote["id"], items=items)
    assert res.status_code == 422, res.text
    assert f"items.offering_id.{other['id']}" in res.text


def test_second_line_of_an_already_present_archived_offering_is_rejected(client, tenant, auth_headers):
    quote, archived, active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    items = [_line(archived, line_id=_line_id(quote, archived)), _line(active), _line(archived)]
    res = _patch(client, auth_headers, quote["id"], items=items)
    assert res.status_code == 422, res.text


def test_removing_and_re_adding_an_archived_line_without_its_id_is_rejected(client, tenant, auth_headers):
    quote, archived, active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    res = _patch(client, auth_headers, quote["id"], items=[_line(active), _line(archived)])
    assert res.status_code == 422, res.text
    # The rejected save changed nothing: the original archived line (and its id) is still there.
    after = _get(client, auth_headers, quote["id"])
    assert _line_id(after, archived) == _line_id(quote, archived)


def test_archived_line_submitted_without_an_id_is_rejected(client, tenant, auth_headers):
    quote, archived, active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    res = _patch(client, auth_headers, quote["id"], items=[_line(archived), _line(active)])
    assert res.status_code == 422, res.text
    assert "archived offering cannot be added" in res.text


# --- 10-12: forged / mismatched ids ---------------------------------------------------------------


def test_duplicate_claim_of_one_stored_line_id_is_rejected(client, tenant, auth_headers):
    quote, archived, active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    stored_id = _line_id(quote, archived)
    items = [_line(archived, line_id=stored_id), _line(archived, line_id=stored_id), _line(active)]
    res = _patch(client, auth_headers, quote["id"], items=items)
    assert res.status_code == 422, res.text
    assert "already used" in res.text


def test_two_archived_lines_each_with_their_own_id_are_both_retained(client, tenant, auth_headers):
    customer = tenant.customer()
    archived = _product(client, auth_headers)
    created = _post(client, auth_headers, customer, [_line(archived), _line(archived, qty="2")])
    assert created.status_code == 201, created.text
    _archive(client, auth_headers, archived)
    stored = _get(client, auth_headers, created.json()["id"])
    ids = [i["id"] for i in stored["items"]]
    assert len(set(ids)) == 2
    items = [_line(archived, line_id=ids[0]), _line(archived, qty="2", line_id=ids[1])]
    assert _patch(client, auth_headers, stored["id"], items=items).status_code == 200
    # Dropping one of the two and re-adding it without an id is a new use.
    again = _get(client, auth_headers, stored["id"])
    keep = again["items"][0]["id"]
    res = _patch(client, auth_headers, stored["id"], items=[_line(archived, line_id=keep), _line(archived)])
    assert res.status_code == 422, res.text


def test_line_id_belonging_to_another_quote_is_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    archived = _product(client, auth_headers)
    first = _post(client, auth_headers, customer, [_line(archived)])
    second = _post(client, auth_headers, customer, [_line(archived)])
    assert first.status_code == second.status_code == 201
    _archive(client, auth_headers, archived)
    first_line_id = _line_id(_get(client, auth_headers, first.json()["id"]), archived)
    res = _patch(client, auth_headers, second.json()["id"], items=[_line(archived, line_id=first_line_id)])
    assert res.status_code == 422, res.text
    assert "does not belong to this quote" in res.text


def test_line_id_whose_stored_offering_differs_is_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    one, two = _product(client, auth_headers), _product(client, auth_headers)
    created = _post(client, auth_headers, customer, [_line(one), _line(two)])
    assert created.status_code == 201, created.text
    _archive(client, auth_headers, one)
    _archive(client, auth_headers, two)
    stored = _get(client, auth_headers, created.json()["id"])
    id_one, id_two = _line_id(stored, one), _line_id(stored, two)
    swapped = [_line(one, line_id=id_two), _line(two, line_id=id_one)]
    res = _patch(client, auth_headers, stored["id"], items=swapped)
    assert res.status_code == 422, res.text
    assert "different offering" in res.text


# --- 14: active offerings behave as before ----------------------------------------------------------------


def test_active_offerings_do_not_need_ids_on_update(client, tenant, auth_headers):
    customer = tenant.customer()
    a, b = _product(client, auth_headers), _product(client, auth_headers)
    created = _post(client, auth_headers, customer, [_line(a)])
    assert created.status_code == 201, created.text
    res = _patch(client, auth_headers, created.json()["id"], items=[_line(a), _line(b, qty="3")])
    assert res.status_code == 200, res.text
    assert len(res.json()["items"]) == 2


def test_a_new_active_line_beside_a_retained_archived_line_needs_no_id(client, tenant, auth_headers):
    quote, archived, active, _customer = _quote_with_archived_line(client, tenant, auth_headers)
    fresh = _product(client, auth_headers)
    items = [_line(archived, line_id=_line_id(quote, archived)), _line(active), _line(fresh)]
    res = _patch(client, auth_headers, quote["id"], items=items)
    assert res.status_code == 200, res.text
    assert len(res.json()["items"]) == 3


# --- 15: cross-tenant validation unchanged ------------------------------------------------------------------


def test_foreign_offering_is_still_reported_as_unknown_not_archived(client, tenant, auth_headers, db):
    customer = tenant.customer()
    other = Tenant(db, "qao-other")
    foreign = _product(client, other.headers())
    _archive(client, other.headers(), foreign)
    res = _post(client, auth_headers, customer, [_line(foreign)])
    assert res.status_code == 422, res.text
    assert "unknown offering" in res.text
    assert "archived" not in res.text.lower().replace("archived offering cannot", "")


# --- 16: unarchive makes the offering usable again --------------------------------------------------------------


def test_unarchived_offering_can_be_used_on_a_new_quote_again(client, tenant, auth_headers):
    customer = tenant.customer()
    offering = _product(client, auth_headers)
    _archive(client, auth_headers, offering)
    assert _post(client, auth_headers, customer, [_line(offering)]).status_code == 422
    res = client.post(f"{OFFERINGS}/{offering['id']}/unarchive", headers=auth_headers)
    assert res.status_code == 200, res.text
    assert _post(client, auth_headers, customer, [_line(offering)]).status_code == 201


# --- pricing simulation: clean 422 instead of a 500 ----------------------------------------------------------


def test_pricing_simulation_of_an_archived_offering_is_a_422(client, auth_headers):
    archived = _product(client, auth_headers)
    _archive(client, auth_headers, archived)
    res = client.post(PRICING_SIMULATE, json={"offering_id": archived["id"], "quantity": "1"}, headers=auth_headers)
    assert res.status_code == 422, res.text
    assert "archived" in res.text


def test_pricing_simulation_of_an_active_offering_is_unchanged(client, auth_headers):
    active = _product(client, auth_headers)
    res = client.post(PRICING_SIMULATE, json={"offering_id": active["id"], "quantity": "2"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["offering_id"] == active["id"]

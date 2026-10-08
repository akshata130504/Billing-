"""Archived offerings on user-created invoices.

Business rule: an archived offering (offerings.is_active = false) must not be used on a NEW invoice
line, but an invoice that already carries it keeps working. On update the client says which stored
lines it keeps by echoing their `id`; a removed and re-added line has no id and is a new use.
System-generated invoices (renewals, quote conversion, ...) are not restricted.
"""
from datetime import date

from backend.app.models import Subscription
from backend.tests.conftest import Tenant
from backend.tests.test_offering_subscriptions import SUBS, _offering as _plan_offering, _sub_invoices, _subscribe
from backend.tests.test_quote_to_subscription import OFFERINGS, QUOTES, _accepted_quote, _offering

INVOICES = "/api/v1/invoices"
PRICING_CALCULATE = "/api/v1/pricing/calculate"


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
    return client.post(INVOICES, json={"customer_id": customer.id, "items": items}, headers=headers)


def _patch(client, headers, invoice_id, **body):
    return client.patch(f"{INVOICES}/{invoice_id}", json=body, headers=headers)


def _get(client, headers, invoice_id):
    res = client.get(f"{INVOICES}/{invoice_id}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _line_id(invoice, offering):
    return next(i["id"] for i in invoice["items"] if i["offering_id"] == offering["id"])


def _invoice_with_archived_line(client, tenant, headers):
    """A draft invoice created while its offering was active; the offering is archived afterwards."""
    customer = tenant.customer()
    archived, active = _product(client, headers), _product(client, headers)
    created = _post(client, headers, customer, [_line(archived), _line(active)])
    assert created.status_code == 201, created.text
    _archive(client, headers, archived)
    invoice = _get(client, headers, created.json()["id"])
    return invoice, archived, active, customer


# --- schema compatibility -------------------------------------------------------------------------------


def test_invoice_schemas_still_accept_shared_line_item_objects():
    from backend.app.schemas.common_refs import LineItemIn
    from backend.app.schemas.invoices import InvoiceCreate, InvoiceLineItemIn, InvoiceUpdate

    shared = LineItemIn(description="Shared", quantity="1", unit_price="10", tax_rate_pct="0")
    created = InvoiceCreate(customer_id="c1", items=[shared])
    updated = InvoiceUpdate(items=[shared])
    assert updated.items is not None
    assert isinstance(created.items[0], InvoiceLineItemIn) and created.items[0].id is None
    assert isinstance(updated.items[0], InvoiceLineItemIn) and updated.items[0].id is None
    # The shared contract itself is untouched: it still has no `id` field.
    assert "id" not in LineItemIn.model_fields


# --- create -------------------------------------------------------------------------------------------------


def test_new_invoice_with_archived_offering_is_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    archived = _product(client, auth_headers)
    _archive(client, auth_headers, archived)
    res = _post(client, auth_headers, customer, [_line(archived)])
    assert res.status_code == 422, res.text
    assert "items[0].offering_id" in res.text
    assert "archived" in res.text


def test_new_invoice_with_active_offering_still_succeeds(client, tenant, auth_headers):
    customer = tenant.customer()
    active = _product(client, auth_headers)
    res = _post(client, auth_headers, customer, [_line(active)])
    assert res.status_code == 201, res.text
    assert res.json()["items"][0]["offering_id"] == active["id"]


def test_foreign_offering_is_still_reported_as_unknown_reference(client, tenant, auth_headers, db):
    customer = tenant.customer()
    other = Tenant(db, "iao-other")
    foreign = _product(client, other.headers())
    _archive(client, other.headers(), foreign)
    res = _post(client, auth_headers, customer, [_line(foreign)])
    assert res.status_code == 422, res.text
    assert "unknown reference" in res.text
    assert "archived" not in res.text.lower()


def test_ids_on_a_new_invoice_never_grant_an_archived_offering(client, tenant, auth_headers):
    customer = tenant.customer()
    archived = _product(client, auth_headers)
    _archive(client, auth_headers, archived)
    res = _post(client, auth_headers, customer, [_line(archived, line_id="00000000-0000-0000-0000-000000000000")])
    assert res.status_code == 422, res.text


def test_ids_on_a_new_invoice_are_ignored_for_active_offerings(client, tenant, auth_headers):
    customer = tenant.customer()
    active = _product(client, auth_headers)
    res = _post(client, auth_headers, customer, [_line(active, line_id="not-a-real-line")])
    assert res.status_code == 201, res.text


# --- existing invoices keep working --------------------------------------------------------------------------


def test_existing_invoice_is_still_readable_after_its_offering_is_archived(client, tenant, auth_headers):
    invoice, archived, active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    assert {i["offering_id"] for i in invoice["items"]} == {archived["id"], active["id"]}


def test_retaining_an_archived_line_with_its_id_is_accepted(client, tenant, auth_headers):
    invoice, archived, active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    items = [_line(archived, line_id=_line_id(invoice, archived)), _line(active, line_id=_line_id(invoice, active))]
    res = _patch(client, auth_headers, invoice["id"], items=items)
    assert res.status_code == 200, res.text
    assert {i["offering_id"] for i in res.json()["items"]} == {archived["id"], active["id"]}


def test_quantity_change_on_a_retained_archived_line_is_accepted(client, tenant, auth_headers):
    invoice, archived, active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    items = [_line(archived, qty="5", line_id=_line_id(invoice, archived)), _line(active)]
    res = _patch(client, auth_headers, invoice["id"], items=items)
    assert res.status_code == 200, res.text
    by_offering = {i["offering_id"]: i for i in res.json()["items"]}
    assert float(by_offering[archived["id"]]["quantity"]) == 5.0


def test_notes_only_patch_without_items_is_unchanged(client, tenant, auth_headers):
    invoice, archived, _active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    res = _patch(client, auth_headers, invoice["id"], notes="Renamed")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["notes"] == "Renamed"
    assert archived["id"] in {i["offering_id"] for i in body["items"]}


def test_offering_id_survives_an_items_patch(client, tenant, auth_headers):
    customer = tenant.customer()
    a, b = _product(client, auth_headers), _product(client, auth_headers)
    created = _post(client, auth_headers, customer, [_line(a), _line(b)])
    assert created.status_code == 201, created.text
    res = _patch(client, auth_headers, created.json()["id"], items=[_line(a, qty="2"), _line(b)])
    assert res.status_code == 200, res.text
    assert [i["offering_id"] for i in res.json()["items"]] == [a["id"], b["id"]]
    assert [i["offering_id"] for i in _get(client, auth_headers, created.json()["id"])["items"]] == [a["id"], b["id"]]


def test_archived_line_stays_linked_after_being_retained_and_saved_again(client, tenant, auth_headers):
    invoice, archived, active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    first = _patch(
        client, auth_headers, invoice["id"],
        items=[_line(archived, line_id=_line_id(invoice, archived)), _line(active)],
    )
    assert first.status_code == 200, first.text
    # The line ids were re-issued by the save; the next edit echoes the new ones and still passes.
    again = _get(client, auth_headers, invoice["id"])
    second = _patch(
        client, auth_headers, invoice["id"],
        items=[_line(archived, "3", line_id=_line_id(again, archived)), _line(active)],
    )
    assert second.status_code == 200, second.text
    assert archived["id"] in {i["offering_id"] for i in second.json()["items"]}


# --- new uses on an existing invoice ---------------------------------------------------------------------------


def test_adding_a_different_archived_offering_to_an_existing_invoice_is_rejected(client, tenant, auth_headers):
    invoice, archived, active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    other = _product(client, auth_headers)
    _archive(client, auth_headers, other)
    items = [_line(archived, line_id=_line_id(invoice, archived)), _line(active), _line(other)]
    res = _patch(client, auth_headers, invoice["id"], items=items)
    assert res.status_code == 422, res.text
    assert "items[2].offering_id" in res.text


def test_second_line_of_an_already_present_archived_offering_is_rejected(client, tenant, auth_headers):
    invoice, archived, active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    items = [_line(archived, line_id=_line_id(invoice, archived)), _line(active), _line(archived)]
    res = _patch(client, auth_headers, invoice["id"], items=items)
    assert res.status_code == 422, res.text


def test_removing_and_re_adding_an_archived_line_without_its_id_is_rejected(client, tenant, auth_headers):
    invoice, archived, active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    res = _patch(client, auth_headers, invoice["id"], items=[_line(active), _line(archived)])
    assert res.status_code == 422, res.text
    after = _get(client, auth_headers, invoice["id"])
    assert _line_id(after, archived) == _line_id(invoice, archived)  # nothing changed


def test_archived_line_submitted_without_an_id_is_rejected(client, tenant, auth_headers):
    invoice, archived, active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    res = _patch(client, auth_headers, invoice["id"], items=[_line(archived), _line(active)])
    assert res.status_code == 422, res.text
    assert "archived offering cannot be added" in res.text


# --- forged / mismatched ids -----------------------------------------------------------------------------------


def test_duplicate_claim_of_one_stored_line_id_is_rejected(client, tenant, auth_headers):
    invoice, archived, active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    stored_id = _line_id(invoice, archived)
    items = [_line(archived, line_id=stored_id), _line(archived, line_id=stored_id), _line(active)]
    res = _patch(client, auth_headers, invoice["id"], items=items)
    assert res.status_code == 422, res.text
    assert "already used" in res.text


def test_line_id_belonging_to_another_invoice_is_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    archived = _product(client, auth_headers)
    first = _post(client, auth_headers, customer, [_line(archived)])
    second = _post(client, auth_headers, customer, [_line(archived)])
    assert first.status_code == second.status_code == 201
    _archive(client, auth_headers, archived)
    first_line_id = _line_id(_get(client, auth_headers, first.json()["id"]), archived)
    res = _patch(client, auth_headers, second.json()["id"], items=[_line(archived, line_id=first_line_id)])
    assert res.status_code == 422, res.text
    assert "does not belong to this invoice" in res.text


def test_line_id_whose_stored_offering_differs_is_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    one, two = _product(client, auth_headers), _product(client, auth_headers)
    created = _post(client, auth_headers, customer, [_line(one), _line(two)])
    assert created.status_code == 201, created.text
    _archive(client, auth_headers, one)
    _archive(client, auth_headers, two)
    stored = _get(client, auth_headers, created.json()["id"])
    id_one, id_two = _line_id(stored, one), _line_id(stored, two)
    res = _patch(client, auth_headers, stored["id"], items=[_line(one, line_id=id_two), _line(two, line_id=id_one)])
    assert res.status_code == 422, res.text
    assert "different offering" in res.text


def test_two_archived_lines_each_with_their_own_id_are_both_retained(client, tenant, auth_headers):
    customer = tenant.customer()
    archived = _product(client, auth_headers)
    created = _post(client, auth_headers, customer, [_line(archived), _line(archived, qty="2")])
    assert created.status_code == 201, created.text
    _archive(client, auth_headers, archived)
    stored = _get(client, auth_headers, created.json()["id"])
    ids = [i["id"] for i in stored["items"]]
    assert len(set(ids)) == 2
    ok = _patch(client, auth_headers, stored["id"], items=[_line(archived, line_id=ids[0]), _line(archived, qty="2", line_id=ids[1])])
    assert ok.status_code == 200, ok.text
    again = _get(client, auth_headers, stored["id"])
    res = _patch(client, auth_headers, stored["id"], items=[_line(archived, line_id=again["items"][0]["id"]), _line(archived)])
    assert res.status_code == 422, res.text


# --- active offerings behave as before -------------------------------------------------------------------------


def test_active_offerings_do_not_need_ids_on_update(client, tenant, auth_headers):
    customer = tenant.customer()
    a, b = _product(client, auth_headers), _product(client, auth_headers)
    created = _post(client, auth_headers, customer, [_line(a)])
    assert created.status_code == 201, created.text
    res = _patch(client, auth_headers, created.json()["id"], items=[_line(a), _line(b, qty="3")])
    assert res.status_code == 200, res.text
    assert len(res.json()["items"]) == 2


def test_a_new_active_line_beside_a_retained_archived_line_needs_no_id(client, tenant, auth_headers):
    invoice, archived, active, _customer = _invoice_with_archived_line(client, tenant, auth_headers)
    fresh = _product(client, auth_headers)
    items = [_line(archived, line_id=_line_id(invoice, archived)), _line(active), _line(fresh)]
    res = _patch(client, auth_headers, invoice["id"], items=items)
    assert res.status_code == 200, res.text
    assert len(res.json()["items"]) == 3


# --- unarchive makes the offering usable again --------------------------------------------------------------------


def test_unarchived_offering_can_be_used_on_a_new_invoice_again(client, tenant, auth_headers):
    customer = tenant.customer()
    offering = _product(client, auth_headers)
    _archive(client, auth_headers, offering)
    assert _post(client, auth_headers, customer, [_line(offering)]).status_code == 422
    res = client.post(f"{OFFERINGS}/{offering['id']}/unarchive", headers=auth_headers)
    assert res.status_code == 200, res.text
    assert _post(client, auth_headers, customer, [_line(offering)]).status_code == 201


# --- pricing: clean 422 instead of a 500 ----------------------------------------------------------------------------


def test_pricing_calculate_of_an_archived_offering_is_a_422(client, auth_headers):
    archived = _product(client, auth_headers)
    _archive(client, auth_headers, archived)
    res = client.post(
        PRICING_CALCULATE, json={"items": [{"offering_id": archived["id"], "quantity": "1"}]}, headers=auth_headers
    )
    assert res.status_code == 422, res.text
    assert "archived" in res.text
    assert "items[0].offering_id" in res.text


def test_pricing_calculate_of_an_active_offering_is_unchanged(client, auth_headers):
    active = _product(client, auth_headers)
    res = client.post(
        PRICING_CALCULATE, json={"items": [{"offering_id": active["id"], "quantity": "2"}]}, headers=auth_headers
    )
    assert res.status_code == 200, res.text
    assert res.json()["items"][0]["offering_id"] == active["id"]


# --- system-generated invoices stay unrestricted -----------------------------------------------------------------------


def test_quote_conversion_with_an_archived_offering_still_succeeds(client, tenant, auth_headers):
    customer = tenant.customer()
    archived, other = _product(client, auth_headers), _product(client, auth_headers)
    quote = _accepted_quote(client, auth_headers, customer, [_line(archived), _line(other)])
    _archive(client, auth_headers, archived)
    res = client.post(f"{QUOTES}/{quote['id']}/convert", json={}, headers=auth_headers)
    assert res.status_code == 201, res.text
    assert archived["id"] in {i["offering_id"] for i in res.json()["items"]}


def test_subscription_renewal_invoice_for_an_archived_offering_still_succeeds(client, tenant, auth_headers, db):
    offering = _plan_offering(client, auth_headers)
    first = _subscribe(client, auth_headers, tenant.customer().id, offering_id=offering["id"])
    assert first.status_code == 201, first.text
    assert client.delete(f"{OFFERINGS}/{offering['id']}", headers=auth_headers).status_code == 204
    sub = db.get(Subscription, first.json()["id"])
    sub.next_billing_date = date.today()
    db.commit()
    assert client.post(f"{SUBS}/{sub.id}/renew", headers=auth_headers).status_code == 200
    invoices = _sub_invoices(db, sub.id)
    assert invoices, "the renewal produced no invoice"
    assert any(item.offering_id == offering["id"] for inv in invoices for item in inv.items)

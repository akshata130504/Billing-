"""Save-time validation of volume/tiered pricing brackets (same semantics the engine bills with)."""
import uuid

import pytest
from pydantic import ValidationError

from backend.app.schemas.catalog_cpq import OfferingCreate, OfferingUpdate

OFFERINGS = "/api/v1/catalog/offerings"

VALID = [{"min_qty": 1, "max_qty": 10, "unit_price": 100}, {"min_qty": 11, "max_qty": None, "unit_price": 90}]
INVALID = {
    "overlap": [{"min_qty": 1, "max_qty": 10, "unit_price": 1}, {"min_qty": 10, "max_qty": 20, "unit_price": 1}],
    "open_ended_not_last": [{"min_qty": 1, "max_qty": None, "unit_price": 1}, {"min_qty": 11, "max_qty": 20, "unit_price": 1}],
    "inverted": [{"min_qty": 5, "max_qty": 2, "unit_price": 1}],
}


def _payload(**overrides):
    data = {
        "name": f"Tiered {uuid.uuid4().hex[:6]}",
        "sku": f"TV-{uuid.uuid4().hex[:8].upper()}",
        "type": "plan",
        "category": "Subscriptions",
        "unit": "seat",
        "currency": "INR",
        "pricing_model": "volume",
        "base_price": "100.00",
        "tax_rate_pct": "18.00",
        "billing_frequency": "monthly",
        "is_active": True,
    }
    data.update(overrides)
    return data


def test_update_schema_accepts_valid_brackets():
    assert OfferingUpdate(pricing_tiers=VALID).pricing_tiers


@pytest.mark.parametrize("label", sorted(INVALID))
def test_update_schema_rejects_invalid_brackets(label):
    with pytest.raises(ValidationError):
        OfferingUpdate(pricing_tiers=INVALID[label])


def test_create_schema_rejects_overlap():
    with pytest.raises(ValidationError):
        OfferingCreate(**_payload(pricing_tiers=INVALID["overlap"]))


def test_api_rejects_overlapping_tiers_and_accepts_valid(client, auth_headers):
    bad = client.post(OFFERINGS, json=_payload(pricing_tiers=INVALID["overlap"]), headers=auth_headers)
    assert bad.status_code == 422, bad.text
    good = client.post(OFFERINGS, json=_payload(pricing_tiers=VALID), headers=auth_headers)
    assert good.status_code == 201, good.text


def test_api_update_rejects_open_ended_tier_not_last(client, auth_headers):
    created = client.post(OFFERINGS, json=_payload(pricing_tiers=VALID), headers=auth_headers)
    assert created.status_code == 201, created.text
    res = client.patch(
        f"{OFFERINGS}/{created.json()['id']}", json={"pricing_tiers": INVALID["open_ended_not_last"]}, headers=auth_headers
    )
    assert res.status_code == 422, res.text


# QA (new-bugs PDF, "Catalog - Edit Commercial Offering"): adding a pricing bracket while updating an
# offering returned 500 "An unexpected error occurred" (Decimal values written to the JSON column).
@pytest.mark.parametrize("model,brackets", [
    ("volume", [{"min_qty": 0, "max_qty": 1, "unit_price": 1000}]),
    ("tiered", [{"min_qty": 0, "max_qty": 11, "unit_price": 1000}]),
    ("tiered", [{"min_qty": 0, "max_qty": 10, "unit_price": "1000.00"}, {"min_qty": 11, "max_qty": None, "unit_price": "2500.00"}]),
])
def test_api_update_adds_valid_brackets(client, auth_headers, model, brackets):
    created = client.post(OFFERINGS, json=_payload(pricing_model="per_unit", type="service"), headers=auth_headers)
    assert created.status_code == 201, created.text
    res = client.patch(
        f"{OFFERINGS}/{created.json()['id']}",
        json={"pricing_model": model, "pricing_tiers": brackets},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    stored = res.json()["pricing_tiers"]
    assert len(stored) == len(brackets)
    assert float(stored[0]["unit_price"]) == 1000.0
    again = client.get(f"{OFFERINGS}/{created.json()['id']}", headers=auth_headers)
    assert again.json()["pricing_tiers"] == stored


# QA (new-bugs PDF, "Catalog - Price Books"): searching "science" must list only matching books.
def test_price_book_search_filters_by_name(client, auth_headers):
    tag = uuid.uuid4().hex[:6]
    for name in (f"English {tag}", f"Science {tag}", f"Test2 {tag}"):
        res = client.post(
            "/api/v1/catalog/price-books",
            json={"name": name, "currency": "INR", "customer_segment": "Enterprise", "entries": []},
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
    found = client.get("/api/v1/catalog/price-books", params={"search": f"science {tag}"}, headers=auth_headers)
    assert found.status_code == 200, found.text
    assert [b["name"] for b in found.json()["items"]] == [f"Science {tag}"]

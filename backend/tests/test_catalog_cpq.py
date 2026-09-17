"""Tests for Product Catalog, Pricing Engine, Price Books, and CPQ Deal Builder."""
import uuid
from datetime import date, timedelta
from decimal import Decimal
import pytest

from backend.app.models.catalog_cpq import OfferingType, OfferingPricingModel

CATALOG_OFFERINGS = "/api/v1/catalog/offerings"
CATALOG_PRICE_BOOKS = "/api/v1/catalog/price-books"
CPQ_SIMULATE = "/api/v1/cpq/simulate"
CPQ_RULES = "/api/v1/cpq/rules"
CPQ_DEALS = "/api/v1/cpq/deals"
CUSTOMERS = "/api/v1/customers"


def _offering(**overrides):
    data = {
        "name": "Cloud Compute Node",
        "sku": f"COMP-{uuid.uuid4().hex[:6].upper()}",
        "type": "product",
        "category": "Cloud Infrastructure",
        "unit": "instance",
        "currency": "INR",
        "pricing_model": "per_unit",
        "base_price": "5000.00",
        "tax_rate_pct": "18.00",
        "billing_frequency": "monthly",
    }
    data.update(overrides)
    return data


def test_offering_crud_and_sku_uniqueness(client, auth_headers):
    # 1. Create Offering
    sku = f"NODE-{uuid.uuid4().hex[:4].upper()}"
    resp = client.post(CATALOG_OFFERINGS, json=_offering(sku=sku, name="Dedicated Node"), headers=auth_headers)
    assert resp.status_code == 201, resp.text
    item = resp.json()
    assert item["sku"] == sku
    assert item["base_price"] == "5000.00"
    assert item["type"] == "product"

    # 2. Duplicate SKU check
    dup_resp = client.post(CATALOG_OFFERINGS, json=_offering(sku=sku.lower()), headers=auth_headers)
    assert dup_resp.status_code == 409

    # 3. Read Offering
    get_resp = client.get(f"{CATALOG_OFFERINGS}/{item['id']}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Dedicated Node"

    # 4. Update Offering
    up_resp = client.patch(f"{CATALOG_OFFERINGS}/{item['id']}", json={"base_price": "5500.00"}, headers=auth_headers)
    assert up_resp.status_code == 200
    assert up_resp.json()["base_price"] == "5500.00"

    # 5. Archive Offering
    del_resp = client.delete(f"{CATALOG_OFFERINGS}/{item['id']}", headers=auth_headers)
    assert del_resp.status_code == 204


def test_update_offering_with_pricing_brackets(client, auth_headers):
    # Create offering without pricing brackets
    resp = client.post(CATALOG_OFFERINGS, json=_offering(name="Bandwidth Tiered"), headers=auth_headers)
    assert resp.status_code == 201, resp.text
    offering_id = resp.json()["id"]

    # Update offering to add pricing brackets (verifies JSON serialization fix)
    brackets = [
        {"min_qty": 0, "max_qty": 100, "unit_price": 50.0},
        {"min_qty": 101, "max_qty": 500, "unit_price": 40.0},
        {"min_qty": 501, "max_qty": None, "unit_price": 30.0},
    ]
    up_resp = client.patch(
        f"{CATALOG_OFFERINGS}/{offering_id}",
        json={"pricing_model": "volume", "pricing_tiers": brackets},
        headers=auth_headers,
    )
    assert up_resp.status_code == 200, up_resp.text
    updated = up_resp.json()
    assert len(updated["pricing_tiers"]) == 3
    assert updated["pricing_tiers"][0]["unit_price"] == 50.0

    # Update again to modify brackets
    modified_brackets = [
        {"min_qty": 0, "max_qty": 200, "unit_price": 45.0},
    ]
    up_resp2 = client.patch(
        f"{CATALOG_OFFERINGS}/{offering_id}",
        json={"pricing_tiers": modified_brackets},
        headers=auth_headers,
    )
    assert up_resp2.status_code == 200
    assert len(up_resp2.json()["pricing_tiers"]) == 1
    assert up_resp2.json()["pricing_tiers"][0]["unit_price"] == 45.0

    # Update to clear brackets
    up_resp3 = client.patch(
        f"{CATALOG_OFFERINGS}/{offering_id}",
        json={"pricing_model": "per_unit", "pricing_tiers": []},
        headers=auth_headers,
    )
    assert up_resp3.status_code == 200
    assert up_resp3.json()["pricing_tiers"] is None


def test_pricing_engine_all_models_and_boundaries(client, auth_headers):
    # 1. Flat Model
    flat_resp = client.post(
        CATALOG_OFFERINGS,
        json=_offering(name="Setup Fee", pricing_model="flat", base_price="15000.00"),
        headers=auth_headers,
    )
    assert flat_resp.status_code == 201
    flat_id = flat_resp.json()["id"]

    sim_flat = client.post(
        CPQ_SIMULATE,
        json={"items": [{"offering_id": flat_id, "quantity": 5}]},
        headers=auth_headers,
    )
    assert sim_flat.status_code == 200
    # Flat pricing stays 15,000 regardless of quantity
    assert sim_flat.json()["items"][0]["line_subtotal"] == "15000.00"

    # 2. Volume Model:
    # 1-100 = 100, 101-500 = 80
    # 300 units = 24,000
    vol_resp = client.post(
        CATALOG_OFFERINGS,
        json=_offering(
            name="API Volume Usage",
            pricing_model="volume",
            base_price="100.00",
            pricing_tiers=[
                {"min_qty": 1, "max_qty": 100, "unit_price": 100.00},
                {"min_qty": 101, "max_qty": 500, "unit_price": 80.00},
            ],
        ),
        headers=auth_headers,
    )
    assert vol_resp.status_code == 201
    vol_id = vol_resp.json()["id"]

    # Exactly 300 units -> ₹24,000 (300 * 80)
    sim_vol_300 = client.post(
        CPQ_SIMULATE,
        json={"items": [{"offering_id": vol_id, "quantity": 300}]},
        headers=auth_headers,
    )
    assert sim_vol_300.status_code == 200
    assert sim_vol_300.json()["items"][0]["effective_unit_price"] == "80.00"
    assert sim_vol_300.json()["items"][0]["line_subtotal"] == "24000.00"

    # Exact boundary 100 units -> ₹10,000 (100 * 100)
    sim_vol_100 = client.post(
        CPQ_SIMULATE,
        json={"items": [{"offering_id": vol_id, "quantity": 100}]},
        headers=auth_headers,
    )
    assert sim_vol_100.json()["items"][0]["effective_unit_price"] == "100.00"
    assert sim_vol_100.json()["items"][0]["line_subtotal"] == "10000.00"

    # One above boundary 101 units -> ₹8,080 (101 * 80)
    sim_vol_101 = client.post(
        CPQ_SIMULATE,
        json={"items": [{"offering_id": vol_id, "quantity": 101}]},
        headers=auth_headers,
    )
    assert sim_vol_101.json()["items"][0]["effective_unit_price"] == "80.00"
    assert sim_vol_101.json()["items"][0]["line_subtotal"] == "8080.00"

    # 3. Tiered Model:
    # 1-100 = 100
    # 101-200 = 80
    # 201-300 = 60
    # 300 units: 100x100 + 100x80 + 100x60 = 24,000
    tier_resp = client.post(
        CATALOG_OFFERINGS,
        json=_offering(
            name="Storage Tiered",
            pricing_model="tiered",
            base_price="100.00",
            pricing_tiers=[
                {"min_qty": 1, "max_qty": 100, "unit_price": 100.00},
                {"min_qty": 101, "max_qty": 200, "unit_price": 80.00},
                {"min_qty": 201, "max_qty": 300, "unit_price": 60.00},
            ],
        ),
        headers=auth_headers,
    )
    assert tier_resp.status_code == 201
    tier_id = tier_resp.json()["id"]

    sim_tier_300 = client.post(
        CPQ_SIMULATE,
        json={"items": [{"offering_id": tier_id, "quantity": 300}]},
        headers=auth_headers,
    )
    assert sim_tier_300.status_code == 200
    # Tiered 300 units = 100*100 + 100*80 + 100*60 = 24000
    assert sim_tier_300.json()["items"][0]["line_subtotal"] == "24000.00"

    # Tiered 150 units = 100*100 + 50*80 = 10000 + 4000 = 14,000
    sim_tier_150 = client.post(
        CPQ_SIMULATE,
        json={"items": [{"offering_id": tier_id, "quantity": 150}]},
        headers=auth_headers,
    )
    assert sim_tier_150.json()["items"][0]["line_subtotal"] == "14000.00"

    # 4. Zero and negative quantity API validation (Pydantic gt=0 returns 422)
    sim_zero = client.post(
        CPQ_SIMULATE,
        json={"items": [{"offering_id": vol_id, "quantity": 0}]},
        headers=auth_headers,
    )
    assert sim_zero.status_code == 422

    sim_neg = client.post(
        CPQ_SIMULATE,
        json={"items": [{"offering_id": vol_id, "quantity": -5}]},
        headers=auth_headers,
    )
    assert sim_neg.status_code == 422

    # 5. Direct engine test for zero and negative quantity
    from backend.app.services.pricing_engine import calculate_line_item_pricing
    from backend.app.models.catalog_cpq import Offering
    mock_off = Offering(name="Test", base_price=Decimal("100"), tax_rate_pct=Decimal("18"), is_active=True, pricing_model=OfferingPricingModel.PER_UNIT)
    calc_0 = calculate_line_item_pricing(mock_off, Decimal("0"))
    assert calc_0["subtotal"] == Decimal("0.00")
    with pytest.raises(ValueError, match="non-negative"):
        calculate_line_item_pricing(mock_off, Decimal("-1"))


def test_cpq_rules_and_approval_workflow(client, auth_headers):
    # 1. Create Offerings A and B
    off_a = client.post(CATALOG_OFFERINGS, json=_offering(name="Firewall Appliance"), headers=auth_headers).json()
    off_b = client.post(CATALOG_OFFERINGS, json=_offering(name="Security License"), headers=auth_headers).json()

    # 2. Create REQUIRES Rule: Appliance requires License
    rule_resp = client.post(
        CPQ_RULES,
        json={
            "name": "Firewall requires Security License",
            "rule_type": "requires",
            "conditions": {"offering_id": off_a["id"]},
            "actions": {"requires_offering_id": off_b["id"], "message": "Security License is mandatory."},
        },
        headers=auth_headers,
    )
    assert rule_resp.status_code == 201

    # 3. Simulate with only Appliance -> Rule warning generated
    sim_warn = client.post(
        CPQ_SIMULATE,
        json={"items": [{"offering_id": off_a["id"], "quantity": 1}]},
        headers=auth_headers,
    )
    assert sim_warn.status_code == 200
    assert len(sim_warn.json()["rule_warnings"]) > 0
    assert "requires" in sim_warn.json()["rule_warnings"][0]

    # 4. Create Customer
    cust = client.post(CUSTOMERS, json={"display_name": "MegaCorp Ltd", "currency": "INR"}, headers=auth_headers).json()

    # 5. Deal with excessive discount (25%) -> triggers approval_required
    deal_resp = client.post(
        CPQ_DEALS,
        json={
            "title": "Discounted Hardware Deal",
            "customer_id": cust["id"],
            "discount_pct": 25,
            "items": [{"offering_id": off_a["id"], "quantity": 1}],
        },
        headers=auth_headers,
    )
    assert deal_resp.status_code == 201
    deal = deal_resp.json()
    assert deal["approval_required"] is True
    assert deal["status"] == "pending_approval"

    # 6. Approve the deal
    appr_resp = client.post(f"{CPQ_DEALS}/{deal['id']}/approve", headers=auth_headers)
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "approved"
    assert appr_resp.json()["approval_status"] == "approved"


def test_tenant_isolation_and_security(client, tenant, db):
    from backend.tests.conftest import Tenant
    tenant_b = Tenant(db, "other")
    headers_a = tenant.headers()
    headers_b = tenant_b.headers()

    # Create offering in Tenant A
    off_a = client.post(CATALOG_OFFERINGS, json=_offering(name="Secret Tenant A Offering"), headers=headers_a).json()

    # Tenant B should NOT be able to view or modify it
    get_b = client.get(f"{CATALOG_OFFERINGS}/{off_a['id']}", headers=headers_b)
    assert get_b.status_code == 404

    patch_b = client.patch(f"{CATALOG_OFFERINGS}/{off_a['id']}", json={"name": "Hacked"}, headers=headers_b)
    assert patch_b.status_code == 404

    del_b = client.delete(f"{CATALOG_OFFERINGS}/{off_a['id']}", headers=headers_b)
    assert del_b.status_code == 404

    # Unauthenticated request fails
    unauth = client.get(CATALOG_OFFERINGS)
    assert unauth.status_code in (401, 403)


def test_price_book_and_cpq_deal_flow(client, auth_headers):
    # 1. Create customer
    cust_resp = client.post(
        CUSTOMERS,
        json={"display_name": "Apex Enterprise Corp", "currency": "INR"},
        headers=auth_headers,
    )
    assert cust_resp.status_code == 201
    customer_id = cust_resp.json()["id"]

    # 2. Create offering
    off_resp = client.post(CATALOG_OFFERINGS, json=_offering(base_price="10000.00"), headers=auth_headers)
    assert off_resp.status_code == 201
    offering_id = off_resp.json()["id"]

    # 3. Create Price Book with 10% discount override
    pb_resp = client.post(
        CATALOG_PRICE_BOOKS,
        json={
            "name": f"Enterprise Partner List {uuid.uuid4().hex[:4]}",
            "currency": "INR",
            "customer_segment": "Enterprise",
            "entries": [{"offering_id": offering_id, "discount_pct": 10}],
        },
        headers=auth_headers,
    )
    assert pb_resp.status_code == 201
    pb_id = pb_resp.json()["id"]

    # 4. Create CPQ Deal using this Price Book
    deal_resp = client.post(
        CPQ_DEALS,
        json={
            "title": "Enterprise Cloud Setup 2026",
            "customer_id": customer_id,
            "price_book_id": pb_id,
            "discount_pct": 5,
            "items": [{"offering_id": offering_id, "quantity": 2, "discount_pct": 0}],
        },
        headers=auth_headers,
    )
    assert deal_resp.status_code == 201
    deal = deal_resp.json()
    assert deal["deal_number"].startswith("DEAL-")
    assert deal["items"][0]["unit_price"] == "9000.00"
    assert deal["pricing_explanation"] is not None

    # 5. Convert Deal to Quote
    convert_resp = client.post(f"{CPQ_DEALS}/{deal['id']}/convert-quote", headers=auth_headers)
    assert convert_resp.status_code == 200
    quote = convert_resp.json()
    assert quote["quote_number"].startswith("QT-")
    assert quote["customer"]["id"] == customer_id
    assert len(quote["items"]) == 1
    assert quote["items"][0]["unit_price"] == "9000.00"


def test_package_pricing_model_and_boundary_cases(client, auth_headers):
    """Specific verification for PACKAGE pricing model independent of BUNDLE offering type."""
    from backend.app.services.pricing_engine import calculate_line_item_pricing
    from backend.app.models.catalog_cpq import Offering, OfferingPricingModel

    # 1. Create a Product with PACKAGE pricing model (not a bundle)
    # Tiers: 10 units = ₹5,000; 25 units = ₹10,000; 50 units = ₹18,000
    pkg_sku = f"PKG-{uuid.uuid4().hex[:4].upper()}"
    pkg_resp = client.post(
        CATALOG_OFFERINGS,
        json=_offering(
            name="Bulk API Request Package",
            sku=pkg_sku,
            type="product",  # Normal Product, NOT bundle
            pricing_model="package",
            base_price="5000.00",
            pricing_tiers=[
                {"package_qty": 10, "package_price": 5000.00},
                {"package_qty": 25, "package_price": 10000.00},
                {"package_qty": 50, "package_price": 18000.00},
            ],
        ),
        headers=auth_headers,
    )
    assert pkg_resp.status_code == 201, pkg_resp.text
    pkg_offering = pkg_resp.json()
    pkg_id = pkg_offering["id"]
    assert pkg_offering["pricing_model"] == "package"
    assert pkg_offering["type"] == "product"

    # 2. Test exact package quantities via CPQ simulation API
    # Exact 10 units -> ₹5,000
    sim_10 = client.post(CPQ_SIMULATE, json={"items": [{"offering_id": pkg_id, "quantity": 10}]}, headers=auth_headers)
    assert sim_10.status_code == 200
    assert sim_10.json()["items"][0]["line_subtotal"] == "5000.00"
    assert sim_10.json()["items"][0]["effective_unit_price"] == "500.00"

    # Exact 25 units -> ₹10,000
    sim_25 = client.post(CPQ_SIMULATE, json={"items": [{"offering_id": pkg_id, "quantity": 25}]}, headers=auth_headers)
    assert sim_25.status_code == 200
    assert sim_25.json()["items"][0]["line_subtotal"] == "10000.00"
    assert sim_25.json()["items"][0]["effective_unit_price"] == "400.00"

    # Exact 50 units -> ₹18,000
    sim_50 = client.post(CPQ_SIMULATE, json={"items": [{"offering_id": pkg_id, "quantity": 50}]}, headers=auth_headers)
    assert sim_50.status_code == 200
    assert sim_50.json()["items"][0]["line_subtotal"] == "18000.00"
    assert sim_50.json()["items"][0]["effective_unit_price"] == "360.00"

    # 3. Test quantities between package options
    # 7 units (<= 10) -> covered by 10-unit package -> ₹5,000
    sim_7 = client.post(CPQ_SIMULATE, json={"items": [{"offering_id": pkg_id, "quantity": 7}]}, headers=auth_headers)
    assert sim_7.status_code == 200
    assert sim_7.json()["items"][0]["line_subtotal"] == "5000.00"

    # 15 units (10 < qty <= 25) -> covered by 25-unit package -> ₹10,000
    sim_15 = client.post(CPQ_SIMULATE, json={"items": [{"offering_id": pkg_id, "quantity": 15}]}, headers=auth_headers)
    assert sim_15.status_code == 200
    assert sim_15.json()["items"][0]["line_subtotal"] == "10000.00"

    # 35 units (25 < qty <= 50) -> covered by 50-unit package -> ₹18,000
    sim_35 = client.post(CPQ_SIMULATE, json={"items": [{"offering_id": pkg_id, "quantity": 35}]}, headers=auth_headers)
    assert sim_35.status_code == 200
    assert sim_35.json()["items"][0]["line_subtotal"] == "18000.00"

    # 4. Large quantity test (exceeding largest package)
    # 60 units -> 1x 50-unit package (₹18,000) + 1x 10-unit package (₹5,000) = ₹23,000
    sim_60 = client.post(CPQ_SIMULATE, json={"items": [{"offering_id": pkg_id, "quantity": 60}]}, headers=auth_headers)
    assert sim_60.status_code == 200
    assert sim_60.json()["items"][0]["line_subtotal"] == "23000.00"

    # 100 units -> 2x 50-unit packages = ₹36,000
    sim_100 = client.post(CPQ_SIMULATE, json={"items": [{"offering_id": pkg_id, "quantity": 100}]}, headers=auth_headers)
    assert sim_100.status_code == 200
    assert sim_100.json()["items"][0]["line_subtotal"] == "36000.00"

    # 5. Invalid and zero quantity tests
    sim_zero = client.post(CPQ_SIMULATE, json={"items": [{"offering_id": pkg_id, "quantity": 0}]}, headers=auth_headers)
    assert sim_zero.status_code == 422

    sim_neg = client.post(CPQ_SIMULATE, json={"items": [{"offering_id": pkg_id, "quantity": -3}]}, headers=auth_headers)
    assert sim_neg.status_code == 422

    # Direct engine calculation test for zero and negative
    mock_pkg_off = Offering(
        name="Mock Pkg",
        base_price=Decimal("5000"),
        tax_rate_pct=Decimal("18"),
        is_active=True,
        pricing_model=OfferingPricingModel.PACKAGE,
        pricing_tiers=[
            {"package_qty": 10, "package_price": 5000},
            {"package_qty": 25, "package_price": 10000},
            {"package_qty": 50, "package_price": 18000},
        ],
    )
    engine_zero = calculate_line_item_pricing(mock_pkg_off, Decimal("0"))
    assert engine_zero["subtotal"] == Decimal("0.00")
    with pytest.raises(ValueError, match="non-negative"):
        calculate_line_item_pricing(mock_pkg_off, Decimal("-1"))

    # 6. CPQ Deal creation with PACKAGE model offering
    cust = client.post(CUSTOMERS, json={"display_name": "Package Test Customer", "currency": "INR"}, headers=auth_headers).json()
    deal_resp = client.post(
        CPQ_DEALS,
        json={
            "title": "Package Pricing Deal",
            "customer_id": cust["id"],
            "items": [{"offering_id": pkg_id, "quantity": 25}],
        },
        headers=auth_headers,
    )
    assert deal_resp.status_code == 201
    deal = deal_resp.json()
    assert deal["subtotal"] == "10000.00"
    assert "Package option" in deal["pricing_explanation"]["items"][0]["volume_tier_applied"]

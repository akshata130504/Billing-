"""Volume / graduated tier pricing: boundaries, gaps, fractional quantities,
invalid configurations and an end-to-end quantity -> invoice total check."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.models.catalog_cpq import Offering
from backend.app.services.pricing_engine import (
    calculate_line_item_pricing,
    currency_symbol,
    validate_pricing_tiers,
)

BRACKETS = [
    {"min_qty": 1, "max_qty": 10, "unit_price": 100},
    {"min_qty": 11, "max_qty": 50, "unit_price": 80},
    {"min_qty": 51, "max_qty": None, "unit_price": 60},
]
CLOSED_BRACKETS = [
    {"min_qty": 1, "max_qty": 10, "unit_price": 100},
    {"min_qty": 11, "max_qty": 50, "unit_price": 80},
]


def _offering(model: str, tiers, base="999.00", currency="INR", tax="0") -> Offering:
    return Offering(
        organization_id="org",
        name=f"{model} offering",
        sku=f"SKU-{model}",
        type="plan",
        pricing_model=model,
        base_price=Decimal(base),
        tax_rate_pct=Decimal(tax),
        currency=currency,
        is_active=True,
        pricing_tiers=tiers,
    )


def _price(model, tiers, qty, **kw):
    return calculate_line_item_pricing(_offering(model, tiers, **kw), Decimal(str(qty)))


# ---------------------------------------------------------------- volume
@pytest.mark.parametrize(
    "qty,unit",
    [
        ("0.5", "100.00"),  # below the first bracket -> first bracket
        ("1", "100.00"),  # exactly the first boundary
        ("5", "100.00"),
        ("10", "100.00"),  # exact upper boundary stays in the lower bracket
        ("10.5", "80.00"),  # fractional gap between 10 and 11 -> next bracket (was base price 999)
        ("10.01", "80.00"),
        ("11", "80.00"),
        ("50", "80.00"),
        ("50.5", "60.00"),  # gap between the final two brackets
        ("51", "60.00"),
        ("10000", "60.00"),  # open-ended final bracket
    ],
)
def test_volume_bracket_selection(qty, unit):
    res = _price("volume", BRACKETS, qty)
    assert res["unit_price"] == Decimal(unit)
    assert res["subtotal"] == (Decimal(unit) * Decimal(qty)).quantize(Decimal("0.01"))


def test_volume_integer_gap_between_brackets_uses_next_bracket():
    tiers = [{"min_qty": 1, "max_qty": 10, "unit_price": 100}, {"min_qty": 15, "max_qty": None, "unit_price": 70}]
    assert _price("volume", tiers, 12)["unit_price"] == Decimal("70.00")


def test_volume_above_closed_final_bracket_uses_final_bracket_rate():
    res = _price("volume", CLOSED_BRACKETS, 75)
    assert res["unit_price"] == Decimal("80.00")
    assert res["subtotal"] == Decimal("6000.00")
    assert "final bracket" in res["explanation"]["tier_explanation"]


def test_volume_no_tiers_uses_base_price():
    for tiers in (None, []):
        res = _price("volume", tiers, 7, base="12.50")
        assert res["unit_price"] == Decimal("12.50")
        assert res["subtotal"] == Decimal("87.50")


def test_volume_tier_order_does_not_matter():
    assert _price("volume", list(reversed(BRACKETS)), 20)["unit_price"] == Decimal("80.00")


# ---------------------------------------------------------------- graduated
@pytest.mark.parametrize(
    "qty,subtotal",
    [
        ("0.5", "50.00"),  # below first bracket: priced in first bracket
        ("1", "100.00"),
        ("10", "1000.00"),  # exact boundary
        ("10.5", "1040.00"),  # 10 @100 + 0.5 @80 (fractional gap)
        ("11", "1080.00"),
        ("25", "2200.00"),  # 10 @100 + 15 @80
        ("50", "4200.00"),  # 10 @100 + 40 @80
        ("50.5", "4230.00"),  # + 0.5 @60
        ("60", "4800.00"),  # 10 @100 + 40 @80 + 10 @60
    ],
)
def test_graduated_tiers(qty, subtotal):
    assert _price("tiered", BRACKETS, qty)["subtotal"] == Decimal(subtotal)


def test_graduated_above_closed_final_bracket_prices_excess_at_final_rate():
    # Previously the 25 units above 50 were silently dropped from the subtotal.
    res = _price("tiered", CLOSED_BRACKETS, 75)
    assert res["subtotal"] == Decimal("6200.00")  # 10@100 + 40@80 + 25@80
    assert "above final bracket" in res["explanation"]["tier_explanation"]


def test_graduated_legacy_expectations_are_unchanged():
    tiers = [
        {"min_qty": 1, "max_qty": 10, "unit_price": 10},
        {"min_qty": 11, "max_qty": 20, "unit_price": 8},
        {"min_qty": 21, "max_qty": None, "unit_price": 5},
    ]
    assert _price("tiered", tiers, 25)["subtotal"] == Decimal("205.00")
    zero_based = [{"min_qty": 0, "max_qty": 100, "unit_price": 1}, {"min_qty": 101, "max_qty": None, "unit_price": 0.5}]
    assert _price("tiered", zero_based, 150)["subtotal"] == Decimal("125.00")


def test_graduated_no_tiers_uses_base_price():
    assert _price("tiered", [], 4, base="10")["subtotal"] == Decimal("40.00")


# ---------------------------------------------------------------- invalid tiers
def test_invalid_tiers_are_rejected_at_configuration_time():
    with pytest.raises(ValueError, match="overlap"):
        validate_pricing_tiers([{"min_qty": 1, "max_qty": 10}, {"min_qty": 5, "max_qty": 20}])
    with pytest.raises(ValueError, match="overlap"):
        validate_pricing_tiers([{"min_qty": 0, "max_qty": 10}, {"min_qty": 10, "max_qty": 20}])
    with pytest.raises(ValueError, match="max_qty"):
        validate_pricing_tiers([{"min_qty": 10, "max_qty": 5}])
    with pytest.raises(ValueError, match="open-ended"):
        validate_pricing_tiers([{"min_qty": 1}, {"min_qty": 11, "max_qty": 20}])
    with pytest.raises(ValueError, match="non-negative"):
        validate_pricing_tiers([{"min_qty": 1, "max_qty": 2, "unit_price": -1}])
    # valid configurations pass (including gaps and package-style tiers)
    validate_pricing_tiers(BRACKETS)
    validate_pricing_tiers([{"min_qty": 1, "max_qty": 10}, {"min_qty": 15}])
    validate_pricing_tiers([{"package_qty": 10, "package_price": 5}, {"package_qty": 25, "package_price": 9}])
    validate_pricing_tiers(None)


def test_invalid_stored_tiers_price_deterministically():
    overlapping = [
        {"min_qty": 5, "max_qty": 20, "unit_price": 70},
        {"min_qty": 1, "max_qty": 10, "unit_price": 100},
        {"min_qty": 2, "max_qty": 8, "unit_price": 1},  # fully covered by 1-10: ignored
        {"min_qty": 9, "max_qty": 3, "unit_price": 1},  # inverted: ignored
    ]
    first = _price("volume", overlapping, 8)
    assert first["unit_price"] == Decimal("100.00")  # lower bracket wins
    assert _price("volume", list(reversed(overlapping)), 8)["unit_price"] == Decimal("100.00")
    assert _price("volume", overlapping, 15)["unit_price"] == Decimal("70.00")
    # graduated: 10 @100 then (10, 20] @70
    assert _price("tiered", overlapping, 15)["subtotal"] == Decimal("1350.00")
    # everything after an open-ended bracket is ignored
    two_open = [{"min_qty": 1, "unit_price": 50}, {"min_qty": 100, "unit_price": 1}]
    assert _price("volume", two_open, 500)["unit_price"] == Decimal("50.00")
    # tiers that are all invalid fall back to the base price
    assert _price("volume", [{"min_qty": 9, "max_qty": 3, "unit_price": 1}], 4, base="7")["unit_price"] == Decimal("7.00")


def test_explanations_use_offering_currency_symbol():
    usd = _price("volume", BRACKETS, 20, currency="USD")
    assert "$80" in usd["explanation"]["tier_explanation"]
    assert "₹" not in usd["explanation"]["tier_explanation"]
    eur = _price("tiered", BRACKETS, 20, currency="EUR")
    assert "€" in eur["explanation"]["tier_explanation"] and "₹" not in eur["explanation"]["tier_explanation"]
    assert currency_symbol("INR") == "₹"
    assert currency_symbol("XYZ") == "XYZ "


# ---------------------------------------------------------------- end to end
def test_quantity_to_invoice_total_end_to_end(client, tenant, db):
    customer = tenant.customer()
    offering = Offering(
        organization_id=tenant.organization.id,
        name="Seats",
        sku="SEATS-E2E",
        type="plan",
        pricing_model="volume",
        base_price=Decimal("999.00"),
        tax_rate_pct=Decimal("18.00"),
        currency="INR",
        is_active=True,
        pricing_tiers=BRACKETS,
    )
    db.add(offering)
    db.commit()
    headers = tenant.headers()

    sim = client.post(
        "/api/v1/pricing/simulate",
        json={"offering_id": offering.id, "quantity": "10.5", "discount_pct": "10"},
        headers=headers,
    )
    assert sim.status_code == 200, sim.text
    body = sim.json()
    # 10.5 falls between 1-10 and 11-50 -> bracket 11-50 @ 80
    assert body["effective_unit_price"] == "80.00"
    assert body["subtotal"] == "840.00"
    assert body["discount_amount"] == "84.00"
    assert body["tax_amount"] == "136.08"  # 18% GST on 756.00
    assert body["total_amount"] == "892.08"

    inv = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": customer.id,
            "issue_date": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "currency": "INR",
            "discount_pct": "10",
            "items": [
                {
                    "offering_id": offering.id,
                    "description": "Seats",
                    "quantity": "10.5",
                    "unit_price": body["effective_unit_price"],
                    "tax_rate_pct": "18",
                    "pricing_explanation": body["explanation"]["tier_explanation"],
                }
            ],
        },
        headers=headers,
    )
    assert inv.status_code in (200, 201), inv.text
    invoice = inv.json()
    assert Decimal(str(invoice["subtotal"])) == Decimal("840.00")
    assert Decimal(str(invoice["discount_amount"])) == Decimal("84.00")
    assert Decimal(str(invoice["tax_amount"])) == Decimal("136.08")
    assert Decimal(str(invoice["total"])) == Decimal(body["total_amount"])


def test_simulate_without_offering_returns_422(client, tenant):
    res = client.post("/api/v1/pricing/simulate", json={"quantity": "1"}, headers=tenant.headers())
    assert res.status_code == 422

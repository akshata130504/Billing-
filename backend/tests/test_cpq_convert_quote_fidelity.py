"""A quote converted from a CPQ deal keeps the deal's terms when it is opened and saved in the editor.

QA (new-bugs PDF, "Quotes - Edit Quote"): editing a converted quote cleared the expiry date, showed
the overall discount as 0% and lost the line discounts, so saving repriced the quote.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

CATALOG_OFFERINGS = "/api/v1/catalog/offerings"
CPQ_DEALS = "/api/v1/cpq/deals"
CUSTOMERS = "/api/v1/customers"
QUOTES = "/api/v1/quotes"


def _offering(client, headers, price):
    body = {
        "name": f"Offering {uuid.uuid4().hex[:6]}", "sku": f"SKU-{uuid.uuid4().hex[:6].upper()}",
        "type": "service", "category": "General", "unit": "unit", "currency": "INR",
        "pricing_model": "per_unit", "base_price": price, "tax_rate_pct": "18.00", "billing_frequency": "one_time",
    }
    res = client.post(CATALOG_OFFERINGS, json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _converted_quote(client, headers):
    a = _offering(client, headers, "1000.00")
    b = _offering(client, headers, "100.00")
    customer = client.post(CUSTOMERS, json={"display_name": "Academy Ltd", "currency": "INR"}, headers=headers).json()
    deal = client.post(CPQ_DEALS, json={
        "title": "Academy", "customer_id": customer["id"], "discount_pct": 3,
        "items": [
            {"offering_id": a["id"], "quantity": 4, "discount_pct": 5},
            {"offering_id": b["id"], "quantity": 2, "discount_pct": 2},
        ],
    }, headers=headers)
    assert deal.status_code == 201, deal.text
    assert deal.json()["approval_required"] is False
    res = client.post(f"{CPQ_DEALS}/{deal.json()['id']}/convert-quote", headers=headers)
    assert res.status_code == 200, res.text
    return client.get(f"{QUOTES}/{res.json()['id']}", headers=headers).json()


def test_converted_quote_carries_line_discounts_validity_and_terms(client, auth_headers):
    quote = _converted_quote(client, auth_headers)

    # Line discounts are applied to each line's unit price; the deal discount stays the quote discount.
    prices = sorted(Decimal(i["unit_price"]) for i in quote["items"])
    assert prices == [Decimal("98.00"), Decimal("950.00")]
    assert Decimal(quote["subtotal"]) == Decimal("3996.00")
    assert Decimal(quote["discount_pct"]) == Decimal("3")
    assert Decimal(quote["discount_amount"]) == Decimal("119.88")
    assert all(i["offering_id"] for i in quote["items"])

    issue = date.fromisoformat(quote["issue_date"])
    assert date.fromisoformat(quote["expiry_date"]) == issue + timedelta(days=30)
    assert "Quote valid for 30 days" in (quote["terms"] or "")


def test_saving_a_converted_quote_in_the_editor_does_not_reprice_it(client, auth_headers):
    quote = _converted_quote(client, auth_headers)
    # What the quote editor sends back when the user opens the quote and saves without changes.
    body = {
        "title": quote["title"], "issue_date": quote["issue_date"], "expiry_date": quote["expiry_date"],
        "currency": quote["currency"], "discount_pct": quote["discount_pct"], "notes": quote["notes"],
        "terms": quote["terms"],
        "items": [
            {k: item[k] for k in ("offering_id", "description", "quantity", "unit_price", "tax_rate_pct")}
            for item in quote["items"]
        ],
    }
    res = client.patch(f"{QUOTES}/{quote['id']}", json=body, headers=auth_headers)
    assert res.status_code == 200, res.text
    saved = res.json()
    for field in ("subtotal", "discount_pct", "discount_amount", "tax_amount", "total"):
        assert Decimal(saved[field]) == Decimal(quote[field]), field


def test_deal_line_quantity_is_bounded(client, auth_headers):
    a = _offering(client, auth_headers, "10.00")
    customer = client.post(CUSTOMERS, json={"display_name": "Bulk Buyer", "currency": "INR"}, headers=auth_headers).json()
    res = client.post(CPQ_DEALS, json={
        "title": "Huge", "customer_id": customer["id"],
        "items": [{"offering_id": a["id"], "quantity": 187654446786545}],
    }, headers=auth_headers)
    assert res.status_code == 422, res.text

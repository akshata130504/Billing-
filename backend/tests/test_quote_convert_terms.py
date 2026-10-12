"""BUG-28: an invoice converted from a quote must not say "Quote valid for 30 days".

Also BUG-07 at conversion: an organization without a GSTIN invoices without GST.
"""
from decimal import Decimal

BASE = "/api/v1/quotes"
QUOTE_TERMS = (
    "1. Quote valid for 30 days.\n"
    "2. Payment terms: 30 days from invoice date.\n"
    "3. Taxes as applicable per Indian GST."
)


def _accepted_quote(client, headers, customer, **extra):
    body = {
        "customer_id": customer.id,
        "items": [{"description": "Build", "quantity": "1", "unit_price": "1000", "tax_rate_pct": "18"}],
        **extra,
    }
    quote = client.post(BASE, json=body, headers=headers)
    assert quote.status_code == 201, quote.text
    quote = quote.json()
    assert client.post(f"{BASE}/{quote['id']}/send", headers=headers).status_code == 200
    resp = client.post(f"{BASE}/{quote['id']}/mark-accepted", json={"reason": "Signed"}, headers=headers)
    assert resp.status_code == 200, resp.text
    return quote


def _convert(client, headers, quote):
    resp = client.post(f"{BASE}/{quote['id']}/convert", json={}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_converted_invoice_drops_the_quote_validity_sentence(client, tenant, auth_headers):
    customer = tenant.customer()
    quote = _accepted_quote(client, auth_headers, customer, terms=QUOTE_TERMS)
    invoice = _convert(client, auth_headers, quote)
    assert "valid for" not in (invoice["terms"] or "").lower()
    assert invoice["terms"] == (
        "1. Payment terms: 30 days from invoice date.\n"
        "2. Taxes as applicable per Indian GST."
    )


def test_converted_invoice_uses_the_organization_invoice_terms(client, tenant, auth_headers, db):
    tenant.organization.invoice_terms = "Pay by bank transfer within 15 days."
    db.commit()
    customer = tenant.customer()
    quote = _accepted_quote(client, auth_headers, customer, terms=QUOTE_TERMS)
    invoice = _convert(client, auth_headers, quote)
    assert invoice["terms"] == "Pay by bank transfer within 15 days."


def test_quote_converted_after_gstin_removed_invoices_without_gst(client, tenant, auth_headers, db):
    customer = tenant.customer(billing_state="Karnataka", billing_country="IN")
    quote = _accepted_quote(client, auth_headers, customer)
    assert Decimal(quote["tax_amount"]) == Decimal("180.00")

    tenant.organization.gstin = None
    db.commit()
    invoice = _convert(client, auth_headers, quote)
    assert Decimal(invoice["tax_amount"]) == Decimal("0.00")
    assert Decimal(invoice["total"]) == Decimal("1000.00")
    assert Decimal(invoice["amount_due"]) == Decimal("1000.00")
    assert all(Decimal(i["tax_rate_pct"]) == 0 for i in invoice["items"])

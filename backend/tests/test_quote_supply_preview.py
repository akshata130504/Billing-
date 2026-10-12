"""BUG-08 / BUG-07: form previews use the server's own GST rule, and no GSTIN means no GST.

The quote form used to hard-code CGST 9% + SGST 9% while the server saved IGST (seller
state unknown) - the form now asks the server. Product decision for BUG-07: an
organization without a GSTIN cannot charge GST, so its documents carry no tax at all.
"""
from decimal import Decimal

from backend.app.models import Invoice, Organization
from backend.app.services.invoice_pdf import render_invoice_pdf

KA_ORG_GSTIN = "29AAFCB9900V1Z8"
MH_CUST_GSTIN = "27AABCB1234F1Z5"
LINE = {"description": "Consulting", "quantity": 1, "unit_price": "1000", "tax_rate_pct": 18}


def _registered(tenant, db):
    tenant.organization.gstin = KA_ORG_GSTIN
    tenant.organization.state = "Karnataka"
    tenant.organization.country = "IN"
    db.commit()


def _unregistered(tenant, db):
    tenant.organization.gstin = None
    tenant.organization.state = "Karnataka"
    tenant.organization.country = "IN"
    db.commit()


def _preview(client, headers, customer_id):
    res = client.get("/api/v1/quotes/supply-preview", headers=headers, params={"customer_id": customer_id})
    assert res.status_code == 200, res.text
    return res.json()


def _post(client, headers, path, customer_id):
    res = client.post(path, headers=headers, json={"customer_id": customer_id, "items": [LINE]})
    assert res.status_code == 201, res.text
    return res.json()


def test_registered_same_state_previews_and_saves_cgst_sgst(client, tenant, auth_headers, db):
    _registered(tenant, db)
    customer = tenant.customer(billing_state="Karnataka", billing_country="IN")

    preview = _preview(client, auth_headers, customer.id)
    assert preview["supply_type"] == "intra_state"
    assert preview["charges_gst"] is True
    assert preview["place_of_supply_name"] == "Karnataka"

    for path in ("/api/v1/quotes", "/api/v1/invoices"):
        saved = _post(client, auth_headers, path, customer.id)
        assert saved["supply_type"] == "intra_state"
        assert Decimal(saved["cgst_amount"]) == Decimal(saved["sgst_amount"]) == Decimal("90.00")
        assert Decimal(saved["tax_amount"]) == Decimal("180.00")


def test_registered_other_state_previews_and_saves_igst(client, tenant, auth_headers, db):
    _registered(tenant, db)
    customer = tenant.customer(gstin=MH_CUST_GSTIN, billing_state="Maharashtra", billing_country="IN")

    preview = _preview(client, auth_headers, customer.id)
    assert preview["supply_type"] == "inter_state"
    assert preview["charges_gst"] is True

    for path in ("/api/v1/quotes", "/api/v1/invoices"):
        saved = _post(client, auth_headers, path, customer.id)
        assert Decimal(saved["igst_amount"]) == Decimal("180.00")
        assert Decimal(saved["cgst_amount"]) == Decimal("0.00")


def test_no_gstin_means_no_gst_on_quotes_and_invoices(client, tenant, auth_headers, db):
    _unregistered(tenant, db)
    customer = tenant.customer(billing_state="Karnataka", billing_country="IN")

    assert _preview(client, auth_headers, customer.id)["charges_gst"] is False

    for path in ("/api/v1/quotes", "/api/v1/invoices"):
        saved = _post(client, auth_headers, path, customer.id)
        assert Decimal(saved["tax_amount"]) == Decimal("0.00"), path
        assert Decimal(saved["cgst_amount"]) == Decimal(saved["sgst_amount"]) == Decimal(saved["igst_amount"]) == 0
        assert Decimal(saved["total"]) == Decimal("1000.00"), path


def _pdf_texts(db, invoice_id, monkeypatch):
    import backend.app.services.invoice_pdf as invoice_pdf

    texts = []
    real = invoice_pdf._p

    def spy(text, style):
        texts.append(str(text))
        return real(text, style)

    monkeypatch.setattr(invoice_pdf, "_p", spy)
    invoice = db.get(Invoice, invoice_id)
    assert render_invoice_pdf(invoice, db.get(Organization, invoice.organization_id)).startswith(b"%PDF")
    return texts


def test_no_gstin_invoice_pdf_is_a_bill_of_supply(client, tenant, auth_headers, db, monkeypatch):
    _unregistered(tenant, db)
    customer = tenant.customer(billing_state="Karnataka", billing_country="IN")
    saved = _post(client, auth_headers, "/api/v1/invoices", customer.id)
    texts = _pdf_texts(db, saved["id"], monkeypatch)
    assert any("BILL OF SUPPLY" in t for t in texts)
    assert not any("TAX INVOICE" in t for t in texts)


def test_registered_invoice_pdf_is_a_tax_invoice(client, tenant, auth_headers, db, monkeypatch):
    _registered(tenant, db)
    customer = tenant.customer(billing_state="Karnataka", billing_country="IN")
    saved = _post(client, auth_headers, "/api/v1/invoices", customer.id)
    assert any("TAX INVOICE" in t for t in _pdf_texts(db, saved["id"], monkeypatch))


def test_no_gstin_standalone_credit_note_has_no_gst(client, tenant, auth_headers, db):
    from backend.app.services import credit_service

    _unregistered(tenant, db)
    customer = tenant.customer(billing_state="Karnataka", billing_country="IN")
    cn = credit_service.create_credit_note(
        db,
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        lines=[{"description": "Goodwill", "quantity": 1, "unit_price": "100", "tax_rate_pct": 18}],
    )
    assert cn.tax_amount == 0
    assert cn.cgst_amount == cn.sgst_amount == cn.igst_amount == 0
    assert cn.total == Decimal("100")


def test_preview_rejects_unknown_customer(client, tenant, auth_headers):
    res = client.get("/api/v1/quotes/supply-preview", headers=auth_headers, params={"customer_id": "nope"})
    assert res.status_code == 404

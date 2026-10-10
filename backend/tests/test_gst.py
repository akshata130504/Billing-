"""GST correctness: place of supply, CGST/SGST/IGST split, and reconciliation.

These are the tests that make the tax numbers on an issued invoice trustworthy.
A GST invoice that shows one combined tax figure, or whose heads do not add back
to the tax charged, is not a valid tax invoice.
"""
from decimal import Decimal

import pytest

from backend.app.services import gst
from backend.app.services.money import LineInput, compute_totals

KA_ORG_GSTIN = "29AAFCB9900V1Z8"   # Karnataka
KA_CUST_GSTIN = "29AAACN5678K1Z2"  # Karnataka
MH_CUST_GSTIN = "27AABCB1234F1Z5"  # Maharashtra


class _Org:
    def __init__(self, gstin=KA_ORG_GSTIN, state="Karnataka", country="IN"):
        self.gstin, self.state, self.country = gstin, state, country


class _Cust:
    def __init__(self, gstin=None, billing_state=None, billing_country="IN"):
        self.gstin, self.billing_state, self.billing_country = gstin, billing_state, billing_country


# --- place of supply ----------------------------------------------------------------------


def test_gstin_state_code_drives_place_of_supply():
    supply = gst.resolve_supply(_Org(), _Cust(gstin=MH_CUST_GSTIN, billing_state="Karnataka"))
    # The GSTIN wins over a contradictory typed address.
    assert supply.place_of_supply_code == "27"
    assert supply.place_of_supply_name == "Maharashtra"
    assert supply.supply_type == gst.SUPPLY_INTER


def test_same_state_is_intra_state():
    supply = gst.resolve_supply(_Org(), _Cust(gstin=KA_CUST_GSTIN))
    assert supply.supply_type == gst.SUPPLY_INTRA
    assert supply.is_gst_registered is True


def test_unregistered_customer_falls_back_to_billing_state():
    supply = gst.resolve_supply(_Org(), _Cust(billing_state="Tamil Nadu"))
    assert supply.place_of_supply_code == "33"
    assert supply.supply_type == gst.SUPPLY_INTER
    assert supply.is_gst_registered is False


def test_unknown_customer_state_defaults_to_suppliers_own_state():
    """Unknown recipient state must charge CGST+SGST, never silently drop tax."""
    supply = gst.resolve_supply(_Org(), _Cust())
    assert supply.supply_type == gst.SUPPLY_INTRA
    assert supply.place_of_supply_code == "29"


def test_overseas_customer_is_an_export():
    supply = gst.resolve_supply(_Org(), _Cust(billing_country="US"))
    assert supply.is_export is True
    assert gst.split_tax("100.00", supply) == gst.ZERO_SPLIT


def test_state_name_aliases_are_recognised():
    assert gst.state_code_from_name("Pondicherry") == "34"
    assert gst.state_code_from_name("tamilnadu") == "33"
    assert gst.state_code_from_name("Nowhere") is None


@pytest.mark.parametrize(
    "gstin,valid",
    [
        (KA_ORG_GSTIN, True),
        ("29AAFCB9900V1Z", False),   # too short
        ("99AAFCB9900V1Z8", True),   # 99 is a real (Centre) code
        ("00AAFCB9900V1Z8", False),  # unknown state code
        (None, False),
    ],
)
def test_gstin_structural_validation(gstin, valid):
    assert gst.is_valid_gstin(gstin) is valid


# --- the split ----------------------------------------------------------------------------


def test_intra_state_split_is_half_and_half():
    supply = gst.resolve_supply(_Org(), _Cust(gstin=KA_CUST_GSTIN))
    split = gst.split_tax("180.00", supply)
    assert (split.cgst, split.sgst, split.igst) == (Decimal("90.00"), Decimal("90.00"), Decimal("0.00"))


def test_inter_state_split_is_all_igst():
    supply = gst.resolve_supply(_Org(), _Cust(gstin=MH_CUST_GSTIN))
    split = gst.split_tax("180.00", supply)
    assert (split.cgst, split.sgst, split.igst) == (Decimal("0.00"), Decimal("0.00"), Decimal("180.00"))


def test_odd_paisa_split_still_reconciles():
    """Halving 4.05 independently would lose a paisa; the split must not."""
    supply = gst.resolve_supply(_Org(), _Cust(gstin=KA_CUST_GSTIN))
    split = gst.split_tax("4.05", supply)
    assert split.cgst + split.sgst == Decimal("4.05")
    assert split.total == Decimal("4.05")


def test_rate_split_for_display():
    intra = gst.resolve_supply(_Org(), _Cust(gstin=KA_CUST_GSTIN))
    inter = gst.resolve_supply(_Org(), _Cust(gstin=MH_CUST_GSTIN))
    assert gst.split_rate(18, intra).cgst == Decimal("9.00")
    assert gst.split_rate(18, intra).sgst == Decimal("9.00")
    assert gst.split_rate(18, inter).igst == Decimal("18.00")


# --- totals engine ------------------------------------------------------------------------

LINES = [
    LineInput("Consulting", Decimal("3"), Decimal("1500"), Decimal("18")),
    LineInput("Hosting", Decimal("1"), Decimal("4999"), Decimal("18")),
]


def test_document_heads_are_the_exact_sum_of_line_heads():
    supply = gst.resolve_supply(_Org(), _Cust(gstin=KA_CUST_GSTIN))
    totals = compute_totals(LINES, 0, supply=supply)
    assert totals.cgst_amount == sum(l.cgst_amount for l in totals.lines)
    assert totals.sgst_amount == sum(l.sgst_amount for l in totals.lines)
    assert totals.igst_amount == sum(l.igst_amount for l in totals.lines)


@pytest.mark.parametrize("discount", [0, 10, 33.33])
def test_heads_reconcile_to_tax_amount_at_any_discount(discount):
    for cust in (_Cust(gstin=KA_CUST_GSTIN), _Cust(gstin=MH_CUST_GSTIN)):
        supply = gst.resolve_supply(_Org(), cust)
        totals = compute_totals(LINES, discount, supply=supply)
        assert totals.cgst_amount + totals.sgst_amount + totals.igst_amount == totals.tax_amount


def test_total_is_unaffected_by_which_heads_are_used():
    """Intra vs inter changes the heads, never the amount the customer pays."""
    intra = compute_totals(LINES, 0, supply=gst.resolve_supply(_Org(), _Cust(gstin=KA_CUST_GSTIN)))
    inter = compute_totals(LINES, 0, supply=gst.resolve_supply(_Org(), _Cust(gstin=MH_CUST_GSTIN)))
    assert intra.total == inter.total
    assert intra.tax_amount == inter.tax_amount


def test_compute_totals_without_supply_stays_backward_compatible():
    totals = compute_totals(LINES, 0)
    assert totals.tax_amount > 0
    assert totals.cgst_amount == totals.sgst_amount == totals.igst_amount == Decimal("0.00")


# --- end to end through the API -----------------------------------------------------------


def _catalog(client, headers):
    product = client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "Consulting", "type": "service", "hsn_sac_code": "998314", "tax_rate_pct": 18},
    ).json()
    return product


def test_issued_invoice_carries_the_gst_split_and_hsn(client, tenant, auth_headers, db):
    """The API must persist and return the heads, place of supply and HSN."""
    tenant.organization.gstin = KA_ORG_GSTIN
    tenant.organization.state = "Karnataka"
    tenant.organization.country = "IN"
    db.commit()

    product = _catalog(client, auth_headers)
    customer = tenant.customer(gstin=MH_CUST_GSTIN, billing_state="Maharashtra", billing_country="IN")

    res = client.post(
        "/api/v1/invoices",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "items": [
                {"product_id": product["id"], "description": "Consulting", "quantity": 2,
                 "unit_price": "1000", "tax_rate_pct": 18}
            ],
        },
    )
    assert res.status_code == 201, res.text
    inv = res.json()

    # Inter-state: everything in IGST, nothing in CGST/SGST.
    assert inv["supply_type"] == "inter_state"
    assert inv["place_of_supply_name"] == "Maharashtra"
    assert inv["place_of_supply_code"] == "27"
    assert inv["customer_gstin"] == MH_CUST_GSTIN
    assert inv["supplier_gstin"] == KA_ORG_GSTIN
    assert Decimal(inv["igst_amount"]) == Decimal("360.00")
    assert Decimal(inv["cgst_amount"]) == Decimal("0.00")
    assert Decimal(inv["sgst_amount"]) == Decimal("0.00")
    assert Decimal(inv["tax_amount"]) == Decimal("360.00")
    assert Decimal(inv["total"]) == Decimal("2360.00")

    line = inv["items"][0]
    assert Decimal(line["igst_amount"]) == Decimal("360.00")
    assert Decimal(line["igst_rate_pct"]) == Decimal("18.00")
    assert line["hsn_sac_code"] == "998314"


def test_intra_state_invoice_splits_into_cgst_and_sgst(client, tenant, auth_headers, db):
    tenant.organization.gstin = KA_ORG_GSTIN
    tenant.organization.state = "Karnataka"
    db.commit()
    product = _catalog(client, auth_headers)
    customer = tenant.customer(gstin=KA_CUST_GSTIN, billing_state="Karnataka")

    inv = client.post(
        "/api/v1/invoices",
        headers=auth_headers,
        json={"customer_id": customer.id, "items": [
            {"product_id": product["id"], "description": "Consulting", "quantity": 1,
             "unit_price": "1000", "tax_rate_pct": 18}]},
    ).json()

    assert inv["supply_type"] == "intra_state"
    assert Decimal(inv["cgst_amount"]) == Decimal("90.00")
    assert Decimal(inv["sgst_amount"]) == Decimal("90.00")
    assert Decimal(inv["igst_amount"]) == Decimal("0.00")
    assert Decimal(inv["cgst_amount"]) + Decimal(inv["sgst_amount"]) == Decimal(inv["tax_amount"])


def test_invoice_pdf_renders_with_gst_heads(client, tenant, auth_headers, db):
    """The PDF is the document the customer files; it must render with the split."""
    from backend.app.models import Invoice, Organization
    from backend.app.services.invoice_pdf import render_invoice_pdf

    tenant.organization.gstin = KA_ORG_GSTIN
    tenant.organization.state = "Karnataka"
    db.commit()
    product = _catalog(client, auth_headers)
    customer = tenant.customer(gstin=KA_CUST_GSTIN, billing_state="Karnataka")
    created = client.post(
        "/api/v1/invoices",
        headers=auth_headers,
        json={"customer_id": customer.id, "items": [
            {"product_id": product["id"], "description": "Consulting", "quantity": 1,
             "unit_price": "1000", "tax_rate_pct": 18}]},
    ).json()

    invoice = db.get(Invoice, created["id"])
    org = db.get(Organization, invoice.organization_id)
    pdf = render_invoice_pdf(invoice, org)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000

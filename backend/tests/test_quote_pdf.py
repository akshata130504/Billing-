"""Tests for Quote PDF generation and GET /api/v1/quotes/{quote_id}/pdf."""
import os
import re
import uuid
import zlib
from datetime import date, timedelta
from decimal import Decimal
import pytest

from backend.app.core.config import settings
from backend.app.models.customization import DocumentTemplate, DocumentType, TemplateLayoutType
from backend.app.models.quotes import Quote, QuoteItem, QuoteStatus
from backend.app.services.quote_pdf import render_quote_pdf
from backend.tests.conftest import Tenant


import base64


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    idx = 0
    decompressed_chunks = []
    while True:
        s_idx = pdf_bytes.find(b"stream", idx)
        if s_idx == -1:
            break
        p = s_idx + 6
        while p < len(pdf_bytes) and pdf_bytes[p : p + 1] in (b"\r", b"\n"):
            p += 1
        e_idx = pdf_bytes.find(b"endstream", p)
        if e_idx == -1:
            break
        chunk = pdf_bytes[p:e_idx].strip()
        idx = e_idx + 9

        if not chunk.startswith(b"<~"):
            chunk = b"<~" + chunk
        if not chunk.endswith(b"~>"):
            chunk = chunk + b"~>"
        try:
            a85 = base64.a85decode(chunk, adobe=True)
            txt = zlib.decompress(a85).decode("latin1", errors="ignore")
            decompressed_chunks.append(txt)
        except Exception:
            # Maybe the chunk didn't have adobe markers or had extra padding
            try:
                # try stripping <~ and ~>
                c2 = chunk
                if c2.startswith(b"<~"):
                    c2 = c2[2:]
                if c2.endswith(b"~>"):
                    c2 = c2[:-2]
                a85 = base64.a85decode(b"<~" + c2.strip() + b"~>", adobe=True)
                txt = zlib.decompress(a85).decode("latin1", errors="ignore")
                decompressed_chunks.append(txt)
            except Exception as e2:
                decompressed_chunks.append(f"ERROR: {e2}")

    return "\n".join(decompressed_chunks) + "\n" + pdf_bytes.decode("latin1", errors="ignore")


def _get_page_count(pdf_bytes: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))


def _create_sample_quote(tenant, db, items_count=2, discount_pct=Decimal("10.00")):
    cust = tenant.customer()
    quote = Quote(
        organization_id=tenant.organization.id,
        quote_number=f"QT-{uuid.uuid4().hex[:8].upper()}",
        customer_id=cust.id,
        status=QuoteStatus.APPROVED,
        issue_date=date.today(),
        expiry_date=date.today() + timedelta(days=30),
        currency="INR",
        subtotal=Decimal("0.00"),
        discount_pct=discount_pct,
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("0.00"),
        total=Decimal("0.00"),
        title="Comprehensive Enterprise Quotation",
        notes="Thank you for considering our proposal.",
        terms="Valid for 30 days from issue date.",
    )
    db.add(quote)
    db.flush()

    subtotal = Decimal("0.00")
    for i in range(1, items_count + 1):
        rate = Decimal("1000.00") * i
        qty = Decimal("1")
        line_amt = rate * qty
        subtotal += line_amt
        item = QuoteItem(
            organization_id=tenant.organization.id,
            quote_id=quote.id,
            description=f"Professional Service Item {i}",
            quantity=qty,
            unit_price=rate,
            tax_rate_pct=Decimal("18.00"),
            amount=line_amt,
            cgst_amount=line_amt * Decimal("0.09"),
            sgst_amount=line_amt * Decimal("0.09"),
            cgst_rate_pct=Decimal("9.00"),
            sgst_rate_pct=Decimal("9.00"),
            hsn_sac_code=f"99831{i}",
            position=i,
            pricing_explanation=f"Tier {i} fixed pricing",
        )
        quote.items.append(item)

    discount_amt = (subtotal * discount_pct / Decimal("100.00")).quantize(Decimal("0.01"))
    taxable = subtotal - discount_amt
    cgst = (taxable * Decimal("0.09")).quantize(Decimal("0.01"))
    sgst = (taxable * Decimal("0.09")).quantize(Decimal("0.01"))
    tax_amt = cgst + sgst
    total = taxable + tax_amt

    quote.subtotal = subtotal
    quote.discount_amount = discount_amt
    quote.tax_amount = tax_amt
    quote.cgst_amount = cgst
    quote.sgst_amount = sgst
    quote.total = total

    db.commit()
    db.refresh(quote)
    return quote


def test_quote_pdf_endpoint_success_and_headers(client, tenant, auth_headers, db):
    quote = _create_sample_quote(tenant, db)
    resp = client.get(f"/api/v1/quotes/{quote.id}/pdf", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"].startswith(f'inline; filename="Quote-{quote.quote_number}.pdf"')
    assert resp.content.startswith(b"%PDF")


def test_quote_pdf_content_and_financial_integrity(client, tenant, auth_headers, db):
    quote = _create_sample_quote(tenant, db, items_count=2, discount_pct=Decimal("15.00"))
    resp = client.get(f"/api/v1/quotes/{quote.id}/pdf", headers=auth_headers)
    assert resp.status_code == 200

    pdf_text = _extract_pdf_text(resp.content)

    # 1. Quote metadata
    assert quote.quote_number in pdf_text
    assert "QUOTATION" in pdf_text or "QUOTE" in pdf_text
    assert "Enterprise" in pdf_text

    # 2. Customer data
    cust = quote.customer
    assert cust.display_name in pdf_text

    # 3. Line items
    assert "Professional" in pdf_text
    assert "Item" in pdf_text
    assert "998311" in pdf_text

    # 4. Totals and GST
    assert "Subtotal" in pdf_text
    assert "Discount" in pdf_text
    assert "15.00%" in pdf_text
    assert "CGST" in pdf_text
    assert "SGST/UTGST" in pdf_text
    assert "Total" in pdf_text

    # 5. Notes and terms
    assert "Thank you for considering our proposal." in pdf_text
    assert "Valid for 30 days from issue date." in pdf_text


def test_quote_pdf_document_template_customization(client, tenant, auth_headers, db):
    quote = _create_sample_quote(tenant, db)

    # Create a custom quote document template
    template = DocumentTemplate(
        organization_id=tenant.organization.id,
        document_type=DocumentType.QUOTE,
        name="Modern Blue Quote",
        layout_type=TemplateLayoutType.MODERN,
        is_default=True,
        primary_color="#0F172A",
        accent_color="#2563EB",
        font_family="Helvetica",
        header_text="CONFIDENTIAL ENTERPRISE QUOTATION",
        footer_text="Authorized Rooman Billing Quotation - Page 1 of 1",
        terms_and_conditions="Custom template terms and conditions apply.",
    )
    db.add(template)
    db.commit()

    resp = client.get(f"/api/v1/quotes/{quote.id}/pdf", headers=auth_headers)
    assert resp.status_code == 200

    pdf_text = _extract_pdf_text(resp.content)
    assert "CONFIDENTIAL ENTERPRISE QUOTATION" in pdf_text
    assert "Authorized Rooman Billing Quotation" in pdf_text


def test_quote_pdf_different_templates_produce_different_output(client, tenant, auth_headers, db):
    quote = _create_sample_quote(tenant, db)

    # Template A
    tmpl_a = DocumentTemplate(
        organization_id=tenant.organization.id,
        document_type=DocumentType.QUOTE,
        name="Template A",
        layout_type=TemplateLayoutType.STANDARD,
        is_default=False,
        header_text="BRANDING_VARIATION_ALPHA",
    )
    # Template B
    tmpl_b = DocumentTemplate(
        organization_id=tenant.organization.id,
        document_type=DocumentType.QUOTE,
        name="Template B",
        layout_type=TemplateLayoutType.MODERN,
        is_default=False,
        header_text="BRANDING_VARIATION_BETA",
    )
    db.add_all([tmpl_a, tmpl_b])
    db.commit()

    resp_a = client.get(f"/api/v1/quotes/{quote.id}/pdf?template_id={tmpl_a.id}", headers=auth_headers)
    resp_b = client.get(f"/api/v1/quotes/{quote.id}/pdf?template_id={tmpl_b.id}", headers=auth_headers)

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    text_a = _extract_pdf_text(resp_a.content)
    text_b = _extract_pdf_text(resp_b.content)

    assert "BRANDING_VARIATION_ALPHA" in text_a
    assert "BRANDING_VARIATION_BETA" not in text_a
    assert "BRANDING_VARIATION_BETA" in text_b
    assert "BRANDING_VARIATION_ALPHA" not in text_b
    assert resp_a.content != resp_b.content


def test_quote_pdf_logo_support(client, tenant, auth_headers, db):
    quote = _create_sample_quote(tenant, db)

    # 1x1 valid PNG bytes
    valid_png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\r\xef5\xcb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    logo_dir = os.path.join(settings.UPLOAD_DIR, "logos")
    os.makedirs(logo_dir, exist_ok=True)
    logo_filename = f"test_quote_logo_{uuid.uuid4().hex[:8]}.png"
    logo_path = os.path.join(logo_dir, logo_filename)
    with open(logo_path, "wb") as f:
        f.write(valid_png_bytes)

    tenant.organization.logo_url = f"/uploads/logos/{logo_filename}"
    db.commit()

    resp = client.get(f"/api/v1/quotes/{quote.id}/pdf", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")

    # Cleanup test logo
    if os.path.exists(logo_path):
        os.remove(logo_path)


def test_quote_pdf_missing_logo_and_template_graceful(client, tenant, auth_headers, db):
    quote = _create_sample_quote(tenant, db)
    tenant.organization.logo_url = None
    db.commit()

    # Direct service call without template
    pdf_bytes = render_quote_pdf(quote, tenant.organization, template=None)
    assert pdf_bytes.startswith(b"%PDF")


def test_quote_pdf_long_multipage_quote(client, tenant, auth_headers, db):
    # Quote with 30 items spanning multiple pages
    long_quote = _create_sample_quote(tenant, db, items_count=30)
    resp = client.get(f"/api/v1/quotes/{long_quote.id}/pdf", headers=auth_headers)

    assert resp.status_code == 200
    assert _get_page_count(resp.content) > 1, "Expected multi-page PDF for 30 line items"

    pdf_text = _extract_pdf_text(resp.content)
    assert "Professional" in pdf_text
    assert "Item" in pdf_text
    assert "30" in pdf_text


def test_quote_pdf_tenant_isolation(client, tenant, auth_headers, db):
    quote_a = _create_sample_quote(tenant, db)
    other_tenant = Tenant(db, uuid.uuid4().hex[:8])
    other_auth_headers = other_tenant.headers()

    # Tenant B tries to access Tenant A's quote PDF
    resp = client.get(f"/api/v1/quotes/{quote_a.id}/pdf", headers=other_auth_headers)
    assert resp.status_code == 404


def test_quote_pdf_not_found(client, tenant, auth_headers):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/api/v1/quotes/{fake_id}/pdf", headers=auth_headers)
    assert resp.status_code == 404


def test_quote_pdf_unauthorized(client, tenant, db):
    quote = _create_sample_quote(tenant, db)
    resp = client.get(f"/api/v1/quotes/{quote.id}/pdf")
    assert resp.status_code == 401


@pytest.mark.parametrize("validity_days", [7, 15, 30, 60, 90])
def test_quote_pdf_dynamic_terms_validity(client, tenant, auth_headers, db, validity_days):
    quote = _create_sample_quote(tenant, db)
    quote.issue_date = date.today()
    quote.expiry_date = date.today() + timedelta(days=validity_days)
    # Stored terms might have the old default 30 days or dynamic
    quote.terms = (
        "1. Quote valid for 30 days.\n"
        "2. Payment terms: 30 days from invoice date.\n"
        "3. Taxes as applicable per Indian GST."
    )
    db.commit()

    resp = client.get(f"/api/v1/quotes/{quote.id}/pdf", headers=auth_headers)
    assert resp.status_code == 200

    pdf_text = _extract_pdf_text(resp.content)

    # 1. Terms must dynamically say "Quote valid for {validity_days} days"
    assert f"Quote valid for {validity_days} days" in pdf_text

    # 2. For non-30-day quotes, the validity line must NOT say "Quote valid for 30 days"
    if validity_days != 30:
        assert "Quote valid for 30 days" not in pdf_text

    # 3. Payment terms must be preserved untouched
    assert "Payment terms: 30 days from invoice date." in pdf_text

    # 4. GST terms must be preserved untouched
    assert "Taxes as applicable per Indian GST." in pdf_text


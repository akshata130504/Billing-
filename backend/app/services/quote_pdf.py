"""Quote PDF rendering with ReportLab.

`render_quote_pdf(quote, organization, template=None)` returns the PDF bytes of a clean A4
document. Amounts are written with the ISO currency code ("INR 1,250.00") instead of the
rupee glyph because built-in Helvetica has no ₹ and a missing glyph renders as a black box.

Reuses the same DocumentTemplate branding (colors, typography, layout, header/footer, logo)
as the invoice PDF engine.
"""
import re
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any, List, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.app.core.logging import logger
from backend.app.services.invoice_pdf import (
    ACCENT,
    LIGHT,
    MUTED,
    _address_lines,
    _load_logo_image,
    _p,
    _parse_color,
    fmt_date,
    fmt_money,
    fmt_qty,
)
from backend.app.services.money import D, q2


def render_quote_pdf(quote, organization, template=None) -> bytes:
    """Render `quote` (with .items and .customer loaded) for `organization` and return PDF bytes.
    Consumes configured `template` (colors, fonts, header/footer, terms, layout) if provided or
    resolves the organization's default template.
    """
    if template is None:
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import object_session
            from backend.app.models.customization import DocumentTemplate, DocumentType

            sess = object_session(quote)
            if sess is not None:
                # 1. Preferred: Default template for Quotes
                template = sess.scalar(
                    select(DocumentTemplate).where(
                        DocumentTemplate.organization_id == organization.id,
                        DocumentTemplate.document_type == DocumentType.QUOTE,
                        DocumentTemplate.is_default.is_(True),
                    )
                )
                # 2. Fallback: Any active template for Quotes
                if template is None:
                    template = sess.scalar(
                        select(DocumentTemplate).where(
                            DocumentTemplate.organization_id == organization.id,
                            DocumentTemplate.document_type == DocumentType.QUOTE,
                            DocumentTemplate.is_active.is_(True),
                        )
                    )
                # Never an invoice template: a template applies only to its own
                # document type (BUG-49). No quote template -> built-in styling.
        except Exception as exc:
            logger.warning("Could not resolve document template for quote %s: %s", getattr(quote, "id", None), exc)
            template = None

    accent_color = _parse_color(getattr(template, "accent_color", None), ACCENT)
    primary_color = _parse_color(getattr(template, "primary_color", None), colors.HexColor("#111827"))

    base_font = "Helvetica"
    bold_font = "Helvetica-Bold"
    if template and getattr(template, "font_family", None):
        ff = template.font_family.lower()
        if "times" in ff or "serif" in ff:
            base_font = "Times-Roman"
            bold_font = "Times-Bold"
        elif "courier" in ff or "mono" in ff:
            base_font = "Courier"
            bold_font = "Courier-Bold"

    layout_val = "standard"
    if template and getattr(template, "layout_type", None):
        layout_val = getattr(template.layout_type, "value", str(template.layout_type)).lower()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Quote {quote.quote_number}",
        author=organization.legal_name or organization.name,
    )
    styles = getSampleStyleSheet()
    base = styles["Normal"]
    base.fontName = base_font
    base.fontSize = 9
    base.leading = 12
    small = ParagraphStyle("small", parent=base, fontName=base_font, fontSize=8, leading=10, textColor=MUTED)
    bold = ParagraphStyle("bold", parent=base, fontName=bold_font)
    heading = ParagraphStyle("heading", parent=base, fontName=bold_font, fontSize=18, leading=22, textColor=accent_color)
    right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("right_bold", parent=bold, alignment=TA_RIGHT)
    section = ParagraphStyle("section", parent=small, fontName=bold_font, textColor=accent_color, spaceAfter=2)

    currency = quote.currency or organization.default_currency or "INR"
    customer = quote.customer

    story = []

    # --- Optional Header banner text ---
    if template and getattr(template, "header_text", None):
        hdr_style = ParagraphStyle("hdr_banner", parent=small, fontName=bold_font, textColor=accent_color, alignment=TA_CENTER)
        story.append(_p(template.header_text, hdr_style))
        story.append(Spacer(1, 3 * mm))

    # --- Header: logo + organization block + quote metadata ---
    logo_target = (getattr(template, "logo_url", None) if template else None) or organization.logo_url
    logo_flowable = _load_logo_image(logo_target)

    org_lines = []
    if logo_flowable:
        org_lines.append(logo_flowable)
        org_lines.append(Spacer(1, 2 * mm))
    org_lines.append(_p(organization.legal_name or organization.name, heading))

    if organization.legal_name and organization.legal_name != organization.name:
        org_lines.append(_p(organization.name, small))
    if not template or getattr(template, "show_company_address", True):
        for line in _address_lines(
            organization.address_line1,
            organization.address_line2,
            " ".join(_address_lines(organization.city, organization.state, organization.postal_code)),
            organization.country,
        ):
            org_lines.append(_p(line, base))
    if organization.gstin:
        org_lines.append(_p(f"GSTIN: {organization.gstin}", base))
    if organization.pan:
        org_lines.append(_p(f"PAN: {organization.pan}", base))
    for line in _address_lines(organization.email, organization.phone, organization.website):
        org_lines.append(_p(line, small))

    status_label = (
        quote.status.value if hasattr(quote.status, "value") else str(quote.status)
    ).replace("_", " ").upper()

    doc_title = "QUOTATION" if layout_val != "minimal" else "QUOTE"
    meta_rows = [
        [_p(doc_title, ParagraphStyle("quo_title", parent=heading, alignment=TA_RIGHT, textColor=accent_color)), ""],
        [_p("Quote number", small), _p(quote.quote_number, right_bold)],
        [_p("Quote date", small), _p(fmt_date(quote.issue_date), right)],
        [_p("Valid until", small), _p(fmt_date(quote.expiry_date) if quote.expiry_date else "N/A", right)],
        [_p("Status", small), _p(status_label, right_bold)],
    ]
    if getattr(quote, "title", None):
        meta_rows.append([_p("Reference", small), _p(quote.title, right)])

    meta = Table(meta_rows, colWidths=[32 * mm, 48 * mm])
    meta.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )

    header = Table([[org_lines, meta]], colWidths=[94 * mm, 80 * mm])
    header_style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]
    if layout_val == "modern":
        header_style.append(("LINEBELOW", (0, 0), (-1, -1), 1.5, accent_color))
        header_style.append(("BOTTOMPADDING", (0, 0), (-1, -1), 6))
    header.setStyle(TableStyle(header_style))
    story.append(header)
    story.append(Spacer(1, 8 * mm if layout_val != "minimal" else 5 * mm))

    # --- Customer section (Quote For) ---
    cust_lines = [_p("QUOTE FOR", section)]
    if customer:
        cust_lines.append(_p(customer.display_name, bold))
        if customer.company_name and customer.company_name != customer.display_name:
            cust_lines.append(_p(customer.company_name, base))
        for line in _address_lines(
            customer.billing_address_line1,
            customer.billing_address_line2,
            " ".join(_address_lines(customer.billing_city, customer.billing_state, customer.billing_postal_code)),
            customer.billing_country,
        ):
            cust_lines.append(_p(line, base))
        if customer.gstin:
            cust_lines.append(_p(f"GSTIN: {customer.gstin}", base))
        for line in _address_lines(customer.email, customer.phone):
            cust_lines.append(_p(line, small))
    else:
        cust_lines.append(_p("Valued Customer", bold))

    pos_name = getattr(quote, "place_of_supply_name", None)
    pos_code = getattr(quote, "place_of_supply_code", None)
    if pos_name:
        cust_lines.append(_p(f"Place of supply: {pos_name}{f' ({pos_code})' if pos_code else ''}", base))

    story.extend(cust_lines)
    story.append(Spacer(1, 6 * mm if layout_val != "minimal" else 4 * mm))

    # --- Line items table ---
    rows = [[
        _p("#", bold),
        _p("Description", bold),
        _p("HSN/SAC", bold),
        _p("Qty", right_bold),
        _p("Unit price", right_bold),
        _p("Tax %", right_bold),
        _p("Amount", right_bold),
    ]]
    for idx, item in enumerate(sorted(quote.items, key=lambda i: getattr(i, "position", 0) or 0), start=1):
        # Customer document: the description only. pricing_explanation is internal (catalog base
        # price, price-book adjustment) and _p escapes markup, so it must never be appended here.
        desc_para = _p(item.description, base)

        rows.append(
            [
                _p(str(idx), base),
                desc_para,
                _p(getattr(item, "hsn_sac_code", None) or "-", small),
                _p(fmt_qty(item.quantity), right),
                _p(fmt_money(item.unit_price, currency), right),
                _p(f"{q2(item.tax_rate_pct):.2f}", right),
                _p(fmt_money(item.amount, currency), right),
            ]
        )

    items_table = Table(
        rows,
        colWidths=[7 * mm, 54 * mm, 21 * mm, 14 * mm, 28 * mm, 18 * mm, 32 * mm],
        repeatRows=1,
    )
    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT if layout_val != "minimal" else colors.HexColor("#ffffff")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0 if layout_val == "modern" else 0.6, accent_color),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    items_table.setStyle(TableStyle(table_styles))
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))

    # --- Totals ---
    totals_rows = [[_p("Subtotal", base), _p(fmt_money(quote.subtotal, currency), right)]]
    if D(quote.discount_amount) > 0:
        pct_text = f" ({q2(quote.discount_pct):.2f}%)" if D(quote.discount_pct) > 0 else ""
        totals_rows.append(
            [_p(f"Discount{pct_text}", base), _p("- " + fmt_money(quote.discount_amount, currency), right)]
        )

    cgst = D(getattr(quote, "cgst_amount", 0))
    sgst = D(getattr(quote, "sgst_amount", 0))
    igst = D(getattr(quote, "igst_amount", 0))
    if cgst > 0 or sgst > 0:
        totals_rows.append([_p("CGST", base), _p(fmt_money(cgst, currency), right)])
        totals_rows.append([_p("SGST/UTGST", base), _p(fmt_money(sgst, currency), right)])
    elif igst > 0:
        totals_rows.append([_p("IGST", base), _p(fmt_money(igst, currency), right)])
    elif D(getattr(quote, "tax_amount", 0)) > 0:
        totals_rows.append([_p("Tax", base), _p(fmt_money(quote.tax_amount, currency), right)])

    totals_rows.append([_p("Total", bold), _p(fmt_money(quote.total, currency), right_bold)])

    totals = Table(totals_rows, colWidths=[44 * mm, 44 * mm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, accent_color),
                ("BACKGROUND", (0, -1), (-1, -1), LIGHT if layout_val != "minimal" else colors.HexColor("#fafafa")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(totals)
    story.append(Spacer(1, 8 * mm if layout_val != "minimal" else 5 * mm))

    # --- Notes & Terms ---
    if quote.notes:
        story.append(_p("NOTES", section))
        story.append(_p(quote.notes, base))
        story.append(Spacer(1, 4 * mm))

    validity_days = None
    if getattr(quote, "issue_date", None) and getattr(quote, "expiry_date", None):
        try:
            diff = (quote.expiry_date - quote.issue_date).days
            if diff > 0:
                validity_days = diff
        except Exception:
            validity_days = None

    raw_terms = quote.terms or (getattr(template, "terms_and_conditions", None) if template else None)
    if raw_terms:
        if validity_days:
            terms_text = re.sub(r'(?i)Quote valid for \d+ days?', f'Quote valid for {validity_days} days', raw_terms)
        else:
            terms_text = raw_terms
    elif validity_days:
        terms_text = f"1. Quote valid for {validity_days} days.\n2. Payment terms: 30 days from invoice date.\n3. Taxes as applicable per Indian GST."
    else:
        terms_text = None

    if terms_text:
        story.append(_p("TERMS & CONDITIONS", section))
        story.append(_p(terms_text, base))
        story.append(Spacer(1, 4 * mm))

    story.append(Spacer(1, 4 * mm))
    story.append(_p(f"Generated by {organization.name} - amounts in {currency}.", small))

    # --- Optional Footer banner text ---
    if template and getattr(template, "footer_text", None):
        story.append(Spacer(1, 2 * mm))
        ftr_style = ParagraphStyle("ftr_banner", parent=small, fontName=base_font, textColor=MUTED, alignment=TA_CENTER)
        story.append(_p(template.footer_text, ftr_style))

    doc.build(story)
    return buffer.getvalue()


__all__ = ["render_quote_pdf"]

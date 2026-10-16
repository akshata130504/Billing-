"""Invoice PDF rendering with reportlab.

`render_invoice_pdf(invoice, organization, template=None)` returns the PDF bytes of a clean A4
document. Amounts are written with the ISO currency code ("INR 1,250.00")
instead of the rupee glyph because the built-in Helvetica font has no ₹ and a
missing glyph renders as a black box.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
import os
from typing import Any, List, Optional
from urllib.parse import unquote, urlsplit
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.app.services.email import frontend_url
from backend.app.services.money import D, q2
from backend.app.core.logging import logger

ACCENT = colors.HexColor("#1f3a5f")
MUTED = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#f3f4f6")


def fmt_money(value, currency: str = "INR") -> str:
    amount = q2(value)
    return f"{currency} {amount:,.2f}"


def fmt_qty(value) -> str:
    q = D(value).quantize(Decimal("0.001"))
    text = format(q, "f").rstrip("0").rstrip(".")
    return text or "0"


def fmt_date(value: Optional[date]) -> str:
    return value.strftime("%d %b %Y") if value else "-"


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


def _address_lines(*parts: Optional[str]) -> List[str]:
    return [p for p in parts if p]


def _parse_color(color_val: Optional[str], fallback: colors.HexColor) -> colors.HexColor:
    if not color_val:
        return fallback
    try:
        return colors.HexColor(color_val)
    except Exception:
        return fallback


def _load_logo_image(logo_url: Optional[str]) -> Optional[Any]:
    if not logo_url:
        return None
    try:
        from PIL import Image as PILImage
        from reportlab.platypus import Image as RLImage
        from backend.app.core.config import settings

        # Only files inside UPLOAD_DIR are ever read. Remote URLs are never fetched
        # (rendering a PDF must not make the server issue arbitrary HTTP requests);
        # an absolute URL is accepted only as a pointer to one of our own uploads.
        path = logo_url
        if logo_url.startswith(("http://", "https://")):
            path = urlsplit(logo_url).path or ""
        img_bytes = None
        rel = None
        for prefix in ("/api/v1/uploads/", "/uploads/"):
            if path.startswith(prefix):
                rel = unquote(path[len(prefix):])
                break
        if rel:
            uploads_root = os.path.realpath(settings.UPLOAD_DIR)
            file_path = os.path.realpath(os.path.join(uploads_root, rel))
            try:
                contained = os.path.commonpath([file_path, uploads_root]) == uploads_root
            except ValueError:  # different drives on Windows
                contained = False
            if contained and os.path.isfile(file_path):
                with open(file_path, "rb") as f:
                    img_bytes = f.read()

        if not img_bytes:
            return None

        bio = BytesIO(img_bytes)
        pil_img = PILImage.open(bio)
        orig_w, orig_h = pil_img.size
        if orig_w <= 0 or orig_h <= 0:
            return None

        max_w = 48 * mm
        max_h = 22 * mm
        aspect = orig_w / orig_h
        if aspect > (max_w / max_h):
            render_w = max_w
            render_h = max_w / aspect
        else:
            render_h = max_h
            render_w = max_h * aspect

        bio.seek(0)
        return RLImage(bio, width=render_w, height=render_h)
    except Exception as exc:
        logger.warning("Could not load invoice logo '%s': %s", logo_url, exc)
        return None


def render_invoice_pdf(invoice, organization, template=None) -> bytes:
    """Render `invoice` (with .items and .customer loaded) for `organization` and return PDF bytes.
    Consumes configured `template` (colors, fonts, header/footer, terms, layout) if provided or
    loads the organization's default template.
    """
    if template is None:
        try:
            from sqlalchemy.orm import object_session
            from sqlalchemy import select
            from backend.app.models.customization import DocumentTemplate, DocumentType
            sess = object_session(invoice)
            if sess is not None:
                template = sess.scalar(
                    select(DocumentTemplate).where(
                        DocumentTemplate.organization_id == organization.id,
                        DocumentTemplate.document_type == DocumentType.INVOICE,
                        DocumentTemplate.is_default.is_(True),
                    )
                )
        except Exception:
            template = None

    accent_color = _parse_color(getattr(template, "accent_color", None), ACCENT)

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

    # GSTINs as frozen on the invoice at issue (a later edit to the organization or
    # customer must not restate an issued tax invoice); live values only as fallback
    # for invoices created before the snapshot columns existed.
    supplier_gstin = getattr(invoice, "supplier_gstin", None) or organization.gstin
    customer_gstin = getattr(invoice, "customer_gstin", None) or getattr(invoice.customer, "gstin", None)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{'Tax Invoice' if supplier_gstin else 'Invoice'} {invoice.invoice_number}",
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

    currency = invoice.currency or organization.default_currency or "INR"
    customer = invoice.customer

    is_tax_invoice = bool(supplier_gstin) and D(invoice.tax_amount) > 0
    doc_heading = "TAX INVOICE" if is_tax_invoice else "BILL OF SUPPLY" if organization.country == "IN" and not supplier_gstin else "INVOICE"
    story = []

    # --- Optional Header text ---
    if template and getattr(template, "header_text", None):
        hdr_style = ParagraphStyle("hdr_banner", parent=small, fontName=bold_font, textColor=accent_color, alignment=TA_CENTER)
        story.append(_p(template.header_text, hdr_style))
        story.append(Spacer(1, 3 * mm))

    # --- Header: logo + organization block + invoice meta --------------------------------
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
    if supplier_gstin:
        org_lines.append(_p(f"GSTIN: {supplier_gstin}", base))
    if organization.pan:
        org_lines.append(_p(f"PAN: {organization.pan}", base))
    for line in _address_lines(organization.email, organization.phone, organization.website):
        org_lines.append(_p(line, small))

    status_label = (invoice.status.value if hasattr(invoice.status, "value") else str(invoice.status)).replace("_", " ").upper()
    meta_rows = [
        [_p(doc_heading, ParagraphStyle("inv", parent=heading, alignment=TA_RIGHT, textColor=accent_color)), ""],
        [_p("Invoice number", small), _p(invoice.invoice_number, right_bold)],
        [_p("Issue date", small), _p(fmt_date(invoice.issue_date), right)],
        [_p("Due date", small), _p(fmt_date(invoice.due_date), right)],
        [_p("Status", small), _p(status_label, right_bold)],
    ]
    if invoice.period_start and invoice.period_end:
        meta_rows.append([_p("Service period", small), _p(f"{fmt_date(invoice.period_start)} - {fmt_date(invoice.period_end)}", right)])
    meta = Table(meta_rows, colWidths=[32 * mm, 48 * mm])
    meta.setStyle(TableStyle([("SPAN", (0, 0), (1, 0)), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 1)]))

    header = Table([[org_lines, meta]], colWidths=[94 * mm, 80 * mm])
    header_style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]
    if layout_val == "modern":
        header_style.append(("LINEBELOW", (0, 0), (-1, -1), 1.5, accent_color))
        header_style.append(("BOTTOMPADDING", (0, 0), (-1, -1), 6))
    header.setStyle(TableStyle(header_style))
    story.append(header)
    story.append(Spacer(1, 8 * mm if layout_val != "minimal" else 5 * mm))

    # --- Bill to -------------------------------------------------------------------------
    bill_lines = [_p("BILL TO", section), _p(customer.display_name, bold)]
    if customer.company_name and customer.company_name != customer.display_name:
        bill_lines.append(_p(customer.company_name, base))
    for line in _address_lines(
        customer.billing_address_line1,
        customer.billing_address_line2,
        " ".join(_address_lines(customer.billing_city, customer.billing_state, customer.billing_postal_code)),
        customer.billing_country,
    ):
        bill_lines.append(_p(line, base))
    if customer_gstin:
        bill_lines.append(_p(f"GSTIN: {customer_gstin}", base))
    pos_name = getattr(invoice, "place_of_supply_name", None)
    pos_code = getattr(invoice, "place_of_supply_code", None)
    if pos_name:
        bill_lines.append(_p(f"Place of supply: {pos_name}{f' ({pos_code})' if pos_code else ''}", base))
    for line in _address_lines(customer.email, customer.phone):
        bill_lines.append(_p(line, small))
    story.extend(bill_lines)
    story.append(Spacer(1, 6 * mm if layout_val != "minimal" else 4 * mm))

    # --- Line items ---------------------------------------------------------------------------
    rows = [[
        _p("#", bold), _p("Description", bold), _p("HSN/SAC", bold), _p("Qty", right_bold),
        _p("Unit price", right_bold), _p("Tax %", right_bold), _p("Amount", right_bold),
    ]]
    for idx, item in enumerate(sorted(invoice.items, key=lambda i: i.position or 0), start=1):
        rows.append(
            [
                _p(str(idx), base),
                _p(item.description, base),
                _p(getattr(item, "hsn_sac_code", None) or "-", small),
                _p(fmt_qty(item.quantity), right),
                _p(fmt_money(item.unit_price, currency), right),
                _p(f"{q2(item.tax_rate_pct):.2f}", right),
                _p(fmt_money(item.amount, currency), right),
            ]
        )
    items_table = Table(rows, colWidths=[7 * mm, 54 * mm, 21 * mm, 14 * mm, 28 * mm, 13 * mm, 30 * mm], repeatRows=1)
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

    # --- Totals --------------------------------------------------------------------------------------
    totals_rows = [[_p("Subtotal", base), _p(fmt_money(invoice.subtotal, currency), right)]]
    if D(invoice.discount_amount) > 0:
        totals_rows.append([_p(f"Discount ({q2(invoice.discount_pct):.2f}%)", base), _p("- " + fmt_money(invoice.discount_amount, currency), right)])
    cgst = D(getattr(invoice, "cgst_amount", 0))
    sgst = D(getattr(invoice, "sgst_amount", 0))
    igst = D(getattr(invoice, "igst_amount", 0))
    if cgst > 0 or sgst > 0:
        totals_rows.append([_p("CGST", base), _p(fmt_money(cgst, currency), right)])
        totals_rows.append([_p("SGST/UTGST", base), _p(fmt_money(sgst, currency), right)])
    elif igst > 0:
        totals_rows.append([_p("IGST", base), _p(fmt_money(igst, currency), right)])
    else:
        totals_rows.append([_p("Tax", base), _p(fmt_money(invoice.tax_amount, currency), right)])
    totals_rows.append([_p("Total", bold), _p(fmt_money(invoice.total, currency), right_bold)])
    totals_rows.append([_p("Amount paid", base), _p(fmt_money(invoice.amount_paid, currency), right)])
    totals_rows.append([_p("Amount due", bold), _p(fmt_money(invoice.amount_due, currency), right_bold)])
    totals = Table(totals_rows, colWidths=[44 * mm, 44 * mm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, -3), (-1, -3), 0.8, accent_color),
                ("BACKGROUND", (0, -1), (-1, -1), LIGHT if layout_val != "minimal" else colors.HexColor("#fafafa")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(totals)
    story.append(Spacer(1, 8 * mm if layout_val != "minimal" else 5 * mm))

    # --- Pay online / notes / terms -------------------------------------------------------------------------
    if invoice.public_token and str(getattr(invoice.status, "value", invoice.status)) not in {"draft", "void", "paid"}:
        story.append(_p("PAY ONLINE", section))
        story.append(_p(frontend_url(f"pay/{invoice.public_token}"), base))
        story.append(Spacer(1, 4 * mm))
    if invoice.notes:
        story.append(_p("NOTES", section))
        story.append(_p(invoice.notes, base))
        story.append(Spacer(1, 4 * mm))

    terms_text = invoice.terms or (getattr(template, "terms_and_conditions", None) if template else None)
    if terms_text:
        story.append(_p("TERMS", section))
        story.append(_p(terms_text, base))
        story.append(Spacer(1, 4 * mm))

    story.append(Spacer(1, 4 * mm))
    story.append(_p(f"Generated by {organization.name} - amounts in {currency}.", small))

    # --- Optional Footer text ---
    if template and getattr(template, "footer_text", None):
        story.append(Spacer(1, 2 * mm))
        ftr_style = ParagraphStyle("ftr_banner", parent=small, fontName=base_font, textColor=MUTED, alignment=TA_CENTER)
        story.append(_p(template.footer_text, ftr_style))

    doc.build(story)
    return buffer.getvalue()


__all__ = ["render_invoice_pdf", "fmt_money"]

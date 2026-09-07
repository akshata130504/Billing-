"""Invoice PDF rendering with reportlab.

`render_invoice_pdf(invoice, organization)` returns the PDF bytes of a clean A4
document. Amounts are written with the ISO currency code ("INR 1,250.00")
instead of the rupee glyph because the built-in Helvetica font has no ₹ and a
missing glyph renders as a black box.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from backend.app.services.email import frontend_url
from backend.app.services.money import D, q2

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


def render_invoice_pdf(invoice, organization) -> bytes:
    """Render `invoice` (with .items and .customer loaded) for `organization` and return PDF bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Invoice {invoice.invoice_number}",
        author=organization.legal_name or organization.name,
    )
    styles = getSampleStyleSheet()
    base = styles["Normal"]
    base.fontSize = 9
    base.leading = 12
    small = ParagraphStyle("small", parent=base, fontSize=8, leading = 10, textColor=MUTED)
    bold = ParagraphStyle("bold", parent=base, fontName="Helvetica-Bold")
    heading = ParagraphStyle("heading", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=ACCENT)
    right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("right_bold", parent=bold, alignment=TA_RIGHT)
    section = ParagraphStyle("section", parent=small, fontName="Helvetica-Bold", textColor=ACCENT, spaceAfter=2)

    currency = invoice.currency or organization.default_currency or "INR"
    customer = invoice.customer
    story = []

    # --- Header: organization block + invoice meta --------------------------------
    org_lines = [_p(organization.legal_name or organization.name, heading)]
    if organization.legal_name and organization.legal_name != organization.name:
        org_lines.append(_p(organization.name, small))
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

    status_label = (invoice.status.value if hasattr(invoice.status, "value") else str(invoice.status)).replace("_", " ").upper()
    meta_rows = [
        [_p("INVOICE", ParagraphStyle("inv", parent=heading, alignment=TA_RIGHT)), ""],
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
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(header)
    story.append(Spacer(1, 8 * mm))

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
    if customer.gstin:
        bill_lines.append(_p(f"GSTIN: {customer.gstin}", base))
    for line in _address_lines(customer.email, customer.phone):
        bill_lines.append(_p(line, small))
    story.extend(bill_lines)
    story.append(Spacer(1, 6 * mm))

    # --- Line items ---------------------------------------------------------------------------
    rows = [[_p("#", bold), _p("Description", bold), _p("Qty", right_bold), _p("Unit price", right_bold), _p("Tax %", right_bold), _p("Amount", right_bold)]]
    for idx, item in enumerate(sorted(invoice.items, key=lambda i: i.position or 0), start=1):
        rows.append(
            [
                _p(str(idx), base),
                _p(item.description, base),
                _p(fmt_qty(item.quantity), right),
                _p(fmt_money(item.unit_price, currency), right),
                _p(f"{q2(item.tax_rate_pct):.2f}", right),
                _p(fmt_money(item.amount, currency), right),
            ]
        )
    items_table = Table(rows, colWidths=[8 * mm, 76 * mm, 16 * mm, 30 * mm, 14 * mm, 30 * mm], repeatRows=1)
    items_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, ACCENT),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))

    # --- Totals --------------------------------------------------------------------------------------
    totals_rows = [[_p("Subtotal", base), _p(fmt_money(invoice.subtotal, currency), right)]]
    if D(invoice.discount_amount) > 0:
        totals_rows.append([_p(f"Discount ({q2(invoice.discount_pct):.2f}%)", base), _p("- " + fmt_money(invoice.discount_amount, currency), right)])
    totals_rows.append([_p("Tax", base), _p(fmt_money(invoice.tax_amount, currency), right)])
    totals_rows.append([_p("Total", bold), _p(fmt_money(invoice.total, currency), right_bold)])
    totals_rows.append([_p("Amount paid", base), _p(fmt_money(invoice.amount_paid, currency), right)])
    totals_rows.append([_p("Amount due", bold), _p(fmt_money(invoice.amount_due, currency), right_bold)])
    totals = Table(totals_rows, colWidths=[44 * mm, 44 * mm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, -3), (-1, -3), 0.6, ACCENT),
                ("BACKGROUND", (0, -1), (-1, -1), LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(totals)
    story.append(Spacer(1, 8 * mm))

    # --- Pay online / notes / terms -------------------------------------------------------------------------
    if invoice.public_token and str(getattr(invoice.status, "value", invoice.status)) not in {"draft", "void", "paid"}:
        story.append(_p("PAY ONLINE", section))
        story.append(_p(frontend_url(f"pay/{invoice.public_token}"), base))
        story.append(Spacer(1, 4 * mm))
    if invoice.notes:
        story.append(_p("NOTES", section))
        story.append(_p(invoice.notes, base))
        story.append(Spacer(1, 4 * mm))
    if invoice.terms:
        story.append(_p("TERMS", section))
        story.append(_p(invoice.terms, base))
        story.append(Spacer(1, 4 * mm))
    story.append(Spacer(1, 4 * mm))
    story.append(_p(f"Generated by {organization.name} - amounts in {currency}.", small))

    doc.build(story)
    return buffer.getvalue()


__all__ = ["render_invoice_pdf", "fmt_money"]

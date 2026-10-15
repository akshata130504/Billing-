"""PDF of a Rooman plan PAYMENT RECEIPT (reportlab, same conventions as invoice_pdf.py).

States plainly that it is a payment receipt and not a tax invoice: no tax lines, rates or seller tax registration
are printed, because Rooman's tax treatment and legal / tax details are not decided. Everything printed comes from
the stored receipt snapshot (models/platform_billing.PlatformPayment); nothing is looked up live or invented.
"""
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

from backend.app.services.invoice_pdf import ACCENT, LIGHT, MUTED, _p
from backend.app.services.platform_receipt_service import RECEIPT_NOTE

ISSUER = "Rooman Billing"


def _money(amount_minor: int, currency: str) -> str:
    return f"{currency} {(Decimal(amount_minor) / 100):,.2f}"


def _dt(value: Optional[datetime]) -> str:
    if value is None:
        return "-"
    value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def _d(value: Optional[datetime]) -> str:
    return value.strftime("%d %b %Y") if value else "-"


def _billed_lines(row) -> List[str]:
    lines = [row.billed_legal_name or row.billed_name]
    if row.billed_legal_name and row.billed_legal_name != row.billed_name:
        lines.append(row.billed_name)
    for part in (row.billed_address_line1, row.billed_address_line2):
        if part:
            lines.append(part)
    place = ", ".join(p for p in (row.billed_city, row.billed_state, row.billed_postal_code) if p)
    if place:
        lines.append(place)
    if row.billed_country:
        lines.append(row.billed_country)
    if row.billed_gstin:
        lines.append(f"GSTIN (as provided): {row.billed_gstin}")
    if row.billed_email:
        lines.append(row.billed_email)
    return lines


def render_receipt_pdf(row) -> bytes:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=13)
    muted = ParagraphStyle("muted", parent=body, textColor=MUTED, fontSize=8.5)
    title = ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=18, textColor=ACCENT, leading=22)
    bold = ParagraphStyle("bold", parent=body, fontName="Helvetica-Bold")
    warn = ParagraphStyle("warn", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#b45309"))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=f"Payment receipt {row.receipt_number}", author=ISSUER)
    story = [_p("PAYMENT RECEIPT", title), _p(RECEIPT_NOTE, muted), Spacer(1, 4 * mm)]
    if row.sandbox or row.mode == "test":
        story += [_p("TEST MODE - no real money was charged. Not a commercial transaction.", warn), Spacer(1, 3 * mm)]

    facts = [
        [_p("Receipt number", muted), _p(row.receipt_number, bold)],
        [_p("Payment date", muted), _p(_dt(row.paid_at), body)],
        [_p("Status", muted), _p("Paid", body)],
        [_p("Payment reference", muted), _p(row.provider_payment_id, body)],
    ]
    if row.provider_invoice_id:
        facts.append([_p("Razorpay invoice", muted), _p(row.provider_invoice_id, body)])
    if row.method:
        facts.append([_p("Payment method", muted), _p(row.method.upper() if len(row.method) <= 4 else row.method.title(), body)])
    fact_table = Table(facts, colWidths=[40 * mm, 60 * mm])
    fact_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))

    parties = Table([[_p("Received from", muted), _p("Issued by", muted)],
                     [_p("\n".join(_billed_lines(row)), body), _p(ISSUER, body)]],
                    colWidths=[95 * mm, 79 * mm])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    every = "month" if row.billing_interval == "month" else "year"
    interval = f"every {row.billing_interval_count} {every}s" if row.billing_interval_count > 1 else f"per {every}"
    period = f"{_d(row.period_start)} to {_d(row.period_end)}" if row.period_start or row.period_end else "-"
    kind = "Plan purchase" if row.kind == "initial" else f"Plan renewal{f' (cycle {row.cycle_number})' if row.cycle_number else ''}"
    lines = Table([
        [_p("Description", bold), _p("Billing period", bold), _p("Amount", bold)],
        [_p(f"{ISSUER} - {row.plan_name or row.plan_code} plan, {interval}\n{kind}", body), _p(period, body),
         _p(_money(row.amount_minor, row.currency), body)],
        ["", _p("Amount received", bold), _p(_money(row.amount_minor, row.currency), bold)],
    ], colWidths=[90 * mm, 50 * mm, 34 * mm])
    lines.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("LINEBELOW", (0, 1), (-1, 1), 0.5, MUTED),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    story += [fact_table, Spacer(1, 6 * mm), parties, Spacer(1, 6 * mm), lines, Spacer(1, 8 * mm),
              _p(f"{RECEIPT_NOTE} Amount shown as charged; no tax is itemised on this receipt.", muted),
              _p(f"Issued {_dt(row.created_at)}.", muted)]
    doc.build(story)
    return buffer.getvalue()

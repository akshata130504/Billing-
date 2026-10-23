"""/reports — management reporting over real invoice/payment/customer data."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_viewer
from backend.app.core.exceptions import ValidationAppError
from backend.app.schemas.reports import (
    CustomerAnalyticsOut,
    InvoiceAnalyticsOut,
    PaymentAnalyticsOut,
    ProductAnalyticsOut,
    ReceivablesAnalyticsOut,
    ReportKPIs,
    RevenueAnalyticsOut,
)
from backend.app.modules.reports import service as svc
from backend.app.services import timezones

router = APIRouter()

# Reporting currency (ISO-4217). Defaults to the organization's base currency; money in
# other currencies is never converted or summed in (see services/currency_totals.py).
CurrencyParam = Query(None, pattern="^[A-Za-z]{3}$", description="Reporting currency; default: the organization's base currency")


def report_range(
    range: str = Query("this_month", description="One of: " + ", ".join(svc.REPORT_RANGE_KEYS)),
    start: date | None = Query(None, description="Required when range=custom"),
    end: date | None = Query(None, description="Required when range=custom"),
    ctx: CurrentContext = Depends(require_viewer),
) -> svc.ReportRange:
    # Ranges are the organization's local business days ("this month" in Asia/Kolkata
    # starts at 00:00 IST, not 00:00 UTC).
    try:
        return svc.resolve_report_range(
            range, start=start, end=end, today=timezones.org_today(ctx.organization), tz=ctx.organization
        )
    except ValueError as exc:
        raise ValidationAppError(str(exc), {"fields": {"range": str(exc)}})


@router.get("/dashboard", response_model=ReportKPIs, summary="Reports KPI cards")
def get_kpis(
    r: svc.ReportRange = Depends(report_range),
    currency: str | None = CurrencyParam,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.kpis(db, ctx.organization_id, r, currency)


@router.get("/revenue", response_model=RevenueAnalyticsOut, summary="Revenue analytics")
def get_revenue(
    r: svc.ReportRange = Depends(report_range),
    currency: str | None = CurrencyParam,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.revenue_analytics(db, ctx.organization_id, r, currency)


@router.get("/receivables", response_model=ReceivablesAnalyticsOut, summary="Receivables analytics")
def get_receivables(
    r: svc.ReportRange = Depends(report_range),
    currency: str | None = CurrencyParam,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.receivables_analytics(db, ctx.organization_id, r, currency)


@router.get("/invoices", response_model=InvoiceAnalyticsOut, summary="Invoice analytics")
def get_invoice_analytics(
    r: svc.ReportRange = Depends(report_range),
    currency: str | None = CurrencyParam,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.invoice_analytics(db, ctx.organization_id, r, currency)


@router.get("/payments", response_model=PaymentAnalyticsOut, summary="Payment analytics")
def get_payment_analytics(
    r: svc.ReportRange = Depends(report_range),
    currency: str | None = CurrencyParam,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.payment_analytics(db, ctx.organization_id, r, currency)


@router.get("/customers", response_model=CustomerAnalyticsOut, summary="Customer analytics")
def get_customer_analytics(
    r: svc.ReportRange = Depends(report_range),
    currency: str | None = CurrencyParam,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.customer_analytics(db, ctx.organization_id, r, currency)


@router.get("/products", response_model=ProductAnalyticsOut, summary="Product/plan analytics")
def get_product_analytics(
    r: svc.ReportRange = Depends(report_range),
    currency: str | None = CurrencyParam,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.product_analytics(db, ctx.organization_id, r, currency)


@router.get(
    "/export",
    response_class=StreamingResponse,
    summary="Export a report section as CSV",
    responses={200: {"content": {"text/csv": {}}}},
)
def export_report(
    section: str = Query(..., description="One of: " + ", ".join(svc.EXPORTABLE_SECTIONS)),
    r: svc.ReportRange = Depends(report_range),
    currency: str | None = CurrencyParam,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    # export_section_csv is a generator function: calling it runs nothing (including its own
    # ValueError guard) until StreamingResponse starts iterating, by which point a 200 has
    # already been sent. Validate eagerly here instead of relying on a try/except around the call.
    if section not in svc.EXPORTABLE_SECTIONS:
        raise ValidationAppError(f"Unknown export section '{section}'.", {"fields": {"section": "invalid"}})
    generator = svc.export_section_csv(db, ctx.organization_id, section, r, currency)
    filename = f"report-{section}-{timezones.org_today(ctx.organization).isoformat()}.csv"
    return StreamingResponse(
        generator,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

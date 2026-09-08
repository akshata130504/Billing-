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
from backend.app.services import reports_service as svc

router = APIRouter()


def report_range(
    range: str = Query("this_month", description="One of: " + ", ".join(svc.REPORT_RANGE_KEYS)),
    start: date | None = Query(None, description="Required when range=custom"),
    end: date | None = Query(None, description="Required when range=custom"),
) -> svc.ReportRange:
    try:
        return svc.resolve_report_range(range, start=start, end=end)
    except ValueError as exc:
        raise ValidationAppError(str(exc), {"fields": {"range": str(exc)}})


@router.get("/dashboard", response_model=ReportKPIs, summary="Reports KPI cards")
def get_kpis(
    r: svc.ReportRange = Depends(report_range),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.kpis(db, ctx.organization_id, r)


@router.get("/revenue", response_model=RevenueAnalyticsOut, summary="Revenue analytics")
def get_revenue(
    r: svc.ReportRange = Depends(report_range),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.revenue_analytics(db, ctx.organization_id, r)


@router.get("/receivables", response_model=ReceivablesAnalyticsOut, summary="Receivables analytics")
def get_receivables(
    r: svc.ReportRange = Depends(report_range),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.receivables_analytics(db, ctx.organization_id, r)


@router.get("/invoices", response_model=InvoiceAnalyticsOut, summary="Invoice analytics")
def get_invoice_analytics(
    r: svc.ReportRange = Depends(report_range),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.invoice_analytics(db, ctx.organization_id, r)


@router.get("/payments", response_model=PaymentAnalyticsOut, summary="Payment analytics")
def get_payment_analytics(
    r: svc.ReportRange = Depends(report_range),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.payment_analytics(db, ctx.organization_id, r)


@router.get("/customers", response_model=CustomerAnalyticsOut, summary="Customer analytics")
def get_customer_analytics(
    r: svc.ReportRange = Depends(report_range),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.customer_analytics(db, ctx.organization_id, r)


@router.get("/products", response_model=ProductAnalyticsOut, summary="Product/plan analytics")
def get_product_analytics(
    r: svc.ReportRange = Depends(report_range),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.product_analytics(db, ctx.organization_id, r)


@router.get(
    "/export",
    response_class=StreamingResponse,
    summary="Export a report section as CSV",
    responses={200: {"content": {"text/csv": {}}}},
)
def export_report(
    section: str = Query(..., description="One of: " + ", ".join(svc.EXPORTABLE_SECTIONS)),
    r: svc.ReportRange = Depends(report_range),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    # export_section_csv is a generator function: calling it runs nothing (including its own
    # ValueError guard) until StreamingResponse starts iterating, by which point a 200 has
    # already been sent. Validate eagerly here instead of relying on a try/except around the call.
    if section not in svc.EXPORTABLE_SECTIONS:
        raise ValidationAppError(f"Unknown export section '{section}'.", {"fields": {"section": "invalid"}})
    generator = svc.export_section_csv(db, ctx.organization_id, section, r)
    filename = f"report-{section}-{date.today().isoformat()}.csv"
    return StreamingResponse(
        generator,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

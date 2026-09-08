"""Reports & Analytics: read-only aggregates over real invoice/payment/customer data.

Every number here is computed live from the same tables the rest of the app
uses (Invoice, Payment, Refund, InvoiceItem, Customer) — nothing is cached,
snapshotted, or fabricated. Two things are worth flagging honestly:

- `receivables_analytics.overdue_by_due_period` groups CURRENTLY overdue
  invoices by the period their due_date falls in — it is not a true
  historical point-in-time series (this app has no receivables snapshot
  table), so it answers "when did today's overdue balance become due"
  rather than "what was overdue on each past date".
- Product/plan analytics are fully real: `InvoiceItem` carries `product_id`
  and `plan_id`, so revenue/quantity can be grouped by them directly.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    Customer,
    CustomerStatus,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    Plan,
    Product,
    Refund,
    RefundStatus,
)
from backend.app.schemas.common_refs import customer_ref, money_str
from backend.app.services import collection_service, invoice_service
from backend.app.services.money import D, q2
from backend.app.services.payment_service import SETTLED_PAYMENT_STATUSES, effective_amount

REPORT_RANGE_KEYS = (
    "today",
    "this_week",
    "this_month",
    "last_month",
    "this_quarter",
    "this_year",
    "last_12_months",
    "custom",
)


@dataclass
class ReportRange:
    key: str
    start: date
    end: date  # inclusive


def resolve_report_range(range_key: str, start: Optional[date] = None, end: Optional[date] = None) -> ReportRange:
    today = date.today()
    key = range_key or "this_month"
    if key == "custom":
        if not start or not end:
            raise ValueError("start and end are required for a custom range.")
        if end < start:
            raise ValueError("end cannot be before start.")
        return ReportRange("custom", start, end)
    if key == "today":
        return ReportRange(key, today, today)
    if key == "this_week":
        return ReportRange(key, today - timedelta(days=today.weekday()), today)
    if key == "this_month":
        return ReportRange(key, today.replace(day=1), today)
    if key == "last_month":
        first_this_month = today.replace(day=1)
        last_day_prev = first_this_month - timedelta(days=1)
        return ReportRange(key, last_day_prev.replace(day=1), last_day_prev)
    if key == "this_quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        return ReportRange(key, today.replace(month=quarter_start_month, day=1), today)
    if key == "this_year":
        return ReportRange(key, today.replace(month=1, day=1), today)
    if key == "last_12_months":
        return ReportRange(key, today - timedelta(days=365), today)
    raise ValueError(f"Unknown range '{range_key}'. Expected one of {REPORT_RANGE_KEYS}.")


def _dt_bounds(r: ReportRange) -> Tuple[datetime, datetime]:
    lo = datetime.combine(r.start, time.min, tzinfo=timezone.utc)
    hi = datetime.combine(r.end, time.max, tzinfo=timezone.utc)
    return lo, hi


def _bucket_key(d: date, granularity: str) -> str:
    return d.isoformat() if granularity == "day" else f"{d.year:04d}-{d.month:02d}"


def _granularity_for(r: ReportRange) -> str:
    return "day" if (r.end - r.start).days <= 62 else "month"


def _empty_buckets(r: ReportRange, granularity: str) -> Dict[str, Decimal]:
    out: Dict[str, Decimal] = {}
    d = r.start
    if granularity == "day":
        while d <= r.end:
            out[_bucket_key(d, "day")] = Decimal("0")
            d += timedelta(days=1)
    else:
        d = r.start.replace(day=1)
        while d <= r.end:
            out[_bucket_key(d, "month")] = Decimal("0")
            year, month = (d.year, d.month + 1) if d.month < 12 else (d.year + 1, 1)
            d = d.replace(year=year, month=month, day=1)
    return out


# --- shared building blocks ---------------------------------------------------------------


def _invoiced_query(organization_id: str, r: ReportRange):
    return select(Invoice).where(
        Invoice.organization_id == organization_id,
        Invoice.status != InvoiceStatus.DRAFT,
        Invoice.issue_date >= r.start,
        Invoice.issue_date <= r.end,
    )


def _settled_payments_query(organization_id: str, r: ReportRange):
    lo, hi = _dt_bounds(r)
    return select(Payment).where(
        Payment.organization_id == organization_id,
        Payment.status.in_(SETTLED_PAYMENT_STATUSES),
        Payment.paid_at >= lo,
        Payment.paid_at <= hi,
    )


def kpis(db: Session, organization_id: str, r: ReportRange) -> Dict[str, Any]:
    payments = list(db.scalars(_settled_payments_query(organization_id, r)))
    gross_revenue = q2(sum((D(p.amount) for p in payments), Decimal("0")))
    net_revenue = q2(sum((effective_amount(p) for p in payments), Decimal("0")))

    invoices = list(db.scalars(_invoiced_query(organization_id, r)))
    total_invoiced = q2(sum((D(i.total) for i in invoices), Decimal("0")))
    invoice_count = len(invoices)

    outstanding = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount_due), 0)).where(
            Invoice.organization_id == organization_id, Invoice.status.in_(OPEN_INVOICE_STATUSES)
        )
    ) or Decimal("0")
    today = date.today()
    overdue = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount_due), 0)).where(
            Invoice.organization_id == organization_id,
            or_(
                Invoice.status == InvoiceStatus.OVERDUE,
                (Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]) & (Invoice.due_date < today)),
            ),
        )
    ) or Decimal("0")

    collection_rate = money_str(q2(net_revenue / total_invoiced * 100)) if total_invoiced > 0 else None
    avg_invoice = money_str(q2(total_invoiced / invoice_count)) if invoice_count else None

    return {
        "total_revenue": money_str(gross_revenue),
        "net_revenue": money_str(net_revenue),
        "total_invoiced": money_str(total_invoiced),
        "total_collected": money_str(net_revenue),
        "outstanding_receivables": money_str(outstanding),
        "overdue_receivables": money_str(overdue),
        "collection_rate": collection_rate,
        "average_invoice_value": avg_invoice,
    }


def _revenue_over_time(db: Session, organization_id: str, r: ReportRange, granularity: str) -> List[Dict[str, Any]]:
    buckets = _empty_buckets(r, granularity)
    for p in db.scalars(_settled_payments_query(organization_id, r)):
        key = _bucket_key(p.paid_at.date(), granularity)
        buckets[key] = buckets.get(key, Decimal("0")) + effective_amount(p)
    return [{"period": k, "amount": money_str(v)} for k, v in sorted(buckets.items())]


def _invoiced_vs_collected(db: Session, organization_id: str, r: ReportRange, granularity: str) -> List[Dict[str, Any]]:
    invoiced = _empty_buckets(r, granularity)
    for inv in db.scalars(_invoiced_query(organization_id, r)):
        key = _bucket_key(inv.issue_date, granularity)
        invoiced[key] = invoiced.get(key, Decimal("0")) + D(inv.total)
    collected = _empty_buckets(r, granularity)
    for p in db.scalars(_settled_payments_query(organization_id, r)):
        key = _bucket_key(p.paid_at.date(), granularity)
        collected[key] = collected.get(key, Decimal("0")) + effective_amount(p)
    keys = sorted(set(invoiced) | set(collected))
    return [
        {"period": k, "invoiced": money_str(invoiced.get(k, Decimal("0"))), "collected": money_str(collected.get(k, Decimal("0")))}
        for k in keys
    ]


def _top_customers_by_revenue(db: Session, organization_id: str, r: ReportRange, limit: int = 10) -> List[Dict[str, Any]]:
    totals: Dict[str, Decimal] = {}
    customers: Dict[str, Customer] = {}
    for p in db.scalars(_settled_payments_query(organization_id, r)):
        if not p.customer_id:
            continue
        totals[p.customer_id] = totals.get(p.customer_id, Decimal("0")) + effective_amount(p)
        if p.customer_id not in customers and p.customer is not None:
            customers[p.customer_id] = p.customer
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [
        {"customer": customer_ref(customers.get(cid)), "amount": money_str(amt)}
        for cid, amt in ranked
        if customers.get(cid) is not None
    ]


def _line_items_grouped(db: Session, organization_id: str, r: ReportRange, group_by: str) -> List[Dict[str, Any]]:
    """group_by: 'product' or 'plan'. Revenue + quantity per product/plan within the range."""
    column = InvoiceItem.product_id if group_by == "product" else InvoiceItem.plan_id
    label_model = Product if group_by == "product" else Plan
    stmt = (
        select(column, func.sum(InvoiceItem.amount), func.sum(InvoiceItem.quantity))
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .where(
            InvoiceItem.organization_id == organization_id,
            Invoice.status != InvoiceStatus.DRAFT,
            Invoice.issue_date >= r.start,
            Invoice.issue_date <= r.end,
            column.is_not(None),
        )
        .group_by(column)
    )
    rows = db.execute(stmt).all()
    if not rows:
        return []
    ids = [row[0] for row in rows]
    labels = {obj.id: obj.name for obj in db.scalars(select(label_model).where(label_model.id.in_(ids)))}
    out = [
        {
            "id": row[0],
            "name": labels.get(row[0], "Unknown"),
            "revenue": money_str(q2(D(row[1] or 0))),
            "quantity": str(row[2] or 0),
        }
        for row in rows
    ]
    out.sort(key=lambda x: D(x["revenue"]), reverse=True)
    return out


def revenue_analytics(db: Session, organization_id: str, r: ReportRange) -> Dict[str, Any]:
    granularity = _granularity_for(r)
    return {
        "granularity": granularity,
        "revenue_over_time": _revenue_over_time(db, organization_id, r, granularity),
        "invoiced_vs_collected": _invoiced_vs_collected(db, organization_id, r, granularity),
        "revenue_by_customer": _top_customers_by_revenue(db, organization_id, r),
        "revenue_by_product": _line_items_grouped(db, organization_id, r, "product"),
        "revenue_by_plan": _line_items_grouped(db, organization_id, r, "plan"),
    }


def receivables_analytics(db: Session, organization_id: str, r: ReportRange) -> Dict[str, Any]:
    open_invoices = list(db.scalars(select(Invoice).where(Invoice.organization_id == organization_id, Invoice.status.in_(OPEN_INVOICE_STATUSES))))

    aging: Dict[str, Dict[str, Any]] = {b: {"count": 0, "amount": Decimal("0")} for b in ("current", "1_30", "31_60", "61_90", "90_plus")}
    overdue_by_due_period: Dict[str, Decimal] = {}
    outstanding_by_customer: Dict[str, Decimal] = {}
    customers: Dict[str, Customer] = {}
    for inv in open_invoices:
        days = invoice_service.days_overdue(inv)
        bucket = collection_service.aging_bucket(days)
        aging[bucket]["count"] += 1
        aging[bucket]["amount"] += D(inv.amount_due)
        if days > 0 and inv.due_date:
            key = f"{inv.due_date.year:04d}-{inv.due_date.month:02d}"
            overdue_by_due_period[key] = overdue_by_due_period.get(key, Decimal("0")) + D(inv.amount_due)
        if inv.customer_id:
            outstanding_by_customer[inv.customer_id] = outstanding_by_customer.get(inv.customer_id, Decimal("0")) + D(inv.amount_due)
            if inv.customer_id not in customers and inv.customer is not None:
                customers[inv.customer_id] = inv.customer

    granularity = _granularity_for(r)
    invoiced_vs_collected = _invoiced_vs_collected(db, organization_id, r, granularity)
    collection_rate_trend = [
        {
            "period": row["period"],
            "rate": money_str(q2(D(row["collected"]) / D(row["invoiced"]) * 100)) if D(row["invoiced"]) > 0 else None,
        }
        for row in invoiced_vs_collected
    ]

    top_outstanding = sorted(outstanding_by_customer.items(), key=lambda kv: kv[1], reverse=True)[:10]

    paid_in_range = db.scalars(
        select(Invoice).where(
            Invoice.organization_id == organization_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at.is_not(None),
            Invoice.paid_at >= datetime.combine(r.start, time.min, tzinfo=timezone.utc),
            Invoice.paid_at <= datetime.combine(r.end, time.max, tzinfo=timezone.utc),
        )
    ).all()
    if paid_in_range:
        total_days = sum(((inv.paid_at.date() - inv.issue_date).days for inv in paid_in_range), 0)
        avg_days_to_payment = round(total_days / len(paid_in_range), 1)
    else:
        avg_days_to_payment = None

    return {
        "outstanding_by_aging": [{"bucket": b, "count": v["count"], "amount": money_str(v["amount"])} for b, v in aging.items()],
        "overdue_by_due_period": [{"period": k, "amount": money_str(v)} for k, v in sorted(overdue_by_due_period.items())],
        "collection_rate_trend": collection_rate_trend,
        "top_customers_by_outstanding": [
            {"customer": customer_ref(customers.get(cid)), "amount": money_str(amt)} for cid, amt in top_outstanding if customers.get(cid)
        ],
        "average_days_to_payment": avg_days_to_payment,
    }


def invoice_analytics(db: Session, organization_id: str, r: ReportRange) -> Dict[str, Any]:
    rows = db.execute(
        select(Invoice.status, func.count(), func.coalesce(func.sum(Invoice.total), 0))
        .where(Invoice.organization_id == organization_id, Invoice.issue_date >= r.start, Invoice.issue_date <= r.end)
        .group_by(Invoice.status)
    ).all()
    by_status = {status.value: {"count": count, "amount": money_str(q2(D(total)))} for status, count, total in rows}
    total_count = sum(v["count"] for v in by_status.values())
    total_amount = sum((D(v["amount"]) for v in by_status.values()), Decimal("0"))
    avg = money_str(q2(total_amount / total_count)) if total_count else None
    return {"by_status": by_status, "total_count": total_count, "average_invoice_amount": avg}


def payment_analytics(db: Session, organization_id: str, r: ReportRange) -> Dict[str, Any]:
    payments = list(db.scalars(_settled_payments_query(organization_id, r)))
    total_amount = q2(sum((D(p.amount) for p in payments), Decimal("0")))
    net_collected = q2(sum((effective_amount(p) for p in payments), Decimal("0")))

    method_totals: Dict[str, Decimal] = {}
    for p in payments:
        key = p.method.value
        method_totals[key] = method_totals.get(key, Decimal("0")) + D(p.amount)

    granularity = _granularity_for(r)
    trend = _revenue_over_time(db, organization_id, r, granularity)

    lo, hi = _dt_bounds(r)
    refund_amount = db.scalar(
        select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.organization_id == organization_id,
            Refund.status == RefundStatus.PROCESSED,
            Refund.created_at >= lo,
            Refund.created_at <= hi,
        )
    ) or Decimal("0")

    return {
        "total_payments": money_str(total_amount),
        "payment_count": len(payments),
        "method_breakdown": [{"method": k, "amount": money_str(v)} for k, v in sorted(method_totals.items(), key=lambda kv: kv[1], reverse=True)],
        "trend": trend,
        "refund_amount": money_str(q2(D(refund_amount))),
        "net_collected": money_str(net_collected),
    }


def customer_analytics(db: Session, organization_id: str, r: ReportRange) -> Dict[str, Any]:
    total_customers = db.scalar(select(func.count()).where(Customer.organization_id == organization_id)) or 0
    active_customers = db.scalar(
        select(func.count()).where(Customer.organization_id == organization_id, Customer.status == CustomerStatus.ACTIVE)
    ) or 0
    customers_with_outstanding = db.scalar(
        select(func.count(func.distinct(Invoice.customer_id))).where(
            Invoice.organization_id == organization_id, Invoice.status.in_(OPEN_INVOICE_STATUSES), Invoice.amount_due > 0
        )
    ) or 0
    return {
        "total_customers": total_customers,
        "active_customers": active_customers,
        "customers_with_outstanding_balance": customers_with_outstanding,
        "top_customers_by_revenue": _top_customers_by_revenue(db, organization_id, r),
        "top_customers_by_outstanding": receivables_analytics(db, organization_id, r)["top_customers_by_outstanding"],
    }


def product_analytics(db: Session, organization_id: str, r: ReportRange) -> Dict[str, Any]:
    by_product = _line_items_grouped(db, organization_id, r, "product")
    by_plan = _line_items_grouped(db, organization_id, r, "plan")
    best_selling = sorted(by_product, key=lambda x: D(x["quantity"]), reverse=True)[:10]

    plan_ids = [row["id"] for row in by_plan]
    pricing_model_totals: Dict[str, Decimal] = {}
    if plan_ids:
        plans = {p.id: p.pricing_model.value for p in db.scalars(select(Plan).where(Plan.id.in_(plan_ids)))}
        for row in by_plan:
            model = plans.get(row["id"], "unknown")
            pricing_model_totals[model] = pricing_model_totals.get(model, Decimal("0")) + D(row["revenue"])

    return {
        "best_selling": best_selling,
        "revenue_by_offering": by_product,
        "revenue_by_pricing_model": [{"pricing_model": k, "amount": money_str(v)} for k, v in pricing_model_totals.items()],
        "plan_revenue": by_plan,
        "quantity_sold": [{"id": row["id"], "name": row["name"], "quantity": row["quantity"]} for row in by_product],
    }


# --- CSV export ----------------------------------------------------------------------------

EXPORTABLE_SECTIONS = (
    "revenue_over_time",
    "invoiced_vs_collected",
    "revenue_by_customer",
    "revenue_by_product",
    "revenue_by_plan",
    "outstanding_by_aging",
    "top_customers_by_outstanding",
    "method_breakdown",
)


def export_section_csv(db: Session, organization_id: str, section: str, r: ReportRange) -> Iterator[str]:
    if section not in EXPORTABLE_SECTIONS:
        raise ValueError(f"Unknown export section '{section}'.")
    revenue = revenue_analytics(db, organization_id, r)
    receivables = receivables_analytics(db, organization_id, r)
    payments = payment_analytics(db, organization_id, r)
    rows_by_section = {
        "revenue_over_time": revenue["revenue_over_time"],
        "invoiced_vs_collected": revenue["invoiced_vs_collected"],
        "revenue_by_customer": [{"customer": row["customer"]["display_name"], "amount": row["amount"]} for row in revenue["revenue_by_customer"]],
        "revenue_by_product": [{"product": row["name"], "revenue": row["revenue"], "quantity": row["quantity"]} for row in revenue["revenue_by_product"]],
        "revenue_by_plan": [{"plan": row["name"], "revenue": row["revenue"], "quantity": row["quantity"]} for row in revenue["revenue_by_plan"]],
        "outstanding_by_aging": receivables["outstanding_by_aging"],
        "top_customers_by_outstanding": [{"customer": row["customer"]["display_name"], "amount": row["amount"]} for row in receivables["top_customers_by_outstanding"]],
        "method_breakdown": payments["method_breakdown"],
    }
    rows = rows_by_section[section]
    buffer = io.StringIO()
    if not rows:
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["No data for this range."])
        yield buffer.getvalue()
        return
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    for row in rows:
        writer.writerow(row)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


__all__ = [
    "REPORT_RANGE_KEYS",
    "ReportRange",
    "resolve_report_range",
    "kpis",
    "revenue_analytics",
    "receivables_analytics",
    "invoice_analytics",
    "payment_analytics",
    "customer_analytics",
    "product_analytics",
    "EXPORTABLE_SECTIONS",
    "export_section_csv",
]

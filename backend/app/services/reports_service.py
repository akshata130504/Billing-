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
- Money is reported one currency at a time (there is no FX conversion): see
  `currency_totals` and the `currency` argument of each analytics function.
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
from backend.app.services import currency_totals, invoice_service, timezones
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
    # The organization's timezone: start/end are its local business days, and instants
    # (paid_at, created_at) are bucketed by their local date. None = UTC.
    tz: Any = None


def resolve_report_range(
    range_key: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    *,
    today: Optional[date] = None,
    tz: Any = None,
) -> ReportRange:
    """`today` should be the organization's local date (timezones.org_today) and `tz` its
    timezone (the endpoints and the scheduled export pass both). Without `today` the date
    is taken in `tz`; with neither, the legacy process-local date is kept for callers that
    have no organization context."""
    if today is None:
        today = timezones.org_today(tz) if tz is not None else date.today()
    key = range_key or "this_month"
    if key == "custom":
        if not start or not end:
            raise ValueError("start and end are required for a custom range.")
        if end < start:
            raise ValueError("end cannot be before start.")
        return ReportRange("custom", start, end, tz)
    if key == "today":
        return ReportRange(key, today, today, tz)
    if key == "this_week":
        return ReportRange(key, today - timedelta(days=today.weekday()), today, tz)
    if key == "this_month":
        return ReportRange(key, today.replace(day=1), today, tz)
    if key == "last_month":
        first_this_month = today.replace(day=1)
        last_day_prev = first_this_month - timedelta(days=1)
        return ReportRange(key, last_day_prev.replace(day=1), last_day_prev, tz)
    if key == "this_quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        return ReportRange(key, today.replace(month=quarter_start_month, day=1), today, tz)
    if key == "this_year":
        return ReportRange(key, today.replace(month=1, day=1), today, tz)
    if key == "last_12_months":
        return ReportRange(key, today - timedelta(days=365), today, tz)
    raise ValueError(f"Unknown range '{range_key}'. Expected one of {REPORT_RANGE_KEYS}.")


def _range_tz(r: ReportRange) -> Any:
    return r.tz if r.tz is not None else timezone.utc


def _dt_bounds(r: ReportRange) -> Tuple[datetime, datetime]:
    """Half-open [start 00:00 local, end+1 00:00 local) as UTC instants (compare with `<` hi)."""
    lo, hi = timezones.range_bounds_utc(r.start, r.end, _range_tz(r))
    return lo, hi


def _local_date(value: datetime, r: ReportRange) -> date:
    return timezones.local_date(value, _range_tz(r))


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
#
# Currency: there is no FX conversion, so every money figure below is for ONE currency.
# Each analytics function takes `currency` (default: the organization's base currency),
# filters invoices/payments to it and labels its output with it; `currencies` lists every
# currency the organization has invoices or payments in, so the UI can offer a switch.


def _base_currency(db: Session, organization_id: str) -> str:
    return currency_totals.org_base_currency(db, organization_id)


def _resolve_currency(db: Session, organization_id: str, currency: Optional[str]) -> str:
    return currency_totals.norm(currency) if currency else _base_currency(db, organization_id)


def report_currencies(db: Session, organization_id: str) -> List[str]:
    """Every currency with issued invoices or payments, base currency first (always present)."""
    base = _base_currency(db, organization_id)
    found = set(
        db.scalars(
            select(func.upper(Invoice.currency))
            .where(Invoice.organization_id == organization_id, Invoice.status.not_in([InvoiceStatus.DRAFT, InvoiceStatus.VOID]))
            .distinct()
        )
    )
    found |= set(db.scalars(select(func.upper(Payment.currency)).where(Payment.organization_id == organization_id).distinct()))
    return currency_totals.order_currencies(found | {base}, base)


def _invoice_currency_is(currency: str):
    return func.upper(Invoice.currency) == currency


def _payment_currency_is(currency: str):
    return func.upper(Payment.currency) == currency


def _invoiced_query(organization_id: str, r: ReportRange, currency: str):
    return select(Invoice).where(
        Invoice.organization_id == organization_id,
        # Drafts were never issued and voided invoices were cancelled: neither is revenue.
        Invoice.status.not_in([InvoiceStatus.DRAFT, InvoiceStatus.VOID]),
        Invoice.issue_date >= r.start,
        Invoice.issue_date <= r.end,
        _invoice_currency_is(currency),
    )


def _settled_payments_query(organization_id: str, r: ReportRange, currency: str):
    lo, hi = _dt_bounds(r)
    return select(Payment).where(
        Payment.organization_id == organization_id,
        Payment.status.in_(SETTLED_PAYMENT_STATUSES),
        Payment.paid_at >= lo,
        Payment.paid_at < hi,
        _payment_currency_is(currency),
    )


def _kpis_for_currency(db: Session, organization_id: str, r: ReportRange, currency: str, today: date) -> Dict[str, Any]:
    payments = list(db.scalars(_settled_payments_query(organization_id, r, currency)))
    gross_revenue = q2(sum((D(p.amount) for p in payments), Decimal("0")))
    net_revenue = q2(sum((effective_amount(p) for p in payments), Decimal("0")))

    invoices = list(db.scalars(_invoiced_query(organization_id, r, currency)))
    total_invoiced = q2(sum((D(i.total) for i in invoices), Decimal("0")))
    invoice_count = len(invoices)

    outstanding = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount_due), 0)).where(
            Invoice.organization_id == organization_id,
            Invoice.status.in_(OPEN_INVOICE_STATUSES),
            _invoice_currency_is(currency),
        )
    ) or Decimal("0")
    overdue = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount_due), 0)).where(
            Invoice.organization_id == organization_id,
            or_(
                Invoice.status == InvoiceStatus.OVERDUE,
                (Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]) & (Invoice.due_date < today)),
            ),
            _invoice_currency_is(currency),
        )
    ) or Decimal("0")

    avg_invoice = money_str(q2(total_invoiced / invoice_count)) if invoice_count else None

    return {
        "currency": currency,
        "total_revenue": money_str(gross_revenue),
        "net_revenue": money_str(net_revenue),
        "total_invoiced": money_str(total_invoiced),
        "total_collected": money_str(net_revenue),
        "outstanding_receivables": money_str(outstanding),
        "overdue_receivables": money_str(overdue),
        "collection_rate": currency_totals.collection_rate(net_revenue, total_invoiced),
        "average_invoice_value": avg_invoice,
        "invoice_count": invoice_count,
    }


def collection_rate_for(db: Session, organization_id: str, r: ReportRange, currency: str) -> Optional[str]:
    """`currency_totals.collection_rate` over `r` in one currency - the figure the Reports KPI
    card shows, reused by the Collections dashboard so the two always agree."""
    return _kpis_for_currency(db, organization_id, r, currency, timezones.org_today_for_id(db, organization_id))[
        "collection_rate"
    ]


def kpis(db: Session, organization_id: str, r: ReportRange, currency: Optional[str] = None) -> Dict[str, Any]:
    """KPI cards in one currency (default: base; the top-level fields) plus `by_currency`
    with the same KPIs for every currency the organization uses."""
    currency = _resolve_currency(db, organization_id, currency)
    currencies = report_currencies(db, organization_id)
    if currency not in currencies:
        currencies.append(currency)
    today = timezones.org_today_for_id(db, organization_id)
    by_currency = [_kpis_for_currency(db, organization_id, r, cur, today) for cur in currencies]
    selected = next(row for row in by_currency if row["currency"] == currency)
    return {**selected, "currencies": currencies, "by_currency": by_currency}


def _revenue_over_time(db: Session, organization_id: str, r: ReportRange, granularity: str, currency: str) -> List[Dict[str, Any]]:
    buckets = _empty_buckets(r, granularity)
    for p in db.scalars(_settled_payments_query(organization_id, r, currency)):
        key = _bucket_key(_local_date(p.paid_at, r), granularity)
        buckets[key] = buckets.get(key, Decimal("0")) + effective_amount(p)
    return [{"period": k, "amount": money_str(v)} for k, v in sorted(buckets.items())]


def _invoiced_vs_collected(db: Session, organization_id: str, r: ReportRange, granularity: str, currency: str) -> List[Dict[str, Any]]:
    invoiced = _empty_buckets(r, granularity)
    for inv in db.scalars(_invoiced_query(organization_id, r, currency)):
        key = _bucket_key(inv.issue_date, granularity)
        invoiced[key] = invoiced.get(key, Decimal("0")) + D(inv.total)
    collected = _empty_buckets(r, granularity)
    for p in db.scalars(_settled_payments_query(organization_id, r, currency)):
        key = _bucket_key(_local_date(p.paid_at, r), granularity)
        collected[key] = collected.get(key, Decimal("0")) + effective_amount(p)
    keys = sorted(set(invoiced) | set(collected))
    return [
        {"period": k, "invoiced": money_str(invoiced.get(k, Decimal("0"))), "collected": money_str(collected.get(k, Decimal("0")))}
        for k in keys
    ]


def _top_customers_by_revenue(db: Session, organization_id: str, r: ReportRange, currency: str, limit: int = 10) -> List[Dict[str, Any]]:
    totals: Dict[str, Decimal] = {}
    customers: Dict[str, Customer] = {}
    for p in db.scalars(_settled_payments_query(organization_id, r, currency)):
        if not p.customer_id:
            continue
        totals[p.customer_id] = totals.get(p.customer_id, Decimal("0")) + effective_amount(p)
        if p.customer_id not in customers and p.customer is not None:
            customers[p.customer_id] = p.customer
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [
        {"customer": customer_ref(customers.get(cid)), "amount": money_str(amt), "currency": currency}
        for cid, amt in ranked
        if customers.get(cid) is not None
    ]


def _line_items_grouped(db: Session, organization_id: str, r: ReportRange, group_by: str, currency: str) -> List[Dict[str, Any]]:
    """group_by: 'product' or 'plan'. Revenue + quantity per product/plan within the range."""
    column = InvoiceItem.product_id if group_by == "product" else InvoiceItem.plan_id
    label_model = Product if group_by == "product" else Plan
    stmt = (
        select(column, func.sum(InvoiceItem.amount), func.sum(InvoiceItem.quantity))
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .where(
            InvoiceItem.organization_id == organization_id,
            # Same rule as _invoiced_query: drafts were never issued, voided invoices were cancelled.
            Invoice.status.not_in([InvoiceStatus.DRAFT, InvoiceStatus.VOID]),
            Invoice.issue_date >= r.start,
            Invoice.issue_date <= r.end,
            _invoice_currency_is(currency),
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
            "currency": currency,
        }
        for row in rows
    ]
    out.sort(key=lambda x: D(x["revenue"]), reverse=True)
    return out


def revenue_analytics(db: Session, organization_id: str, r: ReportRange, currency: Optional[str] = None) -> Dict[str, Any]:
    currency = _resolve_currency(db, organization_id, currency)
    granularity = _granularity_for(r)
    return {
        "currency": currency,
        "currencies": report_currencies(db, organization_id),
        "granularity": granularity,
        "revenue_over_time": _revenue_over_time(db, organization_id, r, granularity, currency),
        "invoiced_vs_collected": _invoiced_vs_collected(db, organization_id, r, granularity, currency),
        "revenue_by_customer": _top_customers_by_revenue(db, organization_id, r, currency),
        "revenue_by_product": _line_items_grouped(db, organization_id, r, "product", currency),
        "revenue_by_plan": _line_items_grouped(db, organization_id, r, "plan", currency),
    }


def _aging_bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1_30"
    if days_overdue <= 60:
        return "31_60"
    if days_overdue <= 90:
        return "61_90"
    return "90_plus"


def receivables_analytics(db: Session, organization_id: str, r: ReportRange, currency: Optional[str] = None) -> Dict[str, Any]:
    currency = _resolve_currency(db, organization_id, currency)
    open_invoices = list(
        db.scalars(
            select(Invoice).where(
                Invoice.organization_id == organization_id,
                Invoice.status.in_(OPEN_INVOICE_STATUSES),
                _invoice_currency_is(currency),
            )
        )
    )

    aging: Dict[str, Dict[str, Any]] = {b: {"count": 0, "amount": Decimal("0")} for b in ("current", "1_30", "31_60", "61_90", "90_plus")}
    overdue_by_due_period: Dict[str, Decimal] = {}
    outstanding_by_customer: Dict[str, Decimal] = {}
    customers: Dict[str, Customer] = {}
    for inv in open_invoices:
        days = invoice_service.days_overdue(inv)
        bucket = _aging_bucket(days)
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
    invoiced_vs_collected = _invoiced_vs_collected(db, organization_id, r, granularity, currency)
    collection_rate_trend = [
        {"period": row["period"], "rate": currency_totals.collection_rate(row["collected"], row["invoiced"])}
        for row in invoiced_vs_collected
    ]

    top_outstanding = sorted(outstanding_by_customer.items(), key=lambda kv: kv[1], reverse=True)[:10]

    paid_lo, paid_hi = _dt_bounds(r)
    paid_in_range = db.scalars(
        select(Invoice).where(
            Invoice.organization_id == organization_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at.is_not(None),
            Invoice.paid_at >= paid_lo,
            Invoice.paid_at < paid_hi,
        )
    ).all()
    if paid_in_range:
        total_days = sum(((_local_date(inv.paid_at, r) - inv.issue_date).days for inv in paid_in_range), 0)
        avg_days_to_payment = round(total_days / len(paid_in_range), 1)
    else:
        avg_days_to_payment = None

    return {
        "currency": currency,
        "currencies": report_currencies(db, organization_id),
        "outstanding_by_aging": [{"bucket": b, "count": v["count"], "amount": money_str(v["amount"])} for b, v in aging.items()],
        "overdue_by_due_period": [{"period": k, "amount": money_str(v)} for k, v in sorted(overdue_by_due_period.items())],
        "collection_rate_trend": collection_rate_trend,
        "top_customers_by_outstanding": [
            {"customer": customer_ref(customers.get(cid)), "amount": money_str(amt), "currency": currency}
            for cid, amt in top_outstanding
            if customers.get(cid)
        ],
        "average_days_to_payment": avg_days_to_payment,
    }


def invoice_analytics(db: Session, organization_id: str, r: ReportRange, currency: Optional[str] = None) -> Dict[str, Any]:
    currency = _resolve_currency(db, organization_id, currency)
    rows = db.execute(
        select(Invoice.status, func.count(), func.coalesce(func.sum(Invoice.total), 0))
        .where(
            Invoice.organization_id == organization_id,
            Invoice.issue_date >= r.start,
            Invoice.issue_date <= r.end,
            _invoice_currency_is(currency),
        )
        .group_by(Invoice.status)
    ).all()
    by_status = {status.value: {"count": count, "amount": money_str(q2(D(total)))} for status, count, total in rows}
    total_count = sum(v["count"] for v in by_status.values())
    total_amount = sum((D(v["amount"]) for v in by_status.values()), Decimal("0"))
    avg = money_str(q2(total_amount / total_count)) if total_count else None
    return {
        "currency": currency,
        "currencies": report_currencies(db, organization_id),
        "by_status": by_status,
        "total_count": total_count,
        "average_invoice_amount": avg,
    }


def payment_analytics(db: Session, organization_id: str, r: ReportRange, currency: Optional[str] = None) -> Dict[str, Any]:
    currency = _resolve_currency(db, organization_id, currency)
    payments = list(db.scalars(_settled_payments_query(organization_id, r, currency)))
    total_amount = q2(sum((D(p.amount) for p in payments), Decimal("0")))
    net_collected = q2(sum((effective_amount(p) for p in payments), Decimal("0")))

    method_totals: Dict[str, Decimal] = {}
    for p in payments:
        key = p.method.value
        method_totals[key] = method_totals.get(key, Decimal("0")) + D(p.amount)

    granularity = _granularity_for(r)
    trend = _revenue_over_time(db, organization_id, r, granularity, currency)

    lo, hi = _dt_bounds(r)
    # A refund is in its payment's currency.
    refund_amount = db.scalar(
        select(func.coalesce(func.sum(Refund.amount), 0))
        .join(Payment, Payment.id == Refund.payment_id)
        .where(
            Refund.organization_id == organization_id,
            Refund.status == RefundStatus.PROCESSED,
            Refund.created_at >= lo,
            Refund.created_at < hi,
            _payment_currency_is(currency),
        )
    ) or Decimal("0")

    return {
        "currency": currency,
        "currencies": report_currencies(db, organization_id),
        "total_payments": money_str(total_amount),
        "payment_count": len(payments),
        "method_breakdown": [
            {"method": k, "amount": money_str(v), "currency": currency}
            for k, v in sorted(method_totals.items(), key=lambda kv: kv[1], reverse=True)
        ],
        "trend": trend,
        "refund_amount": money_str(q2(D(refund_amount))),
        "net_collected": money_str(net_collected),
    }


def customer_analytics(db: Session, organization_id: str, r: ReportRange, currency: Optional[str] = None) -> Dict[str, Any]:
    currency = _resolve_currency(db, organization_id, currency)
    total_customers = db.scalar(select(func.count()).where(Customer.organization_id == organization_id)) or 0
    active_customers = db.scalar(
        select(func.count()).where(Customer.organization_id == organization_id, Customer.status == CustomerStatus.ACTIVE)
    ) or 0
    # A head count, not money: customers owing anything in any currency.
    customers_with_outstanding = db.scalar(
        select(func.count(func.distinct(Invoice.customer_id))).where(
            Invoice.organization_id == organization_id, Invoice.status.in_(OPEN_INVOICE_STATUSES), Invoice.amount_due > 0
        )
    ) or 0
    return {
        "currency": currency,
        "currencies": report_currencies(db, organization_id),
        "total_customers": total_customers,
        "active_customers": active_customers,
        "customers_with_outstanding_balance": customers_with_outstanding,
        "top_customers_by_revenue": _top_customers_by_revenue(db, organization_id, r, currency),
        "top_customers_by_outstanding": receivables_analytics(db, organization_id, r, currency)["top_customers_by_outstanding"],
    }


def product_analytics(db: Session, organization_id: str, r: ReportRange, currency: Optional[str] = None) -> Dict[str, Any]:
    currency = _resolve_currency(db, organization_id, currency)
    by_product = _line_items_grouped(db, organization_id, r, "product", currency)
    by_plan = _line_items_grouped(db, organization_id, r, "plan", currency)
    best_selling = sorted(by_product, key=lambda x: D(x["quantity"]), reverse=True)[:10]

    plan_ids = [row["id"] for row in by_plan]
    pricing_model_totals: Dict[str, Decimal] = {}
    if plan_ids:
        plans = {p.id: p.pricing_model.value for p in db.scalars(select(Plan).where(Plan.id.in_(plan_ids)))}
        for row in by_plan:
            model = plans.get(row["id"], "unknown")
            pricing_model_totals[model] = pricing_model_totals.get(model, Decimal("0")) + D(row["revenue"])

    return {
        "currency": currency,
        "currencies": report_currencies(db, organization_id),
        "best_selling": best_selling,
        "revenue_by_offering": by_product,
        "revenue_by_pricing_model": [
            {"pricing_model": k, "amount": money_str(v), "currency": currency} for k, v in pricing_model_totals.items()
        ],
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


def _section_rows(db: Session, organization_id: str, section: str, r: ReportRange, currency: str) -> List[Dict[str, Any]]:
    """One currency's rows of a section; every row starts with its `currency` column."""
    if section in ("revenue_over_time", "invoiced_vs_collected", "revenue_by_customer", "revenue_by_product", "revenue_by_plan"):
        revenue = revenue_analytics(db, organization_id, r, currency)
        rows = {
            "revenue_over_time": revenue["revenue_over_time"],
            "invoiced_vs_collected": revenue["invoiced_vs_collected"],
            "revenue_by_customer": [{"customer": row["customer"]["display_name"], "amount": row["amount"]} for row in revenue["revenue_by_customer"]],
            "revenue_by_product": [{"product": row["name"], "revenue": row["revenue"], "quantity": row["quantity"]} for row in revenue["revenue_by_product"]],
            "revenue_by_plan": [{"plan": row["name"], "revenue": row["revenue"], "quantity": row["quantity"]} for row in revenue["revenue_by_plan"]],
        }[section]
    elif section in ("outstanding_by_aging", "top_customers_by_outstanding"):
        receivables = receivables_analytics(db, organization_id, r, currency)
        if section == "outstanding_by_aging":
            rows = receivables["outstanding_by_aging"]
        else:
            rows = [{"customer": row["customer"]["display_name"], "amount": row["amount"]} for row in receivables["top_customers_by_outstanding"]]
    else:
        rows = [{"method": row["method"], "amount": row["amount"]} for row in payment_analytics(db, organization_id, r, currency)["method_breakdown"]]
    return [{"currency": currency, **row} for row in rows]


def _has_activity(row: Dict[str, Any]) -> bool:
    """False for the zero-filled rows of a currency with nothing in the range."""
    return any(D(v) != 0 for k, v in row.items() if k in ("amount", "invoiced", "collected", "revenue", "count"))


def export_section_csv(
    db: Session, organization_id: str, section: str, r: ReportRange, currency: Optional[str] = None
) -> Iterator[str]:
    """CSV of one section. Each row carries a `currency` column; without `currency` every
    currency the organization uses is exported (base currency first), never summed."""
    if section not in EXPORTABLE_SECTIONS:
        raise ValueError(f"Unknown export section '{section}'.")
    currencies = [currency_totals.norm(currency)] if currency else report_currencies(db, organization_id)
    rows: List[Dict[str, Any]] = []
    for index, cur in enumerate(currencies):
        cur_rows = _section_rows(db, organization_id, section, r, cur)
        # Other currencies' all-zero time buckets / aging buckets are noise; the base
        # (first) currency keeps its full zero-filled shape.
        if index > 0 and not any(_has_activity(row) for row in cur_rows):
            continue
        rows.extend(cur_rows)
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
    "report_currencies",
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

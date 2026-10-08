"""Server-side summary counters for dashboards and list-page KPI tiles.

Replaces counters the frontend used to derive client-side (sums over the loaded
page) or with one `page_size=1` request per status. Every function:

* is scoped to one organization (every query filters on organization_id - joins
  included - so nothing crosses tenants);
* runs a fixed number of GROUP BY aggregate queries (no per-row queries);
* never adds money in different currencies together - amounts are reported per
  currency, sorted by currency code, with the org base currency first;
* returns every known status key (zero-filled), so an empty org gets a complete,
  all-zero response rather than missing keys.

Date semantics: range filters are inclusive calendar dates in the organization's
timezone (instants are compared against [local 00:00, local 00:00) in UTC). Invoices, quotes and
credit notes filter on issue_date; payments on paid_at; new customers on
created_at. Receivables, subscription statuses and MRR are point-in-time (now).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, case, func, or_, select, true
from sqlalchemy.orm import Session

from backend.app.core.exceptions import ValidationAppError
from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    Customer,
    CustomerStatus,
    Invoice,
    InvoiceStatus,
    Payment,
    Quote,
    QuoteStatus,
    Subscription,
    SubscriptionStatus,
)
from backend.app.models.catalog_cpq import CPQDeal, CPQDealStatus, Offering, OfferingType, PriceBook, PriceBookStatus
from backend.app.services.invoice_service import SETTLED_PAYMENT_STATUSES
from backend.app.services import timezones
from backend.app.services.money import D, q2


def _money(value: Any) -> str:
    return str(q2(D(value if value is not None else 0)))


def _key(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _cur(value: Optional[str], default: str = "INR") -> str:
    return (value or default).upper()


def _order_currencies(currencies: Iterable[str], base: Optional[str]) -> List[str]:
    base = (base or "").upper()
    return sorted(set(currencies), key=lambda c: (c != base, c))


def _bounds(start: Optional[date], end: Optional[date], tz: Any) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Inclusive local dates -> half-open UTC instants in the organization's timezone."""
    return timezones.range_bounds_utc(start, end, tz)


def validate_range(date_from: Optional[date], date_to: Optional[date]) -> None:
    if date_from and date_to and date_from > date_to:
        raise ValidationAppError("date_from must be on or before date_to.", {"fields": {"date_from": "after date_to"}})


def _date_filters(column, date_from: Optional[date], date_to: Optional[date]) -> List[Any]:
    conds = []
    if date_from:
        conds.append(column >= date_from)
    if date_to:
        conds.append(column <= date_to)
    return conds


def _base_currency(organization) -> str:
    return _cur(getattr(organization, "default_currency", None))


# --- quotes ------------------------------------------------------------------------------------------------------

# KPI groupings used by the quotes list page tiles.
QUOTE_GROUPS: Dict[str, Tuple[QuoteStatus, ...]] = {
    "draft": (QuoteStatus.DRAFT,),
    "pending_approval": (QuoteStatus.PENDING_APPROVAL,),
    "sent": (QuoteStatus.SENT, QuoteStatus.VIEWED),
    "accepted": (
        QuoteStatus.ACCEPTED,
        QuoteStatus.PARTIALLY_INVOICED,
        QuoteStatus.INVOICED,
        QuoteStatus.CONVERTED,
    ),
}
# Quotes still in play (value of the open pipeline).
OPEN_QUOTE_STATUSES = (
    QuoteStatus.DRAFT,
    QuoteStatus.PENDING_APPROVAL,
    QuoteStatus.APPROVED,
    QuoteStatus.SENT,
    QuoteStatus.VIEWED,
    QuoteStatus.ACCEPTED,
    QuoteStatus.PARTIALLY_INVOICED,
)


def quotes_summary(
    db: Session,
    organization,
    *,
    search: Optional[str] = None,
    customer_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> Dict[str, Any]:
    """Counts and values of quotes by status, with the same filters as GET /quotes."""
    validate_range(date_from, date_to)
    org_id = organization.id
    try:  # keep counts consistent with GET /quotes, which persists sent/viewed -> expired first
        from backend.app.services.quote_service import expire_stale_quotes

        expire_stale_quotes(db, org_id)
    except Exception:  # pragma: no cover - a read model must not fail on housekeeping
        db.rollback()

    stmt = select(Quote.status, Quote.currency, func.count(Quote.id), func.coalesce(func.sum(Quote.total), 0)).where(
        Quote.organization_id == org_id, *_date_filters(Quote.issue_date, date_from, date_to)
    )
    if customer_id:
        stmt = stmt.where(Quote.customer_id == customer_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.outerjoin(
            Customer, and_(Customer.id == Quote.customer_id, Customer.organization_id == org_id)
        ).where(
            or_(
                Quote.quote_number.ilike(like),
                Quote.title.ilike(like),
                Customer.display_name.ilike(like),
                Customer.company_name.ilike(like),
            )
        )
    rows = db.execute(stmt.group_by(Quote.status, Quote.currency)).all()

    by_status = {s.value: 0 for s in QuoteStatus}
    value: Dict[str, Dict[str, Decimal]] = {}
    open_value: Dict[str, Decimal] = {}
    counts_by_currency: Dict[str, int] = {}
    for status, currency, count, total in rows:
        key = _key(status)
        cur = _cur(currency)
        by_status[key] = by_status.get(key, 0) + int(count)
        value.setdefault(cur, {"total": Decimal("0")})["total"] += D(total)
        counts_by_currency[cur] = counts_by_currency.get(cur, 0) + int(count)
        if key in {s.value for s in OPEN_QUOTE_STATUSES}:
            open_value[cur] = open_value.get(cur, Decimal("0")) + D(total)

    base = _base_currency(organization)
    currencies = _order_currencies(value.keys(), base)
    return {
        "total_count": sum(by_status.values()),
        "by_status": by_status,
        "groups": {name: sum(by_status[s.value] for s in statuses) for name, statuses in QUOTE_GROUPS.items()},
        "value_by_currency": [
            {
                "currency": cur,
                "count": counts_by_currency.get(cur, 0),
                "total": _money(value[cur]["total"]),
                "open_total": _money(open_value.get(cur, 0)),
            }
            for cur in currencies
        ],
        "base_currency": base,
    }


# --- catalog -----------------------------------------------------------------------------------------------------


def catalog_summary(db: Session, organization, *, search: Optional[str] = None) -> Dict[str, Any]:
    """Offering counts by type / active flag and price book counts by status."""
    org_id = organization.id
    stmt = select(Offering.type, Offering.is_active, func.count(Offering.id)).where(Offering.organization_id == org_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Offering.name.ilike(like), Offering.sku.ilike(like)))
    by_type = {t.value: 0 for t in OfferingType}
    active_by_type = {t.value: 0 for t in OfferingType}
    inactive_by_type = {t.value: 0 for t in OfferingType}
    active = inactive = 0
    for otype, is_active, count in db.execute(stmt.group_by(Offering.type, Offering.is_active)).all():
        by_type[_key(otype)] = by_type.get(_key(otype), 0) + int(count)
        bucket = active_by_type if is_active else inactive_by_type
        bucket[_key(otype)] = bucket.get(_key(otype), 0) + int(count)
        if is_active:
            active += int(count)
        else:
            inactive += int(count)

    pb_stmt = select(PriceBook.status, func.count(PriceBook.id)).where(PriceBook.organization_id == org_id)
    if search:
        like = f"%{search.strip()}%"
        pb_stmt = pb_stmt.where(or_(PriceBook.name.ilike(like), PriceBook.customer_segment.ilike(like)))
    pb_by_status = {s.value: 0 for s in PriceBookStatus}
    for status, count in db.execute(pb_stmt.group_by(PriceBook.status)).all():
        pb_by_status[_key(status)] = pb_by_status.get(_key(status), 0) + int(count)

    return {
        "offerings": {
            "total": active + inactive,
            "active": active,
            "inactive": inactive,
            "by_type": by_type,
            "active_by_type": active_by_type,
            "inactive_by_type": inactive_by_type,
        },
        "price_books": {"total": sum(pb_by_status.values()), "by_status": pb_by_status},
    }


# --- CPQ deals ---------------------------------------------------------------------------------------------------

DEAL_GROUPS: Dict[str, Tuple[CPQDealStatus, ...]] = {
    "pending": (CPQDealStatus.PENDING_APPROVAL,),
    "approved": tuple(s for s in CPQDealStatus if s.value in ("approved", "configured")),
    "converted": tuple(s for s in CPQDealStatus if s.value == "converted"),
}


def deals_summary(
    db: Session,
    organization,
    *,
    customer_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> Dict[str, Any]:
    """CPQ deal counts by status and deal value per currency (date filter on created_at)."""
    validate_range(date_from, date_to)
    lo, hi = _bounds(date_from, date_to, timezones.resolve_tz(organization))
    stmt = select(CPQDeal.status, CPQDeal.currency, func.count(CPQDeal.id), func.coalesce(func.sum(CPQDeal.total), 0)).where(
        CPQDeal.organization_id == organization.id
    )
    if customer_id:
        stmt = stmt.where(CPQDeal.customer_id == customer_id)
    if lo is not None:
        stmt = stmt.where(CPQDeal.created_at >= lo)
    if hi is not None:
        stmt = stmt.where(CPQDeal.created_at < hi)
    by_status = {s.value: 0 for s in CPQDealStatus}
    totals: Dict[str, Decimal] = {}
    counts: Dict[str, int] = {}
    for status, currency, count, total in db.execute(stmt.group_by(CPQDeal.status, CPQDeal.currency)).all():
        by_status[_key(status)] = by_status.get(_key(status), 0) + int(count)
        cur = _cur(currency)
        totals[cur] = totals.get(cur, Decimal("0")) + D(total)
        counts[cur] = counts.get(cur, 0) + int(count)
    base = _base_currency(organization)
    return {
        "total_count": sum(by_status.values()),
        "by_status": by_status,
        "groups": {name: sum(by_status[s.value] for s in statuses) for name, statuses in DEAL_GROUPS.items()},
        "value_by_currency": [
            {"currency": cur, "count": counts[cur], "total": _money(totals[cur])} for cur in _order_currencies(totals, base)
        ],
        "base_currency": base,
    }


# --- organization financial summary ------------------------------------------------------------------------------


def financial_summary(
    db: Session,
    organization,
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> Dict[str, Any]:
    """One-call dashboard counters: invoices, receivables, payments collected, subscriptions,
    MRR, quotes, credit notes and customers - all currency-aware."""
    validate_range(date_from, date_to)
    org_id = organization.id
    base = _base_currency(organization)
    today = timezones.org_today(organization)
    lo, hi = _bounds(date_from, date_to, timezones.resolve_tz(organization))

    # Invoices issued in range, by status and currency (1 query).
    inv_rows = db.execute(
        select(
            Invoice.status,
            Invoice.currency,
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.total), 0),
            func.coalesce(func.sum(Invoice.amount_paid), 0),
            func.coalesce(func.sum(Invoice.amount_due), 0),
        )
        .where(Invoice.organization_id == org_id, *_date_filters(Invoice.issue_date, date_from, date_to))
        .group_by(Invoice.status, Invoice.currency)
    ).all()
    inv_by_status = {s.value: 0 for s in InvoiceStatus}
    inv_cur: Dict[str, Dict[str, Any]] = {}
    for status, currency, count, total, paid, due in inv_rows:
        key = _key(status)
        inv_by_status[key] = inv_by_status.get(key, 0) + int(count)
        cur = _cur(currency, base)
        b = inv_cur.setdefault(
            cur, {"count": 0, "total": Decimal("0"), "amount_paid": Decimal("0"), "amount_due": Decimal("0"), "by_status": {}}
        )
        b["count"] += int(count)
        b["by_status"][key] = {"count": int(count), "total": _money(total), "amount_due": _money(due)}
        if key != InvoiceStatus.VOID.value:  # voided invoices are not billed revenue
            b["total"] += D(total)
            b["amount_paid"] += D(paid)
            b["amount_due"] += D(due) if key != InvoiceStatus.DRAFT.value else Decimal("0")

    # Receivables right now (point in time), open + overdue per currency (1 query).
    overdue_cond = or_(
        Invoice.status == InvoiceStatus.OVERDUE,
        and_(Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]), Invoice.due_date < today),
    )
    recv_rows = db.execute(
        select(
            Invoice.currency,
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.amount_due), 0),
            func.coalesce(func.sum(case((overdue_cond, 1), else_=0)), 0),
            func.coalesce(func.sum(case((overdue_cond, Invoice.amount_due), else_=0)), 0),
        )
        .where(Invoice.organization_id == org_id, Invoice.status.in_(list(OPEN_INVOICE_STATUSES)))
        .group_by(Invoice.currency)
    ).all()
    receivables = {
        _cur(cur, base): {
            "currency": _cur(cur, base),
            "open_count": int(count),
            "amount_due": _money(due),
            "overdue_count": int(od_count or 0),
            "overdue_amount": _money(od_amount),
        }
        for cur, count, due, od_count, od_amount in recv_rows
    }

    # Payments collected in range (settled, net of refunds) per currency (1 query).
    pay_stmt = select(
        Payment.currency,
        func.count(Payment.id),
        func.coalesce(func.sum(Payment.amount), 0),
        func.coalesce(func.sum(Payment.amount_refunded), 0),
    ).where(Payment.organization_id == org_id, Payment.status.in_(SETTLED_PAYMENT_STATUSES))
    if lo is not None:
        pay_stmt = pay_stmt.where(Payment.paid_at >= lo)
    if hi is not None:
        pay_stmt = pay_stmt.where(Payment.paid_at < hi)
    payments = {
        _cur(cur, base): {
            "currency": _cur(cur, base),
            "count": int(count),
            "gross": _money(gross),
            "refunded": _money(refunded),
            "net": _money(D(gross) - D(refunded)),
        }
        for cur, count, gross, refunded in db.execute(pay_stmt.group_by(Payment.currency)).all()
    }

    # Subscriptions by status (point in time, 1 query) + MRR (existing single definition).
    sub_by_status = {s.value: 0 for s in SubscriptionStatus}
    for status, count in db.execute(
        select(Subscription.status, func.count(Subscription.id))
        .where(Subscription.organization_id == org_id)
        .group_by(Subscription.status)
    ).all():
        sub_by_status[_key(status)] = int(count)
    from backend.app.services.dashboard_service import compute_mrr

    mrr = compute_mrr(db, org_id, base_currency=base)

    # Customers (1 query).
    cust_row = db.execute(
        select(
            func.count(Customer.id),
            func.coalesce(func.sum(case((Customer.status == CustomerStatus.ACTIVE, 1), else_=0)), 0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                Customer.created_at >= lo if lo is not None else true(),
                                Customer.created_at < hi if hi is not None else true(),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(Customer.organization_id == org_id)
    ).one()

    from backend.app.services import credit_service

    quotes = quotes_summary(db, organization, date_from=date_from, date_to=date_to)
    credit_notes = credit_service.credit_notes_summary(db, org_id, date_from=date_from, date_to=date_to)

    return {
        "base_currency": base,
        "date_from": date_from,
        "date_to": date_to,
        "invoices": {
            "total_count": sum(inv_by_status.values()),
            "by_status": inv_by_status,
            "by_currency": [
                {
                    "currency": cur,
                    "count": inv_cur[cur]["count"],
                    "total": _money(inv_cur[cur]["total"]),
                    "amount_paid": _money(inv_cur[cur]["amount_paid"]),
                    "amount_due": _money(inv_cur[cur]["amount_due"]),
                    "by_status": inv_cur[cur]["by_status"],
                }
                for cur in _order_currencies(inv_cur, base)
            ],
        },
        "receivables": [receivables[c] for c in _order_currencies(receivables, base)],
        "payments_collected": [payments[c] for c in _order_currencies(payments, base)],
        "subscriptions": {"total_count": sum(sub_by_status.values()), "by_status": sub_by_status},
        "mrr": {
            "currency": mrr["currency"],
            "mrr": _money(mrr["mrr"]),
            "arr": _money(D(mrr["mrr"]) * 12),
            "by_currency": {cur: _money(v) for cur, v in mrr["by_currency"].items()},
            "subscription_count": mrr["subscription_count"],
        },
        "quotes": {
            "total_count": quotes["total_count"],
            "by_status": quotes["by_status"],
            "value_by_currency": quotes["value_by_currency"],
        },
        "credit_notes": {
            "total_count": credit_notes["total_count"],
            "count_by_status": credit_notes["count_by_status"],
            "currencies": credit_notes["currencies"],
        },
        "customers": {
            "total": int(cust_row[0] or 0),
            "active": int(cust_row[1] or 0),
            "new_in_period": int(cust_row[2] or 0),
        },
    }

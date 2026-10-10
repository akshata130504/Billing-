"""Per-currency money aggregation shared by reports, collections, dashboards and the portal.

This app has no exchange-rate feature, so amounts in different currencies are NEVER
added together. Every aggregate is grouped by currency; where an API keeps a single
scalar total for backward compatibility it is restricted to one labelled currency (the
organization's base currency unless stated otherwise) and a per-currency breakdown is
returned beside it.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.schemas.common_refs import money_str
from backend.app.services.money import SUPPORTED_CURRENCIES, D, q2


def norm(currency: Optional[str], default: str = "INR") -> str:
    return (currency or default).upper()


def order_currencies(currencies: Iterable[str], base: Optional[str]) -> List[str]:
    """Distinct currencies, the base currency first, the rest by code."""
    base = (base or "").upper()
    return sorted({c.upper() for c in currencies}, key=lambda c: (c != base, c))


def org_base_currency(db: Session, organization_id: str) -> str:
    from backend.app.models import Organization

    org = db.get(Organization, organization_id)
    return norm(org.default_currency if org else None)


def sums_by_currency(db: Session, currency_column, amount_column, *where: Any) -> Dict[str, Decimal]:
    """{CUR: Σ amount} for the rows matching `where` (one GROUP BY query)."""
    rows = db.execute(
        select(currency_column, func.coalesce(func.sum(amount_column), 0)).where(*where).group_by(currency_column)
    ).all()
    out: Dict[str, Decimal] = {}
    for cur, total in rows:
        key = norm(cur)
        out[key] = out.get(key, Decimal("0")) + D(total)
    return out


def format_per_currency(amounts: Mapping[str, Any], base: Optional[str]) -> str:
    """"₹4,509.20 · AED 433.36" - one figure per currency, base first (text answers)."""
    from backend.app.services.pricing_engine import currency_symbol

    if not amounts:
        return f"{currency_symbol(base)}0.00"
    return " · ".join(f"{currency_symbol(cur)}{q2(amounts[cur]):,.2f}" for cur in order_currencies(amounts, base))


def collection_rate(collected: Any, invoiced: Any) -> Optional[str]:
    """THE collection-rate formula, used by Reports and Collections alike (one currency at a time):

        collection rate % = net cash collected / total invoiced x 100

    * net cash collected = settled payments (succeeded / partially refunded) whose paid_at
      falls in the period, minus the amount refunded on them. Credit notes are NOT cash and
      are never counted as collected.
    * total invoiced = Σ total of invoices issued in the period (issue_date), excluding drafts
      (never issued) and voided invoices (cancelled).

    Both figures must be in the same currency. Returns None when nothing was invoiced.
    """
    invoiced = D(invoiced)
    if invoiced <= 0:
        return None
    return money_str(q2(D(collected) / invoiced * 100))


__all__ = [
    "SUPPORTED_CURRENCIES",
    "norm",
    "order_currencies",
    "org_base_currency",
    "sums_by_currency",
    "format_per_currency",
    "collection_rate",
]

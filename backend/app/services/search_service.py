"""Global search across the tenant's customers, invoices, quotes, products, subscriptions and payments."""
from typing import Any, Dict, List

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import Customer, Invoice, Payment, Plan, Product, Quote, Subscription
from backend.app.schemas.common_refs import enum_value, money_str

MAX_LIMIT = 50


def _result(id_: str, category: str, title: str, subtitle: str | None, path: str, badge: str | None) -> Dict[str, Any]:
    return {"id": id_, "category": category, "title": title, "subtitle": subtitle, "path": path, "badge": badge}


def search(db: Session, organization_id: str, q: str, limit: int = 20) -> List[Dict[str, Any]]:
    term = (q or "").strip()
    if not term:
        return []
    limit = max(1, min(int(limit or 20), MAX_LIMIT))
    like = f"%{term}%"
    results: List[Dict[str, Any]] = []

    customers = db.scalars(
        select(Customer)
        .where(
            Customer.organization_id == organization_id,
            or_(
                Customer.display_name.ilike(like),
                Customer.company_name.ilike(like),
                Customer.email.ilike(like),
                Customer.customer_number.ilike(like),
            ),
        )
        .order_by(Customer.display_name.asc())
        .limit(limit)
    ).all()
    for c in customers:
        results.append(
            _result(
                c.id,
                "customers",
                c.display_name,
                " - ".join(p for p in (c.customer_number, c.company_name or c.email) if p),
                f"/customers/{c.id}",
                enum_value(c.status),
            )
        )

    invoices = db.scalars(
        select(Invoice)
        .where(Invoice.organization_id == organization_id, Invoice.invoice_number.ilike(like))
        .options(selectinload(Invoice.customer))
        .order_by(Invoice.issue_date.desc())
        .limit(limit)
    ).all()
    for inv in invoices:
        customer_name = inv.customer.display_name if inv.customer else ""
        results.append(
            _result(
                inv.id,
                "invoices",
                inv.invoice_number,
                f"{customer_name} - {inv.currency} {money_str(inv.total)}".strip(" -"),
                f"/invoices/{inv.id}",
                enum_value(inv.status),
            )
        )

    quotes = db.scalars(
        select(Quote)
        .where(Quote.organization_id == organization_id, Quote.quote_number.ilike(like))
        .options(selectinload(Quote.customer))
        .order_by(Quote.issue_date.desc())
        .limit(limit)
    ).all()
    for qt in quotes:
        customer_name = qt.customer.display_name if qt.customer else ""
        results.append(
            _result(
                qt.id,
                "quotes",
                qt.quote_number,
                f"{customer_name} - {qt.currency} {money_str(qt.total)}".strip(" -"),
                f"/quotes/{qt.id}",
                enum_value(qt.status),
            )
        )

    products = db.scalars(
        select(Product)
        .where(Product.organization_id == organization_id, or_(Product.name.ilike(like), Product.sku.ilike(like)))
        .order_by(Product.name.asc())
        .limit(limit)
    ).all()
    for p in products:
        results.append(
            _result(
                p.id,
                "products",
                p.name,
                f"{p.sku} - {enum_value(p.type)}",
                f"/catalog?product={p.id}",
                "active" if p.is_active else "inactive",
            )
        )

    subscriptions = db.scalars(
        select(Subscription)
        .where(Subscription.organization_id == organization_id, Subscription.subscription_number.ilike(like))
        .options(selectinload(Subscription.customer), selectinload(Subscription.plan).selectinload(Plan.product))
        .order_by(Subscription.created_at.desc())
        .limit(limit)
    ).all()
    for s in subscriptions:
        customer_name = s.customer.display_name if s.customer else ""
        plan_name = s.plan.name if s.plan else ""
        results.append(
            _result(
                s.id,
                "subscriptions",
                s.subscription_number,
                " - ".join(p for p in (customer_name, plan_name) if p),
                f"/subscriptions/{s.id}",
                enum_value(s.status),
            )
        )

    payments = db.scalars(
        select(Payment)
        .where(
            Payment.organization_id == organization_id,
            or_(
                Payment.payment_number.ilike(like),
                Payment.reference.ilike(like),
                Payment.gateway_payment_id.ilike(like),
            ),
        )
        .options(selectinload(Payment.customer))
        .order_by(Payment.created_at.desc())
        .limit(limit)
    ).all()
    for pay in payments:
        customer_name = pay.customer.display_name if pay.customer else ""
        results.append(
            _result(
                pay.id,
                "payments",
                pay.payment_number,
                " - ".join(p for p in (customer_name, enum_value(pay.method), pay.reference) if p),
                f"/payments/{pay.id}",
                f"{pay.currency} {money_str(pay.amount)}",
            )
        )

    return results[:limit]

"""Global search across the tenant's customers, invoices, quotes, products, subscriptions, payments,
projects and expenses."""
from typing import AbstractSet, Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import Customer, Invoice, Payment, Plan, Product, Quote, Subscription
from backend.app.models.expenses import Expense
from backend.app.models.projects import Project
from backend.app.schemas.common_refs import enum_value, money_str

MAX_LIMIT = 50
LIKE_ESCAPE = "\\"


def _like_pattern(term: str) -> str:
    """Contains-pattern with LIKE wildcards (%, _) and the escape char treated literally."""
    escaped = term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", LIKE_ESCAPE + "%").replace("_", LIKE_ESCAPE + "_")
    return f"%{escaped}%"


def _result(id_: str, category: str, title: str, subtitle: str | None, path: str, badge: str | None) -> Dict[str, Any]:
    return {"id": id_, "category": category, "title": title, "subtitle": subtitle, "path": path, "badge": badge}


# Result categories owned by an optional product module (core/modules.json). The others belong to
# base modules every organization has.
CATEGORY_MODULES = {"quotes": "quotes", "subscriptions": "subscriptions", "projects": "projects", "expenses": "expenses"}


def search(db: Session, organization_id: str, q: str, limit: int = 20,
           modules: Optional[AbstractSet[str]] = None) -> List[Dict[str, Any]]:
    """`modules`: the organization's entitled module keys (org_access.entitled_modules); results of
    an optional module outside it are left out. None means no filtering."""
    term = (q or "").strip()
    if not term:
        return []
    limit = max(1, min(int(limit or 20), MAX_LIMIT))
    like = _like_pattern(term)
    results: List[Dict[str, Any]] = []

    customers = db.scalars(
        select(Customer)
        .where(
            Customer.organization_id == organization_id,
            or_(
                Customer.display_name.ilike(like, escape=LIKE_ESCAPE),
                Customer.company_name.ilike(like, escape=LIKE_ESCAPE),
                Customer.email.ilike(like, escape=LIKE_ESCAPE),
                Customer.customer_number.ilike(like, escape=LIKE_ESCAPE),
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
        .where(Invoice.organization_id == organization_id, Invoice.invoice_number.ilike(like, escape=LIKE_ESCAPE))
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
        .where(Quote.organization_id == organization_id, Quote.quote_number.ilike(like, escape=LIKE_ESCAPE))
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
        .where(Product.organization_id == organization_id, or_(Product.name.ilike(like, escape=LIKE_ESCAPE), Product.sku.ilike(like, escape=LIKE_ESCAPE)))
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
        .where(Subscription.organization_id == organization_id, Subscription.subscription_number.ilike(like, escape=LIKE_ESCAPE))
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
                Payment.payment_number.ilike(like, escape=LIKE_ESCAPE),
                Payment.reference.ilike(like, escape=LIKE_ESCAPE),
                Payment.gateway_payment_id.ilike(like, escape=LIKE_ESCAPE),
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

    projects = db.scalars(
        select(Project)
        .where(
            Project.organization_id == organization_id,
            or_(Project.name.ilike(like, escape=LIKE_ESCAPE), Project.customer_name.ilike(like, escape=LIKE_ESCAPE)),
        )
        .order_by(Project.name.asc())
        .limit(limit)
    ).all()
    for pr in projects:
        results.append(
            _result(
                pr.id,
                "projects",
                pr.name,
                pr.customer_name,
                f"/projects/{pr.id}",
                enum_value(pr.status),
            )
        )

    expenses = db.scalars(
        select(Expense)
        .where(
            Expense.organization_id == organization_id,
            or_(
                Expense.name.ilike(like, escape=LIKE_ESCAPE),
                Expense.category.ilike(like, escape=LIKE_ESCAPE),
                Expense.customer_name.ilike(like, escape=LIKE_ESCAPE),
            ),
        )
        .order_by(Expense.date.desc())
        .limit(limit)
    ).all()
    for ex in expenses:
        results.append(
            _result(
                ex.id,
                "expenses",
                ex.name,
                " - ".join(p for p in (ex.category, ex.customer_name) if p),
                f"/expenses/{ex.id}",
                f"{ex.currency} {money_str(ex.amount)}",
            )
        )

    if modules is not None:
        results = [r for r in results if CATEGORY_MODULES.get(r["category"]) in (None, *modules)]
    return results[:limit]

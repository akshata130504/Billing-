"""Server-side dashboard / KPI summary endpoints: tenant isolation, empty orgs,
currency mixing, date ranges, RBAC."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.app.models import InvoiceStatus, MemberRole
from backend.app.models.catalog_cpq import CPQDeal, CPQDealStatus, Offering, PriceBook, PriceBookStatus
from backend.app.models.payments import Payment, PaymentMethod, PaymentStatus
from backend.app.models.quotes import Quote, QuoteStatus
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.tests.conftest import Tenant

FIN = "/api/v1/dashboard/financial-summary"
QUOTES = "/api/v1/dashboard/quotes-summary"
CATALOG = "/api/v1/dashboard/catalog-summary"
DEALS = "/api/v1/dashboard/deals-summary"


def _quote(tenant, customer, status, total, *, currency="INR", issue=None, title="Quote"):
    q = Quote(
        organization_id=tenant.organization.id,
        quote_number=f"QT-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        status=status,
        issue_date=issue or date.today(),
        expiry_date=date.today() + timedelta(days=30),
        currency=currency,
        total=Decimal(total),
        subtotal=Decimal(total),
        title=title,
    )
    tenant.db.add(q)
    tenant.db.commit()
    return q


def _deal(tenant, customer, status, total, currency="INR"):
    d = CPQDeal(
        organization_id=tenant.organization.id,
        deal_number=f"DEAL-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        status=status,
        title="Deal",
        currency=currency,
        total=Decimal(total),
    )
    tenant.db.add(d)
    tenant.db.commit()
    return d


def _offering(tenant, otype, active=True, name=None):
    o = Offering(
        organization_id=tenant.organization.id,
        name=name or f"Off {uuid.uuid4().hex[:5]}",
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        type=otype,
        base_price=Decimal("10"),
        is_active=active,
    )
    tenant.db.add(o)
    tenant.db.commit()
    return o


def _payment(tenant, customer, amount, *, currency="INR", paid_at=None, status=PaymentStatus.SUCCEEDED, refunded="0"):
    p = Payment(
        organization_id=tenant.organization.id,
        payment_number=f"PAY-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        amount=Decimal(amount),
        amount_refunded=Decimal(refunded),
        currency=currency,
        method=PaymentMethod.BANK_TRANSFER,
        status=status,
        paid_at=paid_at or datetime.now(timezone.utc),
    )
    tenant.db.add(p)
    tenant.db.commit()
    return p


def _invoice(tenant, customer, amount, *, currency="INR", status=InvoiceStatus.SENT, issue=None, due=None, paid="0"):
    inv = tenant.invoice(customer, amount=amount, status=status)
    inv.currency = currency
    if issue:
        inv.issue_date = issue
    if due:
        inv.due_date = due
    inv.amount_paid = Decimal(paid)
    inv.amount_due = Decimal(amount) - Decimal(paid)
    tenant.db.commit()
    return inv


# ---------------------------------------------------------------- empty org
def test_empty_org_gets_complete_zero_summaries(client, tenant):
    h = tenant.headers()
    fin = client.get(FIN, headers=h)
    assert fin.status_code == 200, fin.text
    f = fin.json()
    assert f["invoices"]["total_count"] == 0 and all(v == 0 for v in f["invoices"]["by_status"].values())
    assert f["invoices"]["by_currency"] == [] and f["receivables"] == [] and f["payments_collected"] == []
    assert f["mrr"]["mrr"] == "0.00" and f["customers"] == {"total": 0, "active": 0, "new_in_period": 0}
    assert f["credit_notes"]["total_count"] == 0 and f["quotes"]["total_count"] == 0
    q = client.get(QUOTES, headers=h).json()
    assert q["total_count"] == 0 and q["value_by_currency"] == [] and set(q["groups"]) == {"draft", "pending_approval", "sent", "accepted"}
    c = client.get(CATALOG, headers=h).json()
    assert c["offerings"]["total"] == 0 and c["price_books"]["total"] == 0
    assert set(c["offerings"]["by_type"]) >= {"product", "service", "plan", "bundle"}
    d = client.get(DEALS, headers=h).json()
    assert d["total_count"] == 0 and d["groups"] == {"pending": 0, "approved": 0, "converted": 0}


# ---------------------------------------------------------------- quotes
def test_quotes_summary_counts_values_per_currency_and_filters(client, tenant, db):
    a, b = tenant.customer(display_name="Acme Widgets"), tenant.customer(display_name="Zeta Corp")
    _quote(tenant, a, QuoteStatus.DRAFT, "100.00")
    _quote(tenant, a, QuoteStatus.SENT, "200.00")
    _quote(tenant, b, QuoteStatus.VIEWED, "300.00")
    _quote(tenant, b, QuoteStatus.ACCEPTED, "400.00", currency="USD")
    _quote(tenant, b, QuoteStatus.CONVERTED, "50.00", currency="USD")
    _quote(tenant, a, QuoteStatus.DECLINED, "999.00", issue=date.today() - timedelta(days=90))
    h = tenant.headers()

    s = client.get(QUOTES, headers=h).json()
    assert s["total_count"] == 6
    assert s["groups"] == {"draft": 1, "pending_approval": 0, "sent": 2, "accepted": 2}
    by = {v["currency"]: v for v in s["value_by_currency"]}
    assert by["INR"]["total"] == "1599.00" and by["INR"]["count"] == 4
    assert by["INR"]["open_total"] == "600.00"  # declined excluded from open pipeline
    assert by["USD"]["total"] == "450.00" and by["USD"]["open_total"] == "400.00"
    assert [v["currency"] for v in s["value_by_currency"]][0] == "INR"  # base currency first

    recent = client.get(QUOTES, params={"date_from": (date.today() - timedelta(days=7)).isoformat()}, headers=h).json()
    assert recent["total_count"] == 5 and recent["by_status"]["declined"] == 0
    searched = client.get(QUOTES, params={"search": "zeta"}, headers=h).json()
    assert searched["total_count"] == 3
    by_customer = client.get(QUOTES, params={"customer_id": a.id}, headers=h).json()
    assert by_customer["total_count"] == 3
    assert client.get(QUOTES, params={"date_from": "2026-02-02", "date_to": "2026-01-01"}, headers=h).status_code == 422


# ---------------------------------------------------------------- catalog + deals
def test_catalog_and_deals_summaries(client, tenant, db):
    _offering(tenant, "product", name="Widget Pro")
    _offering(tenant, "product", active=False)
    _offering(tenant, "service")
    _offering(tenant, "plan")
    _offering(tenant, "bundle")
    db.add(PriceBook(organization_id=tenant.organization.id, name="Enterprise", status=PriceBookStatus.ACTIVE))
    db.commit()
    h = tenant.headers()
    c = client.get(CATALOG, headers=h).json()
    assert c["offerings"] == {
        "total": 5, "active": 4, "inactive": 1,
        "by_type": {**c["offerings"]["by_type"], "product": 2, "service": 1, "plan": 1, "bundle": 1},
        "active_by_type": c["offerings"]["active_by_type"],
        "inactive_by_type": c["offerings"]["inactive_by_type"],
    }
    # Per-type split by status always adds back up to the combined per-type counts.
    for t, n in c["offerings"]["by_type"].items():
        assert c["offerings"]["active_by_type"][t] + c["offerings"]["inactive_by_type"][t] == n
    assert sum(c["offerings"]["active_by_type"].values()) == 4
    assert sum(c["offerings"]["inactive_by_type"].values()) == 1
    assert c["price_books"]["total"] == 1 and c["price_books"]["by_status"]["active"] == 1
    assert client.get(CATALOG, params={"search": "widget"}, headers=h).json()["offerings"]["total"] == 1

    cust = tenant.customer()
    _deal(tenant, cust, CPQDealStatus.PENDING_APPROVAL, "100")
    _deal(tenant, cust, CPQDealStatus.APPROVED, "200")
    _deal(tenant, cust, CPQDealStatus.CONFIGURED, "300", currency="EUR")
    _deal(tenant, cust, CPQDealStatus.CONVERTED, "400")
    d = client.get(DEALS, headers=h).json()
    assert d["total_count"] == 4
    assert d["groups"] == {"pending": 1, "approved": 2, "converted": 1}
    by = {v["currency"]: v for v in d["value_by_currency"]}
    assert by["INR"]["total"] == "700.00" and by["EUR"]["total"] == "300.00"


# ---------------------------------------------------------------- financial summary
def test_financial_summary_currency_mixing_and_ranges(client, tenant, db):
    tenant.organization.default_currency = "INR"
    db.commit()
    c1 = tenant.customer()
    c2 = tenant.customer(currency="USD")
    today = date.today()
    _invoice(tenant, c1, "1000.00", status=InvoiceStatus.SENT, due=today + timedelta(days=5))
    _invoice(tenant, c1, "500.00", status=InvoiceStatus.PARTIALLY_PAID, paid="200.00", due=today - timedelta(days=3))
    _invoice(tenant, c1, "300.00", status=InvoiceStatus.PAID, paid="300.00")
    _invoice(tenant, c1, "700.00", status=InvoiceStatus.VOID)
    _invoice(tenant, c1, "50.00", status=InvoiceStatus.DRAFT)
    _invoice(tenant, c2, "80.00", currency="USD", status=InvoiceStatus.OVERDUE, due=today - timedelta(days=10))
    _invoice(tenant, c1, "9999.00", status=InvoiceStatus.SENT, issue=today - timedelta(days=100))  # old
    _payment(tenant, c1, "300.00")
    _payment(tenant, c1, "200.00", refunded="50.00")
    _payment(tenant, c2, "20.00", currency="USD")
    _payment(tenant, c1, "111.00", status=PaymentStatus.FAILED)
    _payment(tenant, c1, "777.00", paid_at=datetime.now(timezone.utc) - timedelta(days=100))
    _quote(tenant, c1, QuoteStatus.SENT, "10.00")
    _, plan = tenant.product_with_plan(unit_amount="1200.00")
    db.add(Subscription(
        organization_id=tenant.organization.id, subscription_number=f"SUB-{uuid.uuid4().hex[:6]}",
        customer_id=c1.id, plan_id=plan.id, status=SubscriptionStatus.ACTIVE, quantity=1,
        start_date=today, current_period_start=today, current_period_end=today + timedelta(days=30), currency="INR",
    ))
    db.commit()
    h = tenant.headers()
    since = (today - timedelta(days=30)).isoformat()

    f = client.get(FIN, params={"date_from": since, "date_to": today.isoformat()}, headers=h).json()
    inv = f["invoices"]
    assert inv["total_count"] == 6  # the 100-day-old invoice is outside the range
    assert inv["by_status"]["void"] == 1 and inv["by_status"]["draft"] == 1
    by = {c["currency"]: c for c in inv["by_currency"]}
    assert set(by) == {"INR", "USD"}
    assert by["INR"]["total"] == "1850.00"  # 1000+500+300+50 (void excluded)
    assert by["INR"]["amount_due"] == "1300.00"  # 1000 + 300 (draft/void excluded)
    assert by["USD"]["total"] == "80.00"
    assert by["INR"]["by_status"]["void"]["total"] == "700.00"

    recv = {r["currency"]: r for r in f["receivables"]}  # point in time: includes the old invoice
    assert recv["INR"]["amount_due"] == "11299.00" and recv["INR"]["open_count"] == 3
    assert recv["INR"]["overdue_count"] == 1 and recv["INR"]["overdue_amount"] == "300.00"
    assert recv["USD"]["overdue_amount"] == "80.00"

    col = {p["currency"]: p for p in f["payments_collected"]}
    assert col["INR"] == {"currency": "INR", "count": 2, "gross": "500.00", "refunded": "50.00", "net": "450.00"}
    assert col["USD"]["net"] == "20.00"

    assert f["subscriptions"]["by_status"]["active"] == 1
    assert f["mrr"]["currency"] == "INR" and f["mrr"]["mrr"] == "1200.00" and f["mrr"]["arr"] == "14400.00"
    assert f["quotes"]["total_count"] == 1
    assert f["customers"]["total"] == 2 and f["customers"]["new_in_period"] == 2

    all_time = client.get(FIN, headers=h).json()
    assert all_time["invoices"]["total_count"] == 7
    assert {p["currency"]: p for p in all_time["payments_collected"]}["INR"]["gross"] == "1277.00"
    ranged = client.get(FIN, params={"range": "7_days"}, headers=h).json()
    assert ranged["date_from"] == (today - timedelta(days=6)).isoformat()


def test_summaries_are_tenant_isolated_and_rbac(client, tenant, db):
    other = Tenant(db, uuid.uuid4().hex[:8])
    oc = other.customer()
    _invoice(other, oc, "5000.00")
    _payment(other, oc, "5000.00")
    _quote(other, oc, QuoteStatus.SENT, "123.00")
    _deal(other, oc, CPQDealStatus.APPROVED, "1")
    _offering(other, "product")

    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    for url in (FIN, QUOTES, CATALOG, DEALS):
        res = client.get(url, headers=viewer)
        assert res.status_code == 200, (url, res.text)
    f = client.get(FIN, headers=viewer).json()
    assert f["invoices"]["total_count"] == 0 and f["payments_collected"] == [] and f["customers"]["total"] == 0
    assert client.get(QUOTES, headers=viewer).json()["total_count"] == 0
    assert client.get(QUOTES, params={"customer_id": oc.id}, headers=viewer).json()["total_count"] == 0
    assert client.get(CATALOG, headers=viewer).json()["offerings"]["total"] == 0
    assert client.get(DEALS, headers=viewer).json()["total_count"] == 0
    # the other org sees its own data
    assert client.get(QUOTES, headers=other.headers()).json()["total_count"] == 1
    for url in (FIN, QUOTES, CATALOG, DEALS):
        assert client.get(url).status_code == 401

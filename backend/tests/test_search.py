"""Global search tests."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from backend.app.models import Invoice, InvoiceStatus, Payment, PaymentMethod, Quote, Subscription, SubscriptionStatus

BASE = "/api/v1/search"


def test_search_across_categories(client, tenant, auth_headers, db):
    tag = uuid.uuid4().hex[:6].upper()
    org_id = tenant.organization.id
    customer = tenant.customer(display_name=f"Globex {tag}", company_name="Globex Corporation")
    product, plan = tenant.product_with_plan()
    product.name = f"Widget {tag}"
    today = date.today()
    db.add(
        Invoice(
            organization_id=org_id,
            invoice_number=f"INV-{tag}",
            customer_id=customer.id,
            status=InvoiceStatus.SENT,
            issue_date=today,
            due_date=today,
            total=Decimal("1500.00"),
            amount_due=Decimal("1500.00"),
            public_token=uuid.uuid4().hex,
        )
    )
    db.add(Quote(organization_id=org_id, quote_number=f"QT-{tag}", customer_id=customer.id, issue_date=today, total=Decimal("99")))
    db.add(
        Subscription(
            organization_id=org_id,
            subscription_number=f"SUB-{tag}",
            customer_id=customer.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            start_date=today,
            current_period_start=today,
            current_period_end=today + timedelta(days=30),
        )
    )
    db.add(
        Payment(
            organization_id=org_id,
            payment_number=f"PAY-{tag}",
            customer_id=customer.id,
            amount=Decimal("250.00"),
            method=PaymentMethod.UPI,
            reference=f"UTR{tag}",
        )
    )
    db.commit()

    resp = client.get(BASE, headers=auth_headers, params={"q": tag})
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    by_cat = {r["category"]: r for r in results}
    assert set(by_cat) == {"customers", "invoices", "quotes", "products", "subscriptions", "payments"}
    assert by_cat["customers"]["path"] == f"/customers/{customer.id}"
    assert by_cat["customers"]["badge"] == "active"
    assert by_cat["invoices"]["title"] == f"INV-{tag}"
    assert by_cat["invoices"]["badge"] == "sent"
    assert by_cat["invoices"]["path"].startswith("/invoices/")
    assert by_cat["quotes"]["title"] == f"QT-{tag}"
    assert by_cat["products"]["path"] == f"/catalog?product={product.id}"
    assert by_cat["subscriptions"]["badge"] == "active"
    assert by_cat["payments"]["badge"] == "INR 250.00"
    assert by_cat["payments"]["path"] == f"/payments/{by_cat['payments']['id']}"

    # case-insensitive, matches reference too
    resp = client.get(BASE, headers=auth_headers, params={"q": f"utr{tag.lower()}"})
    assert [r["category"] for r in resp.json()["results"]] == ["payments"]

    # limit caps the total
    resp = client.get(BASE, headers=auth_headers, params={"q": tag, "limit": 2})
    assert len(resp.json()["results"]) == 2


def test_search_requires_query_and_is_tenant_scoped(client, tenant, db):
    from backend.tests.conftest import Tenant

    assert client.get(BASE, headers=tenant.headers()).status_code == 422
    other = Tenant(db, uuid.uuid4().hex[:8])
    foreign = other.customer(display_name="Secret Foreign Customer")
    resp = client.get(BASE, headers=tenant.headers(), params={"q": "Secret Foreign"})
    assert resp.status_code == 200
    assert all(r["id"] != foreign.id for r in resp.json()["results"])
    assert client.get(BASE, params={"q": "x"}).status_code == 401


def test_search_treats_like_wildcards_literally_and_covers_projects_expenses(client, tenant, auth_headers, db):
    from backend.app.models.expenses import Expense
    from backend.app.models.projects import Project

    tag = uuid.uuid4().hex[:6].upper()
    org_id = tenant.organization.id
    tenant.customer(display_name=f"Plain {tag}")
    db.add(Project(organization_id=org_id, name=f"Apollo {tag}", customer_name="Globex"))
    db.add(Expense(organization_id=org_id, name=f"Taxi {tag}", date=date.today(), category="Travel", amount=Decimal("12.50")))
    db.commit()

    # "%" must not act as a wildcard matching everything.
    res = client.get(BASE, params={"q": "%%"}, headers=auth_headers)
    assert res.status_code == 200
    assert all("%%" in (r["title"] + (r["subtitle"] or "")) for r in res.json()["results"])

    # "_" must not match an arbitrary single character.
    res = client.get(BASE, params={"q": f"Plain_{tag}"}, headers=auth_headers)
    assert res.json()["results"] == []

    cats = {r["category"]: r for r in client.get(BASE, params={"q": tag}, headers=auth_headers).json()["results"]}
    assert cats["projects"]["path"].startswith("/projects/")
    assert cats["expenses"]["path"].startswith("/expenses/")

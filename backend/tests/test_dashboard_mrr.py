"""MRR (single shared definition) and logo churn on the dashboard."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.app.models import Subscription, SubscriptionStatus
from backend.app.services.dashboard_service import compute_mrr


def _sub(tenant, customer, plan, *, status=SubscriptionStatus.ACTIVE, quantity=1, unit_price="0", discount="0",
         currency="INR", created_at=None, cancelled_at=None):
    today = date.today()
    sub = Subscription(
        organization_id=tenant.organization.id,
        subscription_number=f"SUB-{customer.id[:6]}-{plan.id[:4]}-{quantity}-{status.value[:3]}",
        customer_id=customer.id,
        plan_id=plan.id,
        quantity=quantity,
        status=status,
        currency=currency,
        unit_price=Decimal(unit_price),
        discount_amount=Decimal(discount),
        start_date=today,
        current_period_start=today,
        current_period_end=today + timedelta(days=30),
        cancelled_at=cancelled_at,
    )
    if created_at is not None:
        sub.created_at = created_at
    tenant.db.add(sub)
    tenant.db.commit()
    return sub


def test_mrr_uses_subscription_price_quantity_discount_and_interval(tenant, db):
    _, monthly = tenant.product_with_plan(unit_amount="1000.00", interval="monthly")
    _, yearly = tenant.product_with_plan(unit_amount="12000.00", interval="yearly")
    c1, c2, c3, c4 = (tenant.customer() for _ in range(4))
    # negotiated price 800 x 2 seats - 100 discount = 1500 / month
    _sub(tenant, c1, monthly, quantity=2, unit_price="800", discount="100")
    # no override -> plan list price 12000 / 12 = 1000 / month; PAST_DUE still counts
    _sub(tenant, c2, yearly, status=SubscriptionStatus.PAST_DUE)
    # trials and paused subscriptions do not bill
    _sub(tenant, c3, monthly, status=SubscriptionStatus.TRIALING)
    # another currency is reported separately, never summed in
    _sub(tenant, c4, monthly, unit_price="50", currency="USD")

    result = compute_mrr(db, tenant.organization.id, base_currency="INR")
    assert result["mrr"] == Decimal("2500.00")
    assert result["other_currencies"] == {"USD": Decimal("50.00")}
    assert result["subscription_count"] == 3


def test_dashboard_reports_mrr_currency_and_logo_churn(client, tenant, auth_headers, db):
    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    long_ago = datetime.now(timezone.utc) - timedelta(days=90)
    stay = tenant.customer()
    churned = tenant.customer()
    _sub(tenant, stay, plan, created_at=long_ago)
    _sub(
        tenant,
        churned,
        plan,
        status=SubscriptionStatus.CANCELLED,
        created_at=long_ago,
        cancelled_at=datetime.now(timezone.utc) - timedelta(days=2),
    )

    res = client.get("/api/v1/dashboard/summary", params={"range": "30_days"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["revenue"]["mrr"] == "1000.00"
    assert body["revenue"]["mrr_currency"] == "INR"
    assert body["revenue"]["mrr_other_currencies"] == {}
    health = body["customer_health"]
    assert health["customers_at_period_start"] == 2
    assert health["churned_customers"] == 1
    assert health["churn_rate"] == "50.00"

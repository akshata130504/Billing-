"""MRR counts every ACTIVE subscription item, not only the primary plan line.

Multi-line quote -> subscription conversion creates the first recurring line as the PLAN
item and the rest as ADDON items (each with its own price snapshot). The shared MRR
definition (dashboard, subscription summary, reports, AI) must include those add-ons.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from backend.app.models import BillingInterval, PricingModel, Subscription
from backend.app.models.billing_cycles import PriceSnapshot, SubscriptionItem, SubscriptionItemStatus, SubscriptionItemType
from backend.app.services import dashboard_service, subscription_service
from backend.tests.test_quote_to_subscription import _accepted_quote, _convert


def _mrr(db, tenant):
    db.expire_all()
    return dashboard_service.compute_mrr(db, tenant.organization.id, base_currency="INR")


def _line(plan, qty, price):
    return {"plan_id": plan.id, "description": plan.name, "quantity": str(qty), "unit_price": price, "tax_rate_pct": "0"}


def test_single_item_subscription_mrr_unchanged(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    quote = _accepted_quote(client, auth_headers, customer, [_line(plan, 2, "1000.00")])
    res = _convert(client, auth_headers, quote["id"], start_date=str(date.today()))
    assert res.status_code == 201, res.text

    result = _mrr(db, tenant)
    sub = db.get(Subscription, res.json()["id"])
    # Exactly the pre-existing primary-plan formula: price x quantity - discount per month.
    expected = dashboard_service._primary_monthly_amount(sub, sub.plan)
    assert expected == Decimal("2000")
    assert result["mrr"] == Decimal("2000.00")
    assert dashboard_service.subscription_monthly_amount(sub, sub.plan) == expected
    assert result["subscription_count"] == 1


def test_addon_items_are_included_and_cancelled_addons_excluded(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, base = tenant.product_with_plan(unit_amount="1000.00")
    _, support = tenant.product_with_plan(unit_amount="500.00")
    _, annual = tenant.product_with_plan(unit_amount="1200.00", interval="yearly")
    quote = _accepted_quote(
        client, auth_headers, customer, [_line(base, 2, "1000.00"), _line(support, 3, "500.00")]
    )
    res = _convert(client, auth_headers, quote["id"], start_date=str(date.today()))
    assert res.status_code == 201, res.text
    sub_id = res.json()["id"]
    # An add-on on a different interval (conversion requires one interval, so add it directly):
    # it is normalised by its own snapshot interval, not the primary plan's.
    snap = PriceSnapshot(
        organization_id=tenant.organization.id,
        plan_id=annual.id,
        unit_amount=Decimal("1200.00"),
        currency="INR",
        billing_interval=BillingInterval.YEARLY,
        interval_count=1,
        pricing_model=PricingModel.PER_UNIT,
    )
    db.add(snap)
    db.flush()
    db.add(
        SubscriptionItem(
            organization_id=tenant.organization.id,
            subscription_id=sub_id,
            plan_id=annual.id,
            price_snapshot_id=snap.id,
            item_type=SubscriptionItemType.ADDON,
            quantity=Decimal("1"),
            unit_price=Decimal("1200.00"),
            status=SubscriptionItemStatus.ACTIVE,
        )
    )
    db.commit()

    db.expire_all()
    items = list(db.scalars(select(SubscriptionItem).where(SubscriptionItem.subscription_id == sub_id)))
    addons = [i for i in items if i.item_type == SubscriptionItemType.ADDON]
    assert len(addons) == 2

    # 2 x 1000 (primary) + 3 x 500 (monthly add-on) + 1200 / 12 (yearly add-on).
    assert _mrr(db, tenant)["mrr"] == Decimal("3600.00")
    summary = subscription_service.get_subscriptions_summary(db, tenant.organization.id)
    assert Decimal(str(summary["total_mrr"])) == Decimal("3600.00")

    # A cancelled add-on stops counting.
    yearly = next(i for i in addons if i.plan_id == annual.id)
    yearly.status = SubscriptionItemStatus.CANCELLED
    db.commit()
    assert _mrr(db, tenant)["mrr"] == Decimal("3500.00")

    monthly = next(i for i in addons if i.plan_id == support.id)
    monthly.status = SubscriptionItemStatus.CANCELLED
    db.commit()
    assert _mrr(db, tenant)["mrr"] == Decimal("2000.00")


def test_metered_items_are_not_recurring_revenue(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="700.00")
    quote = _accepted_quote(client, auth_headers, customer, [_line(plan, 1, "700.00")])
    res = _convert(client, auth_headers, quote["id"], start_date=str(date.today()))
    assert res.status_code == 201, res.text
    db.add(
        SubscriptionItem(
            organization_id=tenant.organization.id,
            subscription_id=res.json()["id"],
            item_type=SubscriptionItemType.METERED,
            quantity=Decimal("40"),
            unit_price=Decimal("25.00"),
            status=SubscriptionItemStatus.ACTIVE,
        )
    )
    db.commit()
    assert _mrr(db, tenant)["mrr"] == Decimal("700.00")

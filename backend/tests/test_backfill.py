"""Tests for safe subscription backfill service."""
from datetime import date

from backend.app.models.billing_cycles import BillingCycle
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.services.backfill_service import backfill_legacy_subscriptions


def test_backfill_legacy_subscriptions(tenant, db):
    org_id = tenant.organization.id
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1800.00", interval="monthly")

    # Manually insert a "legacy" subscription that lacks items and cycles
    legacy_sub = Subscription(
        organization_id=org_id,
        subscription_number="SUB-LEGACY-001",
        customer_id=customer.id,
        plan_id=plan.id,
        quantity=2,
        status=SubscriptionStatus.ACTIVE,
        start_date=date(2026, 1, 1),
        current_period_start=date(2026, 1, 1),
        current_period_end=date(2026, 2, 1),
        next_billing_date=date(2026, 2, 1),
    )
    db.add(legacy_sub)
    db.commit()
    db.refresh(legacy_sub)

    # Pre-check: verify no items or cycles exist
    assert len(legacy_sub.subscription_items) == 0
    cycle_before = db.query(BillingCycle).filter(BillingCycle.subscription_id == legacy_sub.id).first()
    assert cycle_before is None

    # Run backfill
    res = backfill_legacy_subscriptions(db, organization_id=org_id)
    assert res["subscriptions_processed"] >= 1
    assert res["items_created"] >= 1
    assert res["cycles_created"] >= 1

    # Post-check: verify items and cycles now exist
    db.refresh(legacy_sub)
    assert len(legacy_sub.subscription_items) == 1
    item = legacy_sub.subscription_items[0]
    assert item.plan_id == plan.id
    assert int(item.quantity) == 2
    assert item.price_snapshot_id is not None

    cycle_after = db.query(BillingCycle).filter(BillingCycle.subscription_id == legacy_sub.id).first()
    assert cycle_after is not None
    assert cycle_after.cycle_number == 1
    assert cycle_after.period_start == date(2026, 1, 1)

    # Second run should be idempotent (0 new items or cycles created)
    res2 = backfill_legacy_subscriptions(db, organization_id=org_id)
    assert res2["items_created"] == 0
    assert res2["cycles_created"] == 0

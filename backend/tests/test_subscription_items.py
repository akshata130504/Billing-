"""Subscription price-snapshot, item and billing-cycle behaviour.

Split out of test_subscriptions.py during the merge: that module now holds
the lifecycle suite from main, while these cover the subscription_items /
PriceSnapshot / BillingCycle model introduced on this branch.
"""
from decimal import Decimal

BASE = "/api/v1/subscriptions"


def test_subscription_creates_snapshot_item_and_billing_cycle(client, tenant, auth_headers, db):
    from backend.app.models.billing_cycles import BillingCycle, PriceSnapshot, SubscriptionItem

    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="2500.00", interval="monthly")

    resp = client.post(
        BASE,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 3},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    sub_id = resp.json()["id"]

    # Verify PriceSnapshot was created
    snapshot = db.query(PriceSnapshot).filter(PriceSnapshot.plan_id == plan.id).first()
    assert snapshot is not None
    assert Decimal(str(snapshot.unit_amount)) == Decimal("2500.00")

    # Verify SubscriptionItem was created
    item = db.query(SubscriptionItem).filter(SubscriptionItem.subscription_id == sub_id).first()
    assert item is not None
    assert item.plan_id == plan.id
    assert item.price_snapshot_id == snapshot.id
    assert int(item.quantity) == 3

    # Verify initial BillingCycle was created
    cycle = db.query(BillingCycle).filter(BillingCycle.subscription_id == sub_id).first()
    assert cycle is not None
    assert cycle.cycle_number == 1
    assert cycle.status.value in ("open", "invoiced")


def test_subscription_renewal_preserves_snapshot_price(client, tenant, auth_headers, db):
    from backend.app.models.billing_cycles import BillingCycle
    from backend.app.services.subscription_service import get_subscription, renew_subscription

    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="3000.00", interval="monthly")

    resp = client.post(
        BASE,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1, "generate_first_invoice": False},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    sub_id = resp.json()["id"]

    # Modify plan unit_amount in DB to simulate future price hike (e.g. 3000 -> 5000)
    plan.unit_amount = Decimal("5000.00")
    db.commit()

    sub = get_subscription(db, tenant.organization.id, sub_id)
    # Renew subscription
    outcome = renew_subscription(db, sub)
    assert outcome == "renewed"
    db.commit()

    # The renewal invoice should use snapshot price (3000.00), not the updated plan price (5000.00)
    cycles = db.query(BillingCycle).filter(BillingCycle.subscription_id == sub_id).all()
    assert len(cycles) >= 2

    # Check generated renewal invoice
    from backend.app.models.invoices import Invoice
    inv = db.query(Invoice).filter(Invoice.subscription_id == sub_id).first()
    assert inv is not None
    assert Decimal(str(inv.subtotal)) == Decimal("3000.00")

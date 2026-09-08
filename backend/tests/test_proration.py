"""Tests for Proration Calculator and Subscription Changes (Phase 2)."""
from datetime import date, timedelta
from decimal import Decimal
import pytest

from backend.app.models.credits import CreditNote, CreditNoteStatus
from backend.app.models.invoices import Invoice
from backend.app.models.proration import (
    ProrationEffectiveType,
    SubscriptionChangeStatus,
    SubscriptionChangeType,
)
from backend.app.services.proration_calculator import calculate_proration


def test_proration_calculator_upgrade_and_downgrade():
    # 1. Upgrade halfway through a 30-day period: ₹1,000 -> ₹2,000
    res1 = calculate_proration(
        period_start=date(2026, 4, 1),
        period_end=date(2026, 5, 1),
        change_date=date(2026, 4, 16),
        old_price=Decimal("1000.00"),
        new_price=Decimal("2000.00"),
        old_quantity=Decimal("1"),
        new_quantity=Decimal("1"),
    )
    assert res1.total_days == 30
    assert res1.days_used == 15
    assert res1.days_remaining == 15
    assert res1.unused_credit == Decimal("500.00")
    assert res1.remaining_charge == Decimal("1000.00")
    assert res1.net_adjustment == Decimal("500.00")
    assert res1.is_upgrade is True
    assert res1.is_downgrade is False

    # 2. Downgrade: $300/mo -> $100/mo with 15 days used out of 30
    res2 = calculate_proration(
        period_start=date(2026, 4, 5),
        period_end=date(2026, 5, 5),
        change_date=date(2026, 4, 20),
        old_price=Decimal("300.00"),
        new_price=Decimal("100.00"),
        old_quantity=Decimal("1"),
        new_quantity=Decimal("1"),
        currency="USD",
    )
    assert res2.total_days == 30
    assert res2.days_used == 15
    assert res2.days_remaining == 15
    assert res2.unused_credit == Decimal("150.00")
    assert res2.remaining_charge == Decimal("50.00")
    assert res2.net_adjustment == Decimal("-100.00")  # net credit of $100
    assert res2.is_upgrade is False
    assert res2.is_downgrade is True

    # 3. Quantity change: 5 units -> 10 units at $50/unit
    res3 = calculate_proration(
        period_start=date(2026, 4, 1),
        period_end=date(2026, 5, 1),
        change_date=date(2026, 4, 16),
        old_price=Decimal("50.00"),
        new_price=Decimal("50.00"),
        old_quantity=Decimal("5"),
        new_quantity=Decimal("10"),
    )
    assert res3.unused_credit == Decimal("125.00")
    assert res3.remaining_charge == Decimal("250.00")
    assert res3.net_adjustment == Decimal("125.00")


def test_subscription_change_api_preview_and_apply_immediate_upgrade(client, tenant, auth_headers, db):
    customer = tenant.customer()
    prod_basic, plan_basic = tenant.product_with_plan(unit_amount="1000.00")
    prod_prem, plan_prem = tenant.product_with_plan(unit_amount="2500.00")

    # Create active subscription on basic plan
    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={
            "customer_id": customer.id,
            "plan_id": plan_basic.id,
            "quantity": 1,
            "generate_first_invoice": True,
        },
        headers=auth_headers,
    )
    assert sub_resp.status_code == 201, sub_resp.text
    sub_id = sub_resp.json()["id"]

    # 1. Preview Upgrade
    prev_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes/preview",
        json={"target_plan_id": plan_prem.id},
        headers=auth_headers,
    )
    assert prev_resp.status_code == 200, prev_resp.text
    preview = prev_resp.json()
    assert preview["change_type"] == "upgrade"
    assert preview["old_plan"]["id"] == plan_basic.id
    assert preview["new_plan"]["id"] == plan_prem.id
    assert Decimal(preview["remaining_charge"]) > Decimal(preview["unused_credit"])
    assert Decimal(preview["net_amount"]) > Decimal("0")

    # 2. Apply Immediate Upgrade
    apply_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={
            "target_plan_id": plan_prem.id,
            "effective_type": "immediate",
        },
        headers=auth_headers,
    )
    assert apply_resp.status_code == 201, apply_resp.text
    change_data = apply_resp.json()
    assert change_data["status"] == SubscriptionChangeStatus.APPLIED.value
    assert change_data["change_type"] == SubscriptionChangeType.UPGRADE.value
    assert change_data["invoice_id"] is not None
    assert change_data["credit_note_id"] is not None

    # Verify subscription is now on plan_prem
    sub_get = client.get(f"/api/v1/subscriptions/{sub_id}", headers=auth_headers)
    assert sub_get.status_code == 200
    assert sub_get.json()["plan"]["id"] == plan_prem.id

    # 3. Verify history endpoint
    history_resp = client.get(f"/api/v1/subscriptions/{sub_id}/changes", headers=auth_headers)
    assert history_resp.status_code == 200
    changes = history_resp.json()
    assert len(changes) == 1
    assert changes[0]["id"] == change_data["id"]


def test_subscription_change_scheduled_and_cancelled(client, tenant, auth_headers):
    customer = tenant.customer()
    p1, plan1 = tenant.product_with_plan(unit_amount="500.00")
    p2, plan2 = tenant.product_with_plan(unit_amount="1500.00")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan1.id, "quantity": 1},
        headers=auth_headers,
    )
    sub_id = sub_resp.json()["id"]

    # Schedule for END_OF_TERM
    sched_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={"target_plan_id": plan2.id, "effective_type": "end_of_term"},
        headers=auth_headers,
    )
    assert sched_resp.status_code == 201
    change_id = sched_resp.json()["id"]
    assert sched_resp.json()["status"] == SubscriptionChangeStatus.SCHEDULED.value

    # Cancel scheduled change
    cancel_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes/{change_id}/cancel",
        headers=auth_headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == SubscriptionChangeStatus.CANCELLED.value


def test_scheduled_change_execution_via_worker_and_scheduler(client, tenant, auth_headers, db):
    from datetime import date, timedelta
    from backend.app.models.subscriptions import Subscription
    from backend.app.services.subscription_change_service import execute_due_scheduled_changes
    from backend.app.services.scheduler import run_billing_jobs

    customer = tenant.customer()
    p1, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    p2, plan2 = tenant.product_with_plan(unit_amount="2000.00")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan1.id, "quantity": 1},
        headers=auth_headers,
    )
    sub_id = sub_resp.json()["id"]

    # Schedule for END_OF_TERM
    sched_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={"target_plan_id": plan2.id, "effective_type": "end_of_term"},
        headers=auth_headers,
    )
    assert sched_resp.status_code == 201
    change_id = sched_resp.json()["id"]
    change_data = sched_resp.json()
    assert change_data["status"] == "scheduled"
    effective_date = date.fromisoformat(change_data["effective_date"])

    # 1. Running worker before effective_date should not apply it
    applied_early = execute_due_scheduled_changes(db, organization_id=tenant.organization.id, today=effective_date - timedelta(days=1))
    assert len(applied_early) == 0

    # 2. Running scheduler on effective_date executes the change
    counts = run_billing_jobs(db, today=effective_date)
    assert counts["scheduled_changes_applied"] >= 1

    # Verify subscription is now on plan2
    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    assert sub.plan_id == plan2.id


def test_scheduled_change_with_future_date_is_deferred_not_applied(client, tenant, auth_headers, db):
    """A SCHEDULED change dated in the future must NOT mutate the subscription today."""
    from datetime import date, timedelta
    from backend.app.models.subscriptions import Subscription
    from backend.app.models.invoices import Invoice
    from backend.app.services.subscription_change_service import execute_due_scheduled_changes

    customer = tenant.customer()
    p1, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    p2, plan2 = tenant.product_with_plan(unit_amount="3000.00")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan1.id, "quantity": 1},
        headers=auth_headers,
    )
    sub_id = sub_resp.json()["id"]
    invoices_before = db.query(Invoice).filter(Invoice.subscription_id == sub_id).count()

    future_date = date.today() + timedelta(days=10)
    sched_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={
            "target_plan_id": plan2.id,
            "effective_type": "scheduled",
            "effective_date": future_date.isoformat(),
        },
        headers=auth_headers,
    )
    assert sched_resp.status_code == 201, sched_resp.text
    body = sched_resp.json()
    assert body["status"] == SubscriptionChangeStatus.SCHEDULED.value
    assert body["effective_date"] == future_date.isoformat()

    # Subscription untouched and no proration invoice raised today
    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    db.refresh(sub)
    assert sub.plan_id == plan1.id
    assert db.query(Invoice).filter(Invoice.subscription_id == sub_id).count() == invoices_before

    # Worker does not pick it up before the effective date...
    assert execute_due_scheduled_changes(
        db, organization_id=tenant.organization.id, today=future_date - timedelta(days=1)
    ) == []

    # ...but does on the effective date.
    applied = execute_due_scheduled_changes(db, organization_id=tenant.organization.id, today=future_date)
    db.commit()
    assert [c.id for c in applied] == [body["id"]]
    db.refresh(sub)
    assert sub.plan_id == plan2.id


def test_scheduled_change_dated_today_applies_immediately(client, tenant, auth_headers, db):
    from datetime import date
    from backend.app.models.subscriptions import Subscription

    customer = tenant.customer()
    p1, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    p2, plan2 = tenant.product_with_plan(unit_amount="2000.00")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan1.id, "quantity": 1},
        headers=auth_headers,
    )
    sub_id = sub_resp.json()["id"]

    resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={
            "target_plan_id": plan2.id,
            "effective_type": "scheduled",
            "effective_date": date.today().isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == SubscriptionChangeStatus.APPLIED.value

    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    db.refresh(sub)
    assert sub.plan_id == plan2.id

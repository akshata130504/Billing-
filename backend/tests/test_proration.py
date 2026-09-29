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


def test_scheduled_mid_cycle_upgrade_bills_on_execution(client, tenant, auth_headers, db):
    """A genuinely mid-cycle scheduled change (not end-of-term) must raise the same
    credit note + prorated invoice the immediate path would, using the already-stored
    proration values - this is the gap that was fixed."""
    from datetime import date, timedelta
    from backend.app.models.subscriptions import Subscription
    from backend.app.services.subscription_change_service import execute_due_scheduled_changes

    customer = tenant.customer()
    p1, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    p2, plan2 = tenant.product_with_plan(unit_amount="2000.00")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan1.id, "quantity": 1},
        headers=auth_headers,
    )
    sub_id = sub_resp.json()["id"]

    future_date = date.today() + timedelta(days=10)
    sched_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={"target_plan_id": plan2.id, "effective_type": "scheduled", "effective_date": future_date.isoformat()},
        headers=auth_headers,
    )
    assert sched_resp.status_code == 201, sched_resp.text
    change = sched_resp.json()
    assert change["status"] == "scheduled"
    assert change["invoice_id"] is None
    assert change["credit_note_id"] is None
    prorated_credit = Decimal(change["prorated_credit"])
    prorated_charge = Decimal(change["prorated_charge"])
    net_amount = Decimal(change["net_amount"])
    assert prorated_credit > 0
    assert prorated_charge > 0

    applied = execute_due_scheduled_changes(db, organization_id=tenant.organization.id, today=future_date)
    db.commit()
    assert len(applied) == 1
    applied_change = applied[0]
    assert applied_change.status == SubscriptionChangeStatus.APPLIED
    assert applied_change.invoice_id is not None
    assert applied_change.credit_note_id is not None

    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    db.refresh(sub)
    assert sub.plan_id == plan2.id

    invoice = db.query(Invoice).filter(Invoice.id == applied_change.invoice_id).first()
    credit_note = db.query(CreditNote).filter(CreditNote.id == applied_change.credit_note_id).first()
    db.refresh(invoice)
    db.refresh(credit_note)

    # Both documents are proper tax documents: pre-tax amounts equal the stored
    # proration, and tax is added at the plan's product rate.
    assert invoice.subtotal == prorated_charge
    assert credit_note.subtotal == prorated_credit
    assert invoice.tax_amount > 0 and credit_note.tax_amount > 0
    # Upgrade: credit < charge, so the credit note is fully consumed by the offset,
    # leaving the invoice owing the (tax-inclusive) net difference.
    assert credit_note.balance_remaining == Decimal("0.00")
    assert invoice.amount_due == invoice.total - credit_note.total
    assert net_amount == prorated_charge - prorated_credit


def test_scheduled_mid_cycle_downgrade_bills_opposite_direction(client, tenant, auth_headers, db):
    """A downgrade nets a credit rather than a charge - both documents are still
    raised (old-plan credit is larger than new-plan charge), auto-offset pays the
    invoice fully and leaves the remaining credit on the credit note."""
    from datetime import date, timedelta
    from backend.app.models.subscriptions import Subscription
    from backend.app.services.subscription_change_service import execute_due_scheduled_changes

    customer = tenant.customer()
    p1, plan_hi = tenant.product_with_plan(unit_amount="2000.00")
    p2, plan_lo = tenant.product_with_plan(unit_amount="500.00")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan_hi.id, "quantity": 1},
        headers=auth_headers,
    )
    sub_id = sub_resp.json()["id"]

    future_date = date.today() + timedelta(days=10)
    sched_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={"target_plan_id": plan_lo.id, "effective_type": "scheduled", "effective_date": future_date.isoformat()},
        headers=auth_headers,
    )
    assert sched_resp.status_code == 201, sched_resp.text
    change = sched_resp.json()
    assert change["change_type"] == SubscriptionChangeType.DOWNGRADE.value
    prorated_credit = Decimal(change["prorated_credit"])
    prorated_charge = Decimal(change["prorated_charge"])
    net_amount = Decimal(change["net_amount"])
    assert prorated_credit > prorated_charge  # downgrade: bigger credit than charge
    assert net_amount < 0

    applied = execute_due_scheduled_changes(db, organization_id=tenant.organization.id, today=future_date)
    db.commit()
    assert len(applied) == 1
    applied_change = applied[0]
    assert applied_change.invoice_id is not None
    assert applied_change.credit_note_id is not None

    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    db.refresh(sub)
    assert sub.plan_id == plan_lo.id

    invoice = db.query(Invoice).filter(Invoice.id == applied_change.invoice_id).first()
    credit_note = db.query(CreditNote).filter(CreditNote.id == applied_change.credit_note_id).first()
    db.refresh(invoice)
    db.refresh(credit_note)

    assert invoice.subtotal == prorated_charge
    assert credit_note.subtotal == prorated_credit
    # The smaller invoice is fully offset/paid; the credit note keeps the remainder.
    assert invoice.amount_due == Decimal("0.00")
    assert invoice.status.value == "paid"
    assert credit_note.balance_remaining == (credit_note.total - invoice.total)
    assert net_amount == prorated_charge - prorated_credit


def test_scheduled_end_of_term_change_bills_nothing(client, tenant, auth_headers, db):
    """True end-of-term changes have net_amount == 0 (0 days remaining in the OLD
    period at the moment they take effect) - execution must not manufacture any
    invoice or credit note, and existing plan-switch behavior is unchanged."""
    from backend.app.models.subscriptions import Subscription
    from backend.app.services.subscription_change_service import execute_due_scheduled_changes

    customer = tenant.customer()
    p1, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    p2, plan2 = tenant.product_with_plan(unit_amount="2000.00")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan1.id, "quantity": 1},
        headers=auth_headers,
    )
    sub_id = sub_resp.json()["id"]

    sched_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={"target_plan_id": plan2.id, "effective_type": "end_of_term"},
        headers=auth_headers,
    )
    assert sched_resp.status_code == 201, sched_resp.text
    change = sched_resp.json()
    assert change["status"] == "scheduled"
    assert Decimal(change["net_amount"]) == Decimal("0.00")
    effective_date = date.fromisoformat(change["effective_date"])

    invoices_before = db.query(Invoice).filter(Invoice.subscription_id == sub_id).count()

    applied = execute_due_scheduled_changes(db, organization_id=tenant.organization.id, today=effective_date)
    db.commit()
    assert len(applied) == 1
    applied_change = applied[0]
    assert applied_change.status == SubscriptionChangeStatus.APPLIED
    assert applied_change.invoice_id is None
    assert applied_change.credit_note_id is None

    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    db.refresh(sub)
    assert sub.plan_id == plan2.id
    assert db.query(Invoice).filter(Invoice.subscription_id == sub_id).count() == invoices_before


def test_scheduled_change_execution_is_idempotent(client, tenant, auth_headers, db):
    """Running the scheduler twice for the same due change must not double-bill it."""
    from datetime import date, timedelta
    from backend.app.services.subscription_change_service import execute_due_scheduled_changes

    customer = tenant.customer()
    p1, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    p2, plan2 = tenant.product_with_plan(unit_amount="2000.00")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan1.id, "quantity": 1},
        headers=auth_headers,
    )
    sub_id = sub_resp.json()["id"]

    future_date = date.today() + timedelta(days=10)
    sched_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={"target_plan_id": plan2.id, "effective_type": "scheduled", "effective_date": future_date.isoformat()},
        headers=auth_headers,
    )
    change_id = sched_resp.json()["id"]

    first_run = execute_due_scheduled_changes(db, organization_id=tenant.organization.id, today=future_date)
    db.commit()
    assert len(first_run) == 1
    first_invoice_id = first_run[0].invoice_id
    first_credit_note_id = first_run[0].credit_note_id
    assert first_invoice_id is not None
    assert first_credit_note_id is not None

    invoice_count_after_first = db.query(Invoice).filter(Invoice.subscription_id == sub_id).count()
    credit_note_count_after_first = db.query(CreditNote).filter(CreditNote.subscription_id == sub_id).count()

    # Simulate the scheduler (or an overlapping worker) running again for the same window.
    second_run = execute_due_scheduled_changes(db, organization_id=tenant.organization.id, today=future_date)
    db.commit()
    assert second_run == []  # already APPLIED, so the due-changes query no longer selects it

    assert db.query(Invoice).filter(Invoice.subscription_id == sub_id).count() == invoice_count_after_first
    assert db.query(CreditNote).filter(CreditNote.subscription_id == sub_id).count() == credit_note_count_after_first

    from backend.app.models.proration import SubscriptionChange
    change = db.query(SubscriptionChange).filter(SubscriptionChange.id == change_id).first()
    db.refresh(change)
    assert change.invoice_id == first_invoice_id
    assert change.credit_note_id == first_credit_note_id


def test_scheduled_change_billing_failure_does_not_report_false_success(client, tenant, auth_headers, db, monkeypatch):
    """If credit-note/invoice creation blows up mid-execution, the change must be
    marked FAILED (not APPLIED), with no invoice/credit-note id and no plan switch -
    never silently reported as successfully billed."""
    from datetime import date, timedelta
    from backend.app.models.subscriptions import Subscription
    from backend.app.services import subscription_change_service

    customer = tenant.customer()
    p1, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    p2, plan2 = tenant.product_with_plan(unit_amount="2000.00")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan1.id, "quantity": 1},
        headers=auth_headers,
    )
    sub_id = sub_resp.json()["id"]
    # Baseline: creating the subscription already raises its own first-period invoice.
    invoices_before = db.query(Invoice).filter(Invoice.subscription_id == sub_id).count()
    credit_notes_before = db.query(CreditNote).filter(CreditNote.subscription_id == sub_id).count()

    future_date = date.today() + timedelta(days=10)
    sched_resp = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={"target_plan_id": plan2.id, "effective_type": "scheduled", "effective_date": future_date.isoformat()},
        headers=auth_headers,
    )
    change_id = sched_resp.json()["id"]

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated credit-note creation failure")

    monkeypatch.setattr(subscription_change_service.credit_service, "create_credit_note", _boom)

    applied = subscription_change_service.execute_due_scheduled_changes(
        db, organization_id=tenant.organization.id, today=future_date
    )
    assert applied == []

    from backend.app.models.proration import SubscriptionChange
    change = db.query(SubscriptionChange).filter(SubscriptionChange.id == change_id).first()
    assert change.status == SubscriptionChangeStatus.FAILED
    assert change.invoice_id is None
    assert change.credit_note_id is None

    # The subscription's plan mutation must have been rolled back with everything else.
    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    assert sub.plan_id == plan1.id
    assert db.query(Invoice).filter(Invoice.subscription_id == sub_id).count() == invoices_before
    assert db.query(CreditNote).filter(CreditNote.subscription_id == sub_id).count() == credit_notes_before


def test_admin_jobs_run_returns_scheduled_changes_and_dunning_counts(client, auth_headers, db):
    # POST /admin/jobs/run was removed (jobs run only in the scheduler process);
    # the counts contract lives on run_billing_jobs itself.
    from backend.app.services.scheduler import run_billing_jobs

    body = run_billing_jobs(db)
    assert "scheduled_changes_applied" in body
    assert "dunning_recovered" in body
    assert isinstance(body["scheduled_changes_applied"], int)
    assert isinstance(body["dunning_recovered"], int)


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


# --- production-readiness regressions ---------------------------------------------------------


def _new_sub(client, auth_headers, customer, plan, **extra):
    body = {"customer_id": customer.id, "plan_id": plan.id, "quantity": 1}
    body.update(extra)
    resp = client.post("/api/v1/subscriptions", json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_immediate_upgrade_moves_item_snapshot_and_renewal_bills_new_plan(client, tenant, auth_headers, db):
    from datetime import date
    from backend.app.models.billing_cycles import SubscriptionItem, SubscriptionItemType
    from backend.app.models.subscriptions import Subscription
    from backend.app.services.subscription_service import renew_subscription

    customer = tenant.customer()
    _, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    _, plan2 = tenant.product_with_plan(unit_amount="2500.00")
    sub_id = _new_sub(client, auth_headers, customer, plan1)

    resp = client.post(f"/api/v1/subscriptions/{sub_id}/changes", json={"target_plan_id": plan2.id}, headers=auth_headers)
    assert resp.status_code == 201, resp.text

    item = (
        db.query(SubscriptionItem)
        .filter(SubscriptionItem.subscription_id == sub_id, SubscriptionItem.item_type == SubscriptionItemType.PLAN)
        .one()
    )
    db.refresh(item)
    assert item.plan_id == plan2.id
    assert item.unit_price == Decimal("2500.00")
    assert item.price_snapshot.plan_id == plan2.id
    sub = db.get(Subscription, sub_id)
    db.refresh(sub)
    assert sub.unit_price == Decimal("2500.00")

    sub.next_billing_date = date.today()
    db.commit()
    assert renew_subscription(db, sub) == "renewed"
    db.commit()
    renewal = (
        db.query(Invoice)
        .filter(Invoice.subscription_id == sub_id, Invoice.period_start == sub.current_period_start)
        .one()
    )
    assert renewal.subtotal == Decimal("2500.00")


def test_change_on_trialing_subscription_swaps_plan_without_proration(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan1 = tenant.product_with_plan(unit_amount="1000.00", trial_days=14)
    _, plan2 = tenant.product_with_plan(unit_amount="3000.00")
    sub_id = _new_sub(client, auth_headers, customer, plan1)

    resp = client.post(f"/api/v1/subscriptions/{sub_id}/changes", json={"target_plan_id": plan2.id}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert Decimal(body["prorated_credit"]) == 0
    assert Decimal(body["prorated_charge"]) == 0
    assert body["invoice_id"] is None and body["credit_note_id"] is None
    assert client.get(f"/api/v1/subscriptions/{sub_id}", headers=auth_headers).json()["plan"]["id"] == plan2.id


def test_change_validation_rejects_bad_targets(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    _, inactive = tenant.product_with_plan(unit_amount="2000.00")
    _, usd = tenant.product_with_plan(unit_amount="20.00")
    inactive.is_active = False
    usd.currency = "USD"
    db.commit()
    sub_id = _new_sub(client, auth_headers, customer, plan1)

    url = f"/api/v1/subscriptions/{sub_id}/changes"
    assert client.post(url, json={"target_quantity": "2.5"}, headers=auth_headers).status_code == 422
    assert client.post(url, json={"target_plan_id": inactive.id}, headers=auth_headers).status_code == 422
    assert client.post(url, json={"target_plan_id": usd.id}, headers=auth_headers).status_code == 422


def test_proration_uses_contracted_price_not_current_list_price(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan1 = tenant.product_with_plan(unit_amount="1000.00")
    _, plan2 = tenant.product_with_plan(unit_amount="2000.00")
    sub_id = _new_sub(client, auth_headers, customer, plan1)
    plan1.unit_amount = Decimal("5000.00")  # list-price edit after signing
    db.commit()

    preview = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes/preview", json={"target_plan_id": plan2.id}, headers=auth_headers
    ).json()
    assert Decimal(preview["old_plan"]["unit_amount"]) == Decimal("1000.00")
    assert preview["change_type"] == "upgrade"


def test_flat_plan_quantity_change_has_no_proration(client, tenant, auth_headers, db):
    from backend.app.models import PricingModel

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    plan.pricing_model = PricingModel.FLAT
    db.commit()
    sub_id = _new_sub(client, auth_headers, customer, plan)
    resp = client.post(f"/api/v1/subscriptions/{sub_id}/changes", json={"target_quantity": 5}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert Decimal(resp.json()["net_amount"]) == 0
    assert resp.json()["invoice_id"] is None


def test_preview_returns_billed_per_cycle_rates_for_flat_target(client, tenant, auth_headers, db):
    """Browser QA regression: the preview card multiplied unit price x quantity and promised
    "New recurring at renewal 24,995" for 5 seats moving to a FLAT 4,999 plan. The preview
    now returns the per-cycle rates the proration (and renewal) actually use."""
    from backend.app.models import PricingModel

    customer = tenant.customer()
    _, per_unit = tenant.product_with_plan(unit_amount="650.00")
    _, flat = tenant.product_with_plan(unit_amount="4999.00")
    flat.pricing_model = PricingModel.FLAT
    db.commit()
    sub_id = _new_sub(client, auth_headers, customer, per_unit, quantity=5)

    preview = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes/preview",
        json={"target_plan_id": flat.id, "target_quantity": 5},
        headers=auth_headers,
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert Decimal(body["old_total_rate"]) == Decimal("3250.00")
    assert Decimal(body["new_total_rate"]) == Decimal("4999.00")

    scheduled = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={"target_plan_id": flat.id, "target_quantity": 5, "effective_type": "end_of_term"},
        headers=auth_headers,
    )
    assert scheduled.status_code == 201, scheduled.text
    assert Decimal(scheduled.json()["new_plan_amount"]) == Decimal(body["new_total_rate"])

"""Characterization tests for Subscription management and lifecycle."""
from datetime import date, timedelta
from decimal import Decimal
import uuid
import pytest

from backend.app.models import AuditLog, MemberRole, Subscription, SubscriptionStatus

BASE = "/api/v1/subscriptions"


def test_create_subscription_active_and_get(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1500.00", interval="monthly", trial_days=0)

    body = {
        "customer_id": customer.id,
        "plan_id": plan.id,
        "quantity": 2,
        "start_date": date.today().isoformat(),
        "notes": "Test subscription notes",
    }
    resp = client.post(BASE, json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["status"] == "active"
    assert data["customer"]["id"] == customer.id
    assert data["plan"]["id"] == plan.id
    assert data["quantity"] == 2
    assert data["subscription_number"].startswith("SUB-")
    assert data["current_period_start"] == date.today().isoformat()
    assert data["next_billing_date"] is not None

    sub_id = data["id"]
    get_resp = client.get(f"{BASE}/{sub_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == sub_id


def test_create_subscription_trialing(client, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1500.00", interval="monthly", trial_days=14)

    body = {
        "customer_id": customer.id,
        "plan_id": plan.id,
        "quantity": 1,
        "start_date": date.today().isoformat(),
    }
    resp = client.post(BASE, json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["status"] == "trialing"
    assert data["trial_end"] == (date.today() + timedelta(days=14)).isoformat()


def test_update_pause_resume_and_cancel_subscription(client, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan()

    resp = client.post(
        BASE,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    sub_id = resp.json()["id"]

    # Update quantity and notes
    patch_resp = client.patch(
        f"{BASE}/{sub_id}",
        json={"quantity": 5, "notes": "Updated note"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["quantity"] == 5
    assert patch_resp.json()["notes"] == "Updated note"

    # Pause
    pause_resp = client.post(f"{BASE}/{sub_id}/pause", headers=auth_headers)
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    # Resume
    resume_resp = client.post(f"{BASE}/{sub_id}/resume", headers=auth_headers)
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "active"

    # Cancel
    cancel_resp = client.post(
        f"{BASE}/{sub_id}/cancel",
        json={"at_period_end": False, "reason": "Customer request"},
        headers=auth_headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_generate_invoice_for_subscription(client, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1200.00")

    resp = client.post(
        BASE,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1, "generate_first_invoice": False},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    sub_id = resp.json()["id"]

    inv_resp = client.post(f"{BASE}/{sub_id}/generate-invoice", headers=auth_headers)
    assert inv_resp.status_code == 201, inv_resp.text
    inv_data = inv_resp.json()
    assert inv_data["customer"]["id"] == customer.id
    assert inv_data["subscription_id"] == sub_id
    assert inv_data["total"] > "0"

    list_resp = client.get(f"{BASE}/{sub_id}/invoices", headers=auth_headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1



def test_subscription_validation_errors(client, tenant, auth_headers):
    customer = tenant.customer()
    # Unknown plan
    resp = client.post(
        BASE,
        json={"customer_id": customer.id, "plan_id": str(uuid.uuid4()), "quantity": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 404

    # Unknown customer
    product, plan = tenant.product_with_plan()
    resp = client.post(
        BASE,
        json={"customer_id": str(uuid.uuid4()), "plan_id": plan.id, "quantity": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 404


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

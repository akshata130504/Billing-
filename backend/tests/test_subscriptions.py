"""Comprehensive Subscription Management Module tests."""
from datetime import date, timedelta
from decimal import Decimal
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.models import (
    BillingInterval,
    Customer,
    Invoice,
    InvoiceStatus,
    MembershipStatus,
    MemberRole,
    Plan,
    PricingModel,
    Product,
    ProductType,
    Subscription,
    SubscriptionStatus,
)


def test_subscription_creation_and_pricing_snapshot(client: TestClient, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1500.00", interval="monthly")

    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "quantity": 3,
            "notes": "VIP Client Subscription",
            "auto_renewal": True,
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["customer"]["id"] == customer.id
    assert data["plan"]["id"] == plan.id
    assert data["quantity"] == 3
    assert data["status"] == "active"
    assert data["billing_frequency"] == "monthly"
    assert data["currency"] == "INR"
    assert Decimal(data["unit_price"]) == Decimal("1500.00")
    assert Decimal(data["subtotal"]) == Decimal("4500.00")  # 3 * 1500
    assert Decimal(data["tax_amount"]) == Decimal("810.00")   # 18% of 4500
    assert Decimal(data["total_amount"]) == Decimal("5310.00")
    assert data["auto_renewal"] is True
    assert data["notes"] == "VIP Client Subscription"
    assert data["subscription_number"].startswith("SUB-")


def test_subscription_creation_inactive_plan_rejected(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan()
    plan.is_active = False
    db.commit()

    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
    )
    assert res.status_code == 422


def test_subscription_trial_lifecycle_and_conversion(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="2000.00", trial_days=14)

    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
    )
    assert res.status_code == 201
    data = res.json()

    assert data["status"] == "trialing"
    assert data["trial_start"] is not None
    assert data["trial_end"] is not None

    sub_id = data["id"]

    # Pause from trialing
    pause_res = client.post(f"/api/v1/subscriptions/{sub_id}/pause", headers=auth_headers)
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "paused"

    # Resume back to active
    resume_res = client.post(f"/api/v1/subscriptions/{sub_id}/resume", headers=auth_headers)
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "active"


def test_subscription_draft_and_activation(client: TestClient, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1200.00")

    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "quantity": 2,
            "status": "draft",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "draft"
    sub_id = data["id"]

    # Activate
    act_res = client.post(f"/api/v1/subscriptions/{sub_id}/activate", headers=auth_headers)
    assert act_res.status_code == 200
    assert act_res.json()["status"] == "active"


def test_subscription_pause_and_resume_lifecycle(client: TestClient, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="900.00")

    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
    )
    assert res.status_code == 201
    sub_id = res.json()["id"]

    # Pause
    pause_res = client.post(f"/api/v1/subscriptions/{sub_id}/pause", headers=auth_headers)
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "paused"
    assert pause_res.json()["paused_at"] is not None
    assert pause_res.json()["next_billing_date"] is None

    # Cannot pause an already paused subscription
    invalid_pause = client.post(f"/api/v1/subscriptions/{sub_id}/pause", headers=auth_headers)
    assert invalid_pause.status_code == 409

    # Resume
    resume_res = client.post(f"/api/v1/subscriptions/{sub_id}/resume", headers=auth_headers)
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "active"
    assert resume_res.json()["paused_at"] is None
    assert resume_res.json()["next_billing_date"] is not None


def test_subscription_cancellation_immediate_and_period_end(client: TestClient, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="500.00")

    # 1. Cancel at period end
    res1 = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
    )
    sub1_id = res1.json()["id"]

    cancel1_res = client.post(
        f"/api/v1/subscriptions/{sub1_id}/cancel",
        headers=auth_headers,
        json={"at_period_end": True, "reason": "Customer switching provider"},
    )
    assert cancel1_res.status_code == 200
    assert cancel1_res.json()["cancel_at_period_end"] is True
    assert cancel1_res.json()["status"] == "active"
    assert cancel1_res.json()["cancellation_reason"] == "Customer switching provider"

    # 2. Cancel immediately
    res2 = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
    )
    sub2_id = res2.json()["id"]

    cancel2_res = client.post(
        f"/api/v1/subscriptions/{sub2_id}/cancel",
        headers=auth_headers,
        json={"at_period_end": False, "reason": "Immediate termination"},
    )
    assert cancel2_res.status_code == 200
    assert cancel2_res.json()["status"] == "cancelled"
    assert cancel2_res.json()["cancelled_at"] is not None

    # Cannot cancel an already cancelled subscription
    re_cancel = client.post(
        f"/api/v1/subscriptions/{sub2_id}/cancel",
        headers=auth_headers,
        json={"at_period_end": False},
    )
    assert re_cancel.status_code == 409


def test_subscription_manual_renewal_and_invoicing(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="3000.00", interval="monthly")

    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1, "generate_first_invoice": True},
    )
    assert res.status_code == 201
    sub_id = res.json()["id"]
    orig_period_end = res.json()["current_period_end"]

    # Manual renewal advances period
    renew_res = client.post(f"/api/v1/subscriptions/{sub_id}/renew", headers=auth_headers)
    assert renew_res.status_code == 200
    renew_data = renew_res.json()
    assert renew_data["current_period_start"] == orig_period_end

    # Verify linked invoices
    inv_res = client.get(f"/api/v1/subscriptions/{sub_id}/invoices", headers=auth_headers)
    assert inv_res.status_code == 200
    invoices = inv_res.json()["items"]
    assert len(invoices) >= 2


def test_subscription_summary_kpi_metrics(client: TestClient, tenant, auth_headers):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1000.00")

    # Create 1 Active, 1 Paused, 1 Trialing
    client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
    )
    res_pause = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
    )
    client.post(f"/api/v1/subscriptions/{res_pause.json()['id']}/pause", headers=auth_headers)

    client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1, "trial_days": 7},
    )

    summary_res = client.get("/api/v1/subscriptions/summary", headers=auth_headers)
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["total_subscriptions"] >= 3
    assert summary["active_count"] >= 1
    assert summary["paused_count"] >= 1
    assert summary["trialing_count"] >= 1
    assert Decimal(summary["total_mrr"]) >= Decimal("1000.00")


def test_subscription_multi_tenant_isolation(client: TestClient, tenant, db):
    from backend.tests.conftest import Tenant

    tenant_b = Tenant(db, "org-b")
    customer_a = tenant.customer()
    customer_b = tenant_b.customer()
    product_a, plan_a = tenant.product_with_plan(unit_amount="1000.00")
    product_b, plan_b = tenant_b.product_with_plan(unit_amount="2000.00")

    # Org A creates a subscription
    res_a = client.post(
        "/api/v1/subscriptions",
        headers=tenant.headers(),
        json={"customer_id": customer_a.id, "plan_id": plan_a.id, "quantity": 1},
    )
    sub_a_id = res_a.json()["id"]

    # Org B cannot access Org A's subscription
    res_b_get = client.get(f"/api/v1/subscriptions/{sub_a_id}", headers=tenant_b.headers())
    assert res_b_get.status_code == 404

    # Org B cannot pause Org A's subscription
    res_b_pause = client.post(f"/api/v1/subscriptions/{sub_a_id}/pause", headers=tenant_b.headers())
    assert res_b_pause.status_code == 404


def test_subscription_rbac_viewer_permissions(client: TestClient, tenant):
    viewer_headers = tenant.headers_for_role(MemberRole.VIEWER)
    customer = tenant.customer()
    product, plan = tenant.product_with_plan()

    # Viewer cannot create subscription (requires finance/admin)
    create_res = client.post(
        "/api/v1/subscriptions",
        headers=viewer_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
    )
    assert create_res.status_code == 403

    # Owner creates subscription
    owner_create = client.post(
        "/api/v1/subscriptions",
        headers=tenant.headers(),
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
    )
    sub_id = owner_create.json()["id"]

    # Viewer CAN read subscription
    get_res = client.get(f"/api/v1/subscriptions/{sub_id}", headers=viewer_headers)
    assert get_res.status_code == 200

    # Viewer CANNOT pause or cancel
    pause_res = client.post(f"/api/v1/subscriptions/{sub_id}/pause", headers=viewer_headers)
    assert pause_res.status_code == 403

"""Automated tests for Phase 3 Trial Lifecycle: creation, extensions, conversions, fallback, and reporting."""
from datetime import date, timedelta
from decimal import Decimal
import pytest

from backend.app.models import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    Invoice,
    PaymentGateway,
    Plan,
    Subscription,
    SubscriptionStatus,
    TrialConversionStatus,
    TrialPeriod,
    TrialPeriodStatus,
)
from backend.app.services import trial_service


def test_trial_creation_and_details(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1500.00", trial_days=14)

    # 1. Create subscription via API
    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "quantity": 1,
            "start_date": str(date.today()),
        },
    )
    assert res.status_code == 201
    sub_data = res.json()
    assert sub_data["status"] == "trialing"
    sub_id = sub_data["id"]

    # 2. List trials endpoint
    res_list = client.get("/api/v1/trials", headers=auth_headers)
    assert res_list.status_code == 200
    trials_page = res_list.json()
    assert trials_page["total"] >= 1
    trial_entry = next((t for t in trials_page["items"] if t["subscription_id"] == sub_id), None)
    assert trial_entry is not None
    assert trial_entry["status"] == "active"
    assert trial_entry["extension_count"] == 0

    # 3. Get trial details
    res_detail = client.get(f"/api/v1/trials/{sub_id}", headers=auth_headers)
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["subscription_number"] == sub_data["subscription_number"]
    assert detail["trial_period"]["status"] == "active"
    assert len(detail["extensions"]) == 0


def test_trial_extension_lifecycle_and_caps(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1200.00", trial_days=7)

    # Create subscription
    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "quantity": 1,
            "start_date": str(date.today()),
        },
    )
    sub_id = res.json()["id"]

    # 1. First extension: add 5 days
    res_ext1 = client.post(
        f"/api/v1/trials/{sub_id}/extend",
        headers=auth_headers,
        json={"days": 5, "reason": "Customer needs more time to evaluate"},
    )
    assert res_ext1.status_code == 200
    tp1 = res_ext1.json()
    assert tp1["extension_count"] == 1

    # Verify subscription trial_end is updated
    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    db.refresh(sub)
    expected_end_1 = date.today() + timedelta(days=7 + 5)
    assert sub.trial_end == expected_end_1

    # 2. Second extension: add 3 days (reaches max_extensions_allowed=2)
    res_ext2 = client.post(
        f"/api/v1/trials/{sub_id}/extend",
        headers=auth_headers,
        json={"days": 3, "reason": "Technical integration test"},
    )
    assert res_ext2.status_code == 200
    tp2 = res_ext2.json()
    assert tp2["extension_count"] == 2

    # 3. Third extension without override should fail (max reached)
    res_ext3_fail = client.post(
        f"/api/v1/trials/{sub_id}/extend",
        headers=auth_headers,
        json={"days": 2, "reason": "Trying 3rd extension"},
    )
    assert res_ext3_fail.status_code in (400, 422)

    # 4. Third extension with admin_override should succeed
    res_ext3_override = client.post(
        f"/api/v1/trials/{sub_id}/extend",
        headers=auth_headers,
        json={"days": 2, "reason": "VIP customer approved by finance", "admin_override": True},
    )
    assert res_ext3_override.status_code == 200
    assert res_ext3_override.json()["extension_count"] == 3

    # Check detail endpoint reflects extensions audit history
    detail = client.get(f"/api/v1/trials/{sub_id}", headers=auth_headers).json()
    assert len(detail["extensions"]) == 3
    assert detail["extensions"][0]["extended_days"] == 5


def test_trial_early_conversion_to_live(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="2500.00", trial_days=14)

    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "quantity": 1,
            "start_date": str(date.today()),
        },
    )
    sub_id = res.json()["id"]

    # Convert trial to live early
    conv_res = client.post(
        f"/api/v1/trials/{sub_id}/convert",
        headers=auth_headers,
        json={"generate_first_invoice": True},
    )
    assert conv_res.status_code == 200
    conv_data = conv_res.json()
    assert conv_data["status"] == "active"
    assert conv_data["invoice_id"] is not None

    # Check subscription status in DB
    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    db.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE

    # Check invoice exists and is open
    inv = db.query(Invoice).filter(Invoice.id == conv_data["invoice_id"]).first()
    assert inv is not None
    assert inv.subscription_id == sub.id


def test_trial_expired_extension_reactivates_trialing(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1800.00", trial_days=7)

    sub = Subscription(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        plan_id=plan.id,
        quantity=1,
        status=SubscriptionStatus.TRIAL_EXPIRED,
        start_date=date.today() - timedelta(days=10),
        trial_end=date.today() - timedelta(days=3),
        current_period_start=date.today() - timedelta(days=10),
        current_period_end=date.today() - timedelta(days=3),
        subscription_number="SUB-TR-EXP-01",
    )
    db.add(sub)
    db.commit()

    # Verify initial status is TRIAL_EXPIRED
    assert sub.status == SubscriptionStatus.TRIAL_EXPIRED

    # Extend trial from expired state
    new_target = date.today() + timedelta(days=5)
    res = client.post(
        f"/api/v1/trials/{sub.id}/extend",
        headers=auth_headers,
        json={"new_expiration_date": str(new_target), "reason": "Customer called support to reactivate trial"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "active"

    db.refresh(sub)
    # Subscription status transitions back to TRIALING
    assert sub.status == SubscriptionStatus.TRIALING
    assert sub.trial_end == new_target


def test_trial_evaluation_auto_charge_with_payment_method(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="3000.00", trial_days=7)

    # Add a default customer payment method
    pm = CustomerPaymentMethod(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        gateway=PaymentGateway.MANUAL,
        type="card",
        gateway_token="tok_test_vault_card",
        last4="4242",
        card_brand="Visa",
        is_default=True,
        status=CustomerPaymentMethodStatus.ACTIVE,
    )
    db.add(pm)

    sub = Subscription(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        plan_id=plan.id,
        quantity=1,
        status=SubscriptionStatus.TRIALING,
        start_date=date.today() - timedelta(days=8),
        trial_end=date.today(),
        current_period_start=date.today() - timedelta(days=8),
        current_period_end=date.today(),
        subscription_number="SUB-AUTO-CONV-01",
    )
    db.add(sub)
    db.commit()

    # Trigger evaluation
    eval_res = client.post("/api/v1/trials/evaluate", headers=auth_headers)
    assert eval_res.status_code == 200
    stats = eval_res.json()
    assert stats["converted"] >= 1

    db.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE


def test_trial_reports_and_analytics(client, tenant, auth_headers, db):
    # Retrieve acquisition insights trial reports
    res = client.get("/api/v1/trials/reports", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "active_trials_count" in data
    assert "expiring_in_7_days_count" in data
    assert "inactive_trials_count" in data
    assert "converted_trials_count" in data
    assert "overall_conversion_rate_pct" in data
    assert "average_sales_cycle_days" in data
    assert isinstance(data["by_plan"], list)


def test_trial_conversion_declined_charge_does_not_fabricate_success(client, tenant, auth_headers, db):
    """Regression test: when a payment gateway declines the trial conversion charge,
    the system must record the real failure and NOT manufacture a fake manual success or mark invoice paid."""
    from backend.app.services.gateways.base import GatewayChargeResult
    from backend.app.services.gateways.registry import get_gateway_adapter, register_gateway_adapter

    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="4000.00", trial_days=7)

    pm = CustomerPaymentMethod(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        gateway=PaymentGateway.RAZORPAY,
        type="card",
        gateway_token="tok_declining_card",
        last4="1111",
        card_brand="Visa",
        is_default=True,
        status=CustomerPaymentMethodStatus.ACTIVE,
    )
    db.add(pm)

    sub = Subscription(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        plan_id=plan.id,
        quantity=1,
        status=SubscriptionStatus.TRIALING,
        start_date=date.today() - timedelta(days=8),
        trial_end=date.today(),
        current_period_start=date.today() - timedelta(days=8),
        current_period_end=date.today(),
        subscription_number="SUB-FAIL-CONV-01",
    )
    db.add(sub)
    db.commit()

    real_adapter = get_gateway_adapter(PaymentGateway.RAZORPAY)

    class _DecliningGateway:
        gateway_type = PaymentGateway.RAZORPAY

        def charge(self, **kwargs):
            return GatewayChargeResult(
                success=False,
                error_message="Insufficient funds in customer card.",
                error_category="insufficient_funds",
            )

        def refund(self, **kwargs):
            raise NotImplementedError

        def verify_webhook(self, **kwargs):
            return True

        def verify_payment_signature(self, **kwargs):
            return False

    register_gateway_adapter(PaymentGateway.RAZORPAY, _DecliningGateway())
    try:
        eval_res = client.post("/api/v1/trials/evaluate", headers=auth_headers)
        assert eval_res.status_code == 200
        stats = eval_res.json()
        assert stats["converted"] == 0
        assert stats["expired"] >= 1
    finally:
        register_gateway_adapter(PaymentGateway.RAZORPAY, real_adapter)

    db.refresh(sub)
    assert sub.status == SubscriptionStatus.TRIAL_EXPIRED

    # Verify invoice was not marked paid
    inv = db.query(Invoice).filter(Invoice.subscription_id == sub.id).first()
    if inv:
        assert inv.status != "paid"
        assert inv.amount_due > Decimal("0.00")

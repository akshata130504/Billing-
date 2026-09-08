"""Tests for Phase 5: Collections & Dunning Management.

Verifies:
- Dunning policy creation, validation, and tier matching.
- Dunning case initiation on payment failure, idempotent case reuse.
- Special rule: First ACH invoice failure leads directly to cancellation.
- Scheduled retry execution, successful recovery, and subscription restoration.
- Exhaustion of retries and configurable final action (CANCEL_AND_VOID vs UNPAID).
- Pause, resume, and stop controls.
- In-term reactivation of dunning-cancelled subscriptions.
- Recovery metrics and pre-dunning card-expiry detection.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.app.models.dunning import (
    DunningAttemptStatus,
    DunningCase,
    DunningCaseStatus,
    DunningFinalAction,
    DunningPolicy,
)
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.payments import CustomerPaymentMethod, CustomerPaymentMethodStatus
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.services import dunning_service


def test_dunning_policy_crud_and_segmentation(client, tenant, auth_headers, db):
    # 1. List default policies (lazily initializes default policy)
    res = client.get("/api/v1/dunning/policies", headers=auth_headers)
    assert res.status_code == 200
    policies = res.json()
    assert len(policies) >= 1
    default_p = policies[0]
    assert default_p["is_default"] is True
    assert default_p["max_retries"] == 3
    assert default_p["total_span_days"] == 30

    # 2. Create custom high-value policy
    custom_data = {
        "name": "High Value Enterprise Recovery",
        "description": "Gentle 3-retry sequence for enterprise contracts",
        "is_default": False,
        "is_active": True,
        "applies_to_autocharge": True,
        "min_amount": "50000.00",
        "max_retries": 3,
        "retry_intervals_days": [5, 7, 10],
        "total_span_days": 30,
        "notify_on_failure": True,
        "notify_on_retry": True,
        "notify_on_success": True,
        "first_ach_immediate_cancel": True,
        "final_action": "cancel_and_void",
        "non_autocharge_grace_days": 20,
    }
    create_res = client.post("/api/v1/dunning/policies", headers=auth_headers, json=custom_data)
    assert create_res.status_code == 200
    created = create_res.json()
    assert created["name"] == "High Value Enterprise Recovery"
    assert Decimal(created["min_amount"]) == Decimal("50000.00")

    # 3. Test validation rejection (retries > 3 or span exceeded)
    bad_data = dict(custom_data, name="Invalid Policy", retry_intervals_days=[15, 15, 10])  # sum 40 > 30
    bad_res = client.post("/api/v1/dunning/policies", headers=auth_headers, json=bad_data)
    assert bad_res.status_code == 422


def test_trigger_dunning_case_on_autocharge_failure(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="3500.00")

    # Create active subscription
    sub = Subscription(
        organization_id=tenant.organization.id,
        subscription_number=f"SUB-{uuid.uuid4().hex[:6].upper()}",
        customer_id=customer.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        quantity=1,
        start_date=date.today(),
        current_period_start=date.today(),
        current_period_end=date.today() + timedelta(days=30),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    # Create unpaid renewal invoice
    inv = tenant.invoice(customer, amount="3500.00", status=InvoiceStatus.SENT)

    # Trigger dunning for failed card payment
    case = dunning_service.trigger_dunning_for_failed_payment(
        db=db,
        organization_id=tenant.organization.id,
        invoice_id=inv.id,
        customer_id=customer.id,
        subscription_id=sub.id,
        reason="card_declined: insufficient_funds",
        payment_method_type="card",
    )
    db.commit()

    assert case.status == DunningCaseStatus.RETRY_SCHEDULED
    assert case.attempt_count == 0
    assert case.max_attempts == 3
    assert case.next_retry_at is not None
    assert len(case.attempts) == 1
    assert case.attempts[0].attempt_number == 1
    assert case.attempts[0].status == DunningAttemptStatus.SCHEDULED

    # Subscription moved to past_due
    db.refresh(sub)
    assert sub.status == SubscriptionStatus.PAST_DUE

    # Communication log recorded
    assert len(case.communications) == 1
    assert case.communications[0].template_type == "failure"

    # Idempotent re-trigger returns the active case
    duplicate_case = dunning_service.trigger_dunning_for_failed_payment(
        db=db,
        organization_id=tenant.organization.id,
        invoice_id=inv.id,
        customer_id=customer.id,
        subscription_id=sub.id,
    )
    assert duplicate_case.id == case.id


def test_first_ach_failure_immediate_cancellation(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="5000.00")

    sub = Subscription(
        organization_id=tenant.organization.id,
        subscription_number=f"SUB-{uuid.uuid4().hex[:6].upper()}",
        customer_id=customer.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        quantity=1,
        start_date=date.today(),
        current_period_start=date.today(),
        current_period_end=date.today() + timedelta(days=30),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    # First invoice
    inv = tenant.invoice(customer, amount="5000.00", status=InvoiceStatus.SENT)
    inv.subscription_id = sub.id
    db.commit()

    # Trigger dunning for first ACH failure
    case = dunning_service.trigger_dunning_for_failed_payment(
        db=db,
        organization_id=tenant.organization.id,
        invoice_id=inv.id,
        customer_id=customer.id,
        subscription_id=sub.id,
        reason="ach_return_code: R01",
        payment_method_type="ach",
    )
    db.commit()

    # First ACH failure must cancel immediately per Zoho spec
    assert case.status == DunningCaseStatus.FINALIZED
    assert case.final_action_taken == "first_ach_cancelled"

    db.refresh(sub)
    db.refresh(inv)
    assert sub.status == SubscriptionStatus.CANCELLED
    assert inv.status == InvoiceStatus.VOID


def _fresh_dunning_case_with_pm(db, tenant, *, gateway: str, amount: str = "2500.00"):
    """Shared setup: an active subscription, an overdue invoice, an open dunning case, and
    one saved payment method on the given gateway. Returns (case, invoice, subscription)."""
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount=amount)

    sub = Subscription(
        organization_id=tenant.organization.id,
        subscription_number=f"SUB-{uuid.uuid4().hex[:6].upper()}",
        customer_id=customer.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        quantity=1,
        start_date=date.today(),
        current_period_start=date.today(),
        current_period_end=date.today() + timedelta(days=30),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    inv = tenant.invoice(customer, amount=amount, status=InvoiceStatus.SENT)

    case = dunning_service.trigger_dunning_for_failed_payment(
        db=db,
        organization_id=tenant.organization.id,
        invoice_id=inv.id,
        customer_id=customer.id,
        subscription_id=sub.id,
        reason="card_declined",
        payment_method_type="card",
    )
    db.commit()

    pm = CustomerPaymentMethod(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        type="card",
        status=CustomerPaymentMethodStatus.ACTIVE,
        gateway=gateway,
        gateway_token="tok_recovered_card",
        last4="4242",
        card_brand="visa",
        exp_month=12,
        exp_year=2028,
        is_default=True,
    )
    db.add(pm)
    db.commit()

    case.next_retry_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    return case, inv, sub


def test_dunning_retry_success_recovery(client, tenant, auth_headers, db):
    """A real gateway charge (via the adapter contract) is what recovers a case — not merely
    having a saved payment method on file. Uses a test double bound to the same
    PaymentGatewayAdapter contract production code calls, per the gateway registry."""
    from backend.app.models.payments import PaymentGateway
    from backend.app.services.gateways.base import GatewayChargeResult
    from backend.app.services.gateways.registry import get_gateway_adapter, register_gateway_adapter

    case, inv, sub = _fresh_dunning_case_with_pm(db, tenant, gateway="razorpay")

    real_adapter = get_gateway_adapter(PaymentGateway.RAZORPAY)

    class _SucceedingTestAdapter:
        gateway_type = PaymentGateway.RAZORPAY

        def charge(self, **kwargs):
            return GatewayChargeResult(success=True, gateway_payment_id="test_charge_recovered_001")

        def refund(self, **kwargs):
            raise NotImplementedError

        def verify_webhook(self, **kwargs):
            return True

    register_gateway_adapter(PaymentGateway.RAZORPAY, _SucceedingTestAdapter())
    try:
        res = dunning_service.execute_dunning_retries(db, tenant.organization.id)
        db.commit()
    finally:
        register_gateway_adapter(PaymentGateway.RAZORPAY, real_adapter)

    assert res["recovered_count"] == 1

    db.refresh(case)
    db.refresh(inv)
    db.refresh(sub)

    assert case.status == DunningCaseStatus.RECOVERED
    assert case.recovered_at is not None
    assert case.recovered_by_payment_id is not None
    assert inv.status == InvoiceStatus.PAID
    assert inv.amount_due == Decimal("0.00")
    assert sub.status == SubscriptionStatus.ACTIVE


def test_dunning_retry_never_fabricates_success_for_manual_or_declined_charge(client, tenant, auth_headers, db):
    """Regression test for the fixed vulnerability: merely having a saved payment method
    (even an active one) must never be treated as a successful charge. A manual/offline
    method cannot be auto-charged at all, and a real gateway decline must not recover the case."""
    from backend.app.models.payments import PaymentGateway
    from backend.app.services.gateways.base import GatewayChargeResult
    from backend.app.services.gateways.registry import get_gateway_adapter, register_gateway_adapter

    # Case 1: a MANUAL-gateway saved method on file must not auto-recover the case.
    case_manual, inv_manual, _ = _fresh_dunning_case_with_pm(db, tenant, gateway="manual", amount="1000.00")
    res_manual = dunning_service.execute_dunning_retries(db, tenant.organization.id)
    db.commit()
    db.refresh(case_manual)
    db.refresh(inv_manual)
    assert res_manual["recovered_count"] == 0
    assert case_manual.status != DunningCaseStatus.RECOVERED
    assert inv_manual.status != InvoiceStatus.PAID
    assert inv_manual.amount_due > Decimal("0.00")

    # Case 2: a real gateway that explicitly declines the charge must not recover the case.
    case_declined, inv_declined, _ = _fresh_dunning_case_with_pm(db, tenant, gateway="razorpay", amount="1500.00")
    real_adapter = get_gateway_adapter(PaymentGateway.RAZORPAY)

    class _DecliningTestAdapter:
        gateway_type = PaymentGateway.RAZORPAY

        def charge(self, **kwargs):
            return GatewayChargeResult(success=False, error_message="Card declined.", error_category="card_declined")

        def refund(self, **kwargs):
            raise NotImplementedError

        def verify_webhook(self, **kwargs):
            return True

    register_gateway_adapter(PaymentGateway.RAZORPAY, _DecliningTestAdapter())
    try:
        res_declined = dunning_service.execute_dunning_retries(db, tenant.organization.id)
        db.commit()
    finally:
        register_gateway_adapter(PaymentGateway.RAZORPAY, real_adapter)

    db.refresh(case_declined)
    db.refresh(inv_declined)
    assert res_declined["recovered_count"] == 0
    assert case_declined.status != DunningCaseStatus.RECOVERED
    assert inv_declined.status != InvoiceStatus.PAID
    assert inv_declined.amount_due > Decimal("0.00")
    # The failure reason recorded on the case's latest attempt must reflect the real decline,
    # not a hard-coded generic message.
    latest_attempt = next(a for a in case_declined.attempts if a.attempt_number == case_declined.attempt_count)
    assert latest_attempt.error_code == "card_declined"
    assert latest_attempt.error_message == "Card declined."


def test_dunning_retry_exhaustion_final_actions(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1200.00")

    sub = Subscription(
        organization_id=tenant.organization.id,
        subscription_number=f"SUB-{uuid.uuid4().hex[:6].upper()}",
        customer_id=customer.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        quantity=1,
        start_date=date.today(),
        current_period_start=date.today(),
        current_period_end=date.today() + timedelta(days=30),
    )
    db.add(sub)
    db.commit()

    inv = tenant.invoice(customer, amount="1200.00", status=InvoiceStatus.SENT)

    # Configure policy with CANCEL_AND_VOID
    policy = dunning_service.get_or_create_default_policy(db, tenant.organization.id)
    policy.final_action = DunningFinalAction.CANCEL_AND_VOID
    db.commit()

    case = dunning_service.trigger_dunning_for_failed_payment(
        db=db,
        organization_id=tenant.organization.id,
        invoice_id=inv.id,
        customer_id=customer.id,
        subscription_id=sub.id,
        reason="card_declined",
        payment_method_type="card",
    )
    db.commit()

    # Simulate 3 failed retry attempts (no payment method)
    for i in range(3):
        case.next_retry_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
        dunning_service.execute_dunning_retries(db, tenant.organization.id)
        db.commit()
        db.refresh(case)

    # After 3 failed retries, case is finalized
    assert case.status == DunningCaseStatus.FINALIZED
    assert case.final_action_taken == "cancel_and_void"

    db.refresh(sub)
    db.refresh(inv)
    assert sub.status == SubscriptionStatus.CANCELLED
    assert inv.status == InvoiceStatus.VOID

    from backend.app.models.governance import ApprovalRequest, ApprovalType
    approval = db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.organization_id == tenant.organization.id,
            ApprovalRequest.entity_id == inv.id,
            ApprovalRequest.type == ApprovalType.INVOICE_VOID,
        )
    ).first()
    assert approval is not None
    assert approval.status == "approved"


def test_dunning_case_pause_resume_stop(client, tenant, auth_headers, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="800.00", status=InvoiceStatus.SENT)

    case = dunning_service.trigger_dunning_for_failed_payment(
        db=db,
        organization_id=tenant.organization.id,
        invoice_id=inv.id,
        customer_id=customer.id,
    )
    db.commit()

    # Pause case via API
    pause_res = client.post(
        f"/api/v1/dunning/cases/{case.id}/pause",
        headers=auth_headers,
        json={"reason": "Customer requested 3-day extension to transfer funds"},
    )
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "paused"
    assert pause_res.json()["pause_reason"] == "Customer requested 3-day extension to transfer funds"

    # Resume case via API
    resume_res = client.post(
        f"/api/v1/dunning/cases/{case.id}/resume",
        headers=auth_headers,
    )
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "retry_scheduled"

    # Stop case via API
    stop_res = client.post(
        f"/api/v1/dunning/cases/{case.id}/stop",
        headers=auth_headers,
        json={"reason": "Manual agreement reached offline", "apply_final_action": False},
    )
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"


def test_dunning_metrics_and_expiring_cards(client, tenant, auth_headers, db):
    customer = tenant.customer()

    # Add card expiring this month
    today = date.today()
    card = CustomerPaymentMethod(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        type="card",
        status=CustomerPaymentMethodStatus.ACTIVE,
        gateway="manual",
        gateway_token="tok_expiring_soon",
        last4="9999",
        card_brand="mastercard",
        exp_month=today.month,
        exp_year=today.year,
    )
    db.add(card)
    db.commit()

    # Query expiring cards API
    card_res = client.get("/api/v1/dunning/expiring-cards?days=30", headers=auth_headers)
    assert card_res.status_code == 200
    notices = card_res.json()
    assert len(notices) >= 1
    assert notices[0]["card_last4"] == "9999"

    # Query metrics API
    metrics_res = client.get("/api/v1/dunning/metrics", headers=auth_headers)
    assert metrics_res.status_code == 200
    metrics = metrics_res.json()
    assert "recovery_rate_pct" in metrics
    assert "total_amount_at_risk" in metrics
    assert "total_amount_recovered" in metrics


def test_in_term_reactivation_of_cancelled_subscription(client, tenant, auth_headers, db):
    customer = tenant.customer()
    product, plan = tenant.product_with_plan(unit_amount="1500.00")

    sub = Subscription(
        organization_id=tenant.organization.id,
        subscription_number=f"SUB-{uuid.uuid4().hex[:6].upper()}",
        customer_id=customer.id,
        plan_id=plan.id,
        status=SubscriptionStatus.CANCELLED,
        quantity=1,
        start_date=date.today(),
        current_period_start=date.today(),
        current_period_end=date.today() + timedelta(days=30),
    )
    db.add(sub)
    db.commit()

    # Call reactivation API
    res = client.post(f"/api/v1/dunning/subscriptions/{sub.id}/reactivate", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    db.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE

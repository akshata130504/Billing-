"""Comprehensive Customer Lifecycle Module tests."""
from datetime import date, timedelta
from decimal import Decimal
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.models import (
    Customer,
    CustomerLifecycle,
    CustomerLifecycleStage,
    HealthStatus,
    Invoice,
    InvoiceStatus,
    MemberRole,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Quote,
    QuoteStatus,
    Subscription,
    SubscriptionStatus,
    TimeEntry,
    TimeEntryStatus,
    utcnow,
)


def test_lifecycle_list_and_kpis(client: TestClient, tenant, auth_headers):
    # Setup customer
    customer = tenant.customer(display_name="Enterprise Corp")

    res = client.get("/api/v1/lifecycle", headers=auth_headers)
    assert res.status_code == 200, res.text
    items = res.json()
    assert len(items) >= 1
    found = next((i for i in items if i["customer_id"] == customer.id), None)
    assert found is not None
    assert found["customer_name"] == "Enterprise Corp"
    assert found["lifecycle_stage"] in ["active", "onboarding", "prospect"]

    kpi_res = client.get("/api/v1/lifecycle/kpis", headers=auth_headers)
    assert kpi_res.status_code == 200, kpi_res.text
    kpis = kpi_res.json()
    assert kpis["total_customers"] >= 1
    assert "active_customers_count" in kpis
    assert "at_risk_count" in kpis


def test_lifecycle_stage_transition_and_audit(client: TestClient, tenant, auth_headers):
    customer = tenant.customer(display_name="Acme Renewal Corp")

    # Update stage to RENEWAL_DUE with high health
    update_res = client.patch(
        f"/api/v1/lifecycle/{customer.id}",
        headers=auth_headers,
        json={
            "lifecycle_stage": "renewal_due",
            "health_status": "healthy",
            "health_score": 95,
            "next_action": "Send annual renewal proposal",
            "next_action_due": date.today().isoformat(),
            "notes": "Key account up for renewal.",
        },
    )
    assert update_res.status_code == 200, update_res.text
    updated = update_res.json()
    assert updated["lifecycle_stage"] == "renewal_due"
    assert updated["health_score"] == 95
    assert updated["next_action"] == "Send annual renewal proposal"


def test_customer_lifecycle_detail_and_relationships(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer(display_name="Relationship Corp")
    product, plan = tenant.product_with_plan()

    # Add real subscription
    sub = Subscription(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        plan_id=plan.id,
        subscription_number=f"SUB-{uuid.uuid4().hex[:6].upper()}",
        status=SubscriptionStatus.ACTIVE,
        billing_frequency="monthly",
        currency="INR",
        unit_price=Decimal("2000.00"),
        subtotal=Decimal("2000.00"),
        total_amount=Decimal("2360.00"),
        start_date=date.today(),
        current_period_start=date.today(),
        current_period_end=date.today() + timedelta(days=30),
    )
    db.add(sub)

    # Add real time entry
    time_entry = TimeEntry(
        organization_id=tenant.organization.id,
        user_id=tenant.owner.id,
        customer_id=customer.id,
        project_name="Cloud Migration",
        date=date.today(),
        duration_hours=Decimal("12.50"),
        description="Architecture setup",
        billable=True,
        billing_rate=Decimal("150.00"),
        billable_amount=Decimal("1875.00"),
        status=TimeEntryStatus.APPROVED,
    )
    db.add(time_entry)
    db.commit()

    detail_res = client.get(f"/api/v1/lifecycle/{customer.id}", headers=auth_headers)
    assert detail_res.status_code == 200, detail_res.text
    detail = detail_res.json()

    assert detail["customer"]["id"] == customer.id
    assert len(detail["subscriptions"]) >= 1
    assert detail["timesheet_summary"]["total_entries"] >= 1
    assert Decimal(detail["timesheet_summary"]["total_hours"]) == Decimal("12.50")
    assert Decimal(detail["timesheet_summary"]["billable_amount"]) == Decimal("1875.00")


def test_lifecycle_timeline_events(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer(display_name="Timeline Inc")

    # Add quote
    quote = Quote(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        quote_number=f"QT-{uuid.uuid4().hex[:6].upper()}",
        status=QuoteStatus.ACCEPTED,
        issue_date=date.today() - timedelta(days=10),
        expiry_date=date.today() + timedelta(days=20),
        subtotal=Decimal("10000.00"),
        total=Decimal("11800.00"),
        public_token=uuid.uuid4().hex,
        accepted_at=utcnow() - timedelta(days=8),
    )
    db.add(quote)

    # Add payment
    payment = Payment(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        payment_number=f"PAY-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal("5000.00"),
        currency="INR",
        status=PaymentStatus.SUCCEEDED,
        method=PaymentMethod.UPI,
        paid_at=utcnow() - timedelta(days=5),
    )
    db.add(payment)
    db.commit()

    timeline_res = client.get(f"/api/v1/lifecycle/{customer.id}/timeline", headers=auth_headers)
    assert timeline_res.status_code == 200, timeline_res.text
    timeline = timeline_res.json()

    event_types = [e["event_type"] for e in timeline]
    assert "CUSTOMER_CREATED" in event_types
    assert "QUOTE_CREATED" in event_types
    assert "QUOTE_ACCEPTED" in event_types
    assert "PAYMENT_RECEIVED" in event_types


def test_lifecycle_tenant_isolation(client: TestClient, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other_tenant = Tenant(db, suffix=uuid.uuid4().hex[:6])
    other_auth_headers = other_tenant.headers()

    # Customer in tenant 1
    cust1 = tenant.customer(display_name="Tenant 1 Exclusive Corp")

    # Accessing from tenant 2 should yield 404
    res = client.get(f"/api/v1/lifecycle/{cust1.id}", headers=other_auth_headers)
    assert res.status_code == 404

    # Timeline access from tenant 2 should yield 404
    t_res = client.get(f"/api/v1/lifecycle/{cust1.id}/timeline", headers=other_auth_headers)
    assert t_res.status_code == 404

    # Update attempt from tenant 2 should yield 404
    p_res = client.patch(
        f"/api/v1/lifecycle/{cust1.id}",
        headers=other_auth_headers,
        json={"lifecycle_stage": "churned"},
    )
    assert p_res.status_code == 404


def test_lifecycle_invalid_customer_returns_404(client: TestClient, tenant, auth_headers):
    fake_id = "00000000-0000-0000-0000-000000000000"
    res = client.get(f"/api/v1/lifecycle/{fake_id}", headers=auth_headers)
    assert res.status_code == 404


def test_lifecycle_stage_filter(client: TestClient, tenant, auth_headers):
    c1 = tenant.customer(display_name="Filter Customer A")
    client.patch(
        f"/api/v1/lifecycle/{c1.id}",
        headers=auth_headers,
        json={"lifecycle_stage": "at_risk"},
    )

    res = client.get("/api/v1/lifecycle?stage=at_risk", headers=auth_headers)
    assert res.status_code == 200
    items = res.json()
    for item in items:
        assert item["lifecycle_stage"] == "at_risk"

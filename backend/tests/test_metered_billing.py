"""Tests for Metered Billing, event ingestion, and usage aggregation (Phase 2)."""
from datetime import date, datetime, timezone
from decimal import Decimal
import pytest

from backend.app.models.billing_cycles import BillingCycle, BillingCycleStatus
from backend.app.models.meters import AggregationType, UsageAggregateStatus


def test_meter_definition_and_duplicate_handling(client, tenant, auth_headers):
    # 1. Create a meter
    resp = client.post(
        "/api/v1/meters",
        json={
            "code": "api_calls",
            "name": "API Invocations",
            "unit_name": "request",
            "aggregation_type": "sum",
            "description": "Total count of external API calls",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    meter_data = resp.json()
    assert meter_data["code"] == "api_calls"
    assert meter_data["aggregation_type"] == "sum"

    # 2. Duplicate code in same org rejected
    dup_resp = client.post(
        "/api/v1/meters",
        json={
            "code": "api_calls",
            "name": "Duplicate Meter",
            "unit_name": "call",
        },
        headers=auth_headers,
    )
    assert dup_resp.status_code == 409

    # 3. List meters
    list_resp = client.get("/api/v1/meters", headers=auth_headers)
    assert list_resp.status_code == 200
    meters = list_resp.json()
    assert len(meters) >= 1
    assert any(m["code"] == "api_calls" for m in meters)


def test_usage_event_idempotent_ingestion_and_aggregation(client, tenant, auth_headers, db):
    customer = tenant.customer()
    p, plan = tenant.product_with_plan(unit_amount="500.00")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
        headers=auth_headers,
    )
    sub_id = sub_resp.json()["id"]

    # 1. Create Meter
    client.post(
        "/api/v1/meters",
        json={
            "code": "compute_hours",
            "name": "Compute Hours",
            "unit_name": "hour",
            "aggregation_type": "sum",
        },
        headers=auth_headers,
    )

    # 2. Ingest single event
    ev_resp = client.post(
        "/api/v1/meters/events",
        json={
            "meter_code": "compute_hours",
            "customer_id": customer.id,
            "subscription_id": sub_id,
            "quantity": 12.5,
            "idempotency_key": "evt-job-001",
        },
        headers=auth_headers,
    )
    assert ev_resp.status_code == 201, ev_resp.text
    ev1 = ev_resp.json()
    assert ev1["quantity"] == "12.5000"

    # 3. Ingest with SAME idempotency key (must deduplicate without error)
    ev_dup_resp = client.post(
        "/api/v1/meters/events",
        json={
            "meter_code": "compute_hours",
            "customer_id": customer.id,
            "subscription_id": sub_id,
            "quantity": 12.5,
            "idempotency_key": "evt-job-001",
        },
        headers=auth_headers,
    )
    assert ev_dup_resp.status_code == 201
    assert ev_dup_resp.json()["id"] == ev1["id"]

    # 4. Batch ingestion
    batch_resp = client.post(
        "/api/v1/meters/events/batch",
        json={
            "events": [
                {
                    "meter_code": "compute_hours",
                    "customer_id": customer.id,
                    "subscription_id": sub_id,
                    "quantity": 5.0,
                    "idempotency_key": "evt-job-002",
                },
                {
                    "meter_code": "compute_hours",
                    "customer_id": customer.id,
                    "subscription_id": sub_id,
                    "quantity": 7.5,
                    "idempotency_key": "evt-job-003",
                },
            ]
        },
        headers=auth_headers,
    )
    assert batch_resp.status_code == 201
    assert len(batch_resp.json()) == 2

    # 5. Get existing or create billing cycle to test finalization
    cycle = db.query(BillingCycle).filter(BillingCycle.subscription_id == sub_id).first()
    if not cycle:
        cycle = BillingCycle(
            organization_id=tenant.organization.id,
            subscription_id=sub_id,
            cycle_number=1,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status=BillingCycleStatus.OPEN,
        )
        db.add(cycle)
    else:
        cycle.period_start = date(2026, 1, 1)
        cycle.period_end = date(2026, 12, 31)
        cycle.status = BillingCycleStatus.OPEN
    db.commit()
    db.refresh(cycle)

    # 6. Finalize usage for cycle: total = 12.5 + 5.0 + 7.5 = 25.0
    finalize_resp = client.post(
        f"/api/v1/meters/subscriptions/{sub_id}/billing-cycles/{cycle.id}/finalize-usage",
        headers=auth_headers,
    )
    assert finalize_resp.status_code == 200, finalize_resp.text
    agg = finalize_resp.json()
    assert Decimal(agg["total_quantity"]) == Decimal("25.0")
    assert agg["status"] == UsageAggregateStatus.FINALIZED.value
    # rated_amount at 0.50 per unit = 25 * 0.50 = 12.50
    assert agg["rated_amount"] == "12.50"

    # 7. Verify cycle is frozen
    db.refresh(cycle)
    assert cycle.status == BillingCycleStatus.FINALIZED

    # 8. Attempting to ingest new event into finalized cycle must be rejected
    rejected_resp = client.post(
        "/api/v1/meters/events",
        json={
            "meter_code": "compute_hours",
            "customer_id": customer.id,
            "subscription_id": sub_id,
            "quantity": 10.0,
            "timestamp": "2026-06-15T12:00:00Z",
            "idempotency_key": "evt-job-frozen-attempt",
        },
        headers=auth_headers,
    )
    assert rejected_resp.status_code == 409
    assert "already been finalized" in rejected_resp.text

    # 9. Verify metered SubscriptionItem was linked
    from backend.app.models.billing_cycles import SubscriptionItem, SubscriptionItemType
    metered_item = db.query(SubscriptionItem).filter(
        SubscriptionItem.subscription_id == sub_id,
        SubscriptionItem.item_type == SubscriptionItemType.METERED,
    ).first()
    assert metered_item is not None
    assert Decimal(str(metered_item.quantity)) == Decimal("25.0")

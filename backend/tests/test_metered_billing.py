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
    aggs = finalize_resp.json()
    assert len(aggs) == 1
    agg = aggs[0]
    assert Decimal(agg["total_quantity"]) == Decimal("25.0")
    assert agg["status"] == UsageAggregateStatus.FINALIZED.value
    # rated at the plan's real contracted price (500.00/unit), not a hard-coded rate
    assert Decimal(agg["rated_amount"]) == Decimal("25.0") * Decimal("500.00")

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


def _make_meter(client, auth_headers, code, name, unit_name):
    resp = client.post(
        "/api/v1/meters",
        json={"code": code, "name": name, "unit_name": unit_name, "aggregation_type": "sum"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _open_cycle(db, tenant, sub_id):
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
    return cycle


def _subscription(client, auth_headers, customer, plan):
    resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1},
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_finalize_usage_rates_at_the_plan_price_not_a_hardcoded_rate(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="12.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_units", "API Units", "unit")

    client.post(
        "/api/v1/meters/events",
        json={
            "meter_code": "api_units",
            "customer_id": customer.id,
            "subscription_id": sub_id,
            "quantity": 10,
            "idempotency_key": "price-evt-1",
        },
        headers=auth_headers,
    )
    cycle = _open_cycle(db, tenant, sub_id)

    resp = client.post(
        f"/api/v1/meters/subscriptions/{sub_id}/billing-cycles/{cycle.id}/finalize-usage",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    aggs = resp.json()
    assert len(aggs) == 1
    # 10 units * 12.00 (plan price) = 120.00, NOT 10 * 0.50 = 5.00
    assert Decimal(aggs[0]["rated_amount"]) == Decimal("120.00")


def test_finalize_usage_uses_subscription_price_override_and_explicit_override(client, tenant, auth_headers, db):
    from backend.app.models.subscriptions import Subscription
    from backend.app.services import meter_service

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="12.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    sub.unit_price = Decimal("7.50")
    db.commit()

    _make_meter(client, auth_headers, "api_units", "API Units", "unit")
    client.post(
        "/api/v1/meters/events",
        json={
            "meter_code": "api_units",
            "customer_id": customer.id,
            "subscription_id": sub_id,
            "quantity": 4,
            "idempotency_key": "override-evt-1",
        },
        headers=auth_headers,
    )
    cycle = _open_cycle(db, tenant, sub_id)

    resp = client.post(
        f"/api/v1/meters/subscriptions/{sub_id}/billing-cycles/{cycle.id}/finalize-usage",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    # subscription override wins over the plan's list price: 4 * 7.50
    assert Decimal(resp.json()[0]["rated_amount"]) == Decimal("30.00")

    # An explicit caller-supplied price still overrides everything.
    class _Ctx:
        organization_id = tenant.organization.id
        user_id = tenant.owner.id

    aggs = meter_service.finalize_usage_for_cycle(
        db,
        ctx=_Ctx(),
        subscription_id=sub_id,
        billing_cycle_id=cycle.id,
        unit_price=Decimal("2.00"),
    )
    assert Decimal(str(aggs[0].rated_amount)) == Decimal("8.00")


def test_finalize_usage_rates_every_meter_with_usage(client, tenant, auth_headers, db):
    """All meters with usage are rated, not just the first one alphabetically."""
    from backend.app.models.invoices import Invoice, InvoiceItem

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="2.00")
    sub_id = _subscription(client, auth_headers, customer, plan)

    _make_meter(client, auth_headers, "aaa_storage", "AAA Storage", "gb")
    _make_meter(client, auth_headers, "zzz_bandwidth", "ZZZ Bandwidth", "gb")

    for code, qty, key in (("aaa_storage", 10, "m-1"), ("zzz_bandwidth", 30, "m-2")):
        r = client.post(
            "/api/v1/meters/events",
            json={
                "meter_code": code,
                "customer_id": customer.id,
                "subscription_id": sub_id,
                "quantity": qty,
                "idempotency_key": key,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text

    cycle = _open_cycle(db, tenant, sub_id)
    resp = client.post(
        f"/api/v1/meters/subscriptions/{sub_id}/billing-cycles/{cycle.id}/finalize-usage",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    aggs = resp.json()
    assert len(aggs) == 2
    by_amount = sorted(Decimal(a["rated_amount"]) for a in aggs)
    assert by_amount == [Decimal("20.00"), Decimal("60.00")]

    # One invoice line per meter, naming the meter and the quantity/unit.
    usage_invoice_ids = {a["invoice_id"] for a in aggs}
    assert len(usage_invoice_ids) == 1 and None not in usage_invoice_ids
    invoice = db.query(Invoice).filter(Invoice.id == usage_invoice_ids.pop()).first()
    assert invoice is not None
    items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice.id).all()
    assert len(items) == 2
    descriptions = sorted(i.description for i in items)
    assert "AAA Storage" in descriptions[0] and "gb" in descriptions[0]
    assert "ZZZ Bandwidth" in descriptions[1] and "gb" in descriptions[1]
    assert Decimal(str(invoice.total)) == Decimal("80.00")


def test_finalize_usage_without_resolvable_price_is_rejected(client, tenant, auth_headers, db):
    from backend.app.models.catalog import Plan
    from backend.app.models.subscriptions import Subscription

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="10.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_units", "API Units", "unit")
    client.post(
        "/api/v1/meters/events",
        json={
            "meter_code": "api_units",
            "customer_id": customer.id,
            "subscription_id": sub_id,
            "quantity": 3,
            "idempotency_key": "nop-evt-1",
        },
        headers=auth_headers,
    )
    cycle = _open_cycle(db, tenant, sub_id)

    # Zero out both the subscription override and the plan's list price.
    db.query(Subscription).filter(Subscription.id == sub_id).first().unit_price = Decimal("0")
    db.query(Plan).filter(Plan.id == plan.id).first().unit_amount = Decimal("0")
    db.commit()

    resp = client.post(
        f"/api/v1/meters/subscriptions/{sub_id}/billing-cycles/{cycle.id}/finalize-usage",
        headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "unit price" in resp.text

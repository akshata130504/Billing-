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
            "unit_price": "500.00",
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
    # rated at the meter's own per-unit price (500.00/unit)
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


def _make_meter(client, auth_headers, code, name, unit_name, unit_price=None):
    body = {"code": code, "name": name, "unit_name": unit_name, "aggregation_type": "sum"}
    if unit_price is not None:
        body["unit_price"] = unit_price
    resp = client.post(
        "/api/v1/meters",
        json=body,
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
    plan_id = plan.id if hasattr(plan, "id") else plan["id"]
    resp = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan_id, "quantity": 1},
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_finalize_usage_rates_at_the_meter_price_not_the_plan_price(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="999.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_units", "API Units", "unit", unit_price="12.00")

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
    # 10 units * 12.00 (meter price) = 120.00 - the plan's recurring price is irrelevant
    assert Decimal(aggs[0]["rated_amount"]) == Decimal("120.00")


def test_finalize_usage_uses_meter_price_and_explicit_override(client, tenant, auth_headers, db):
    from backend.app.services import meter_service

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="12.00")
    sub_id = _subscription(client, auth_headers, customer, plan)

    _make_meter(client, auth_headers, "api_units", "API Units", "unit", unit_price="7.50")
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
    # the meter's price applies: 4 * 7.50
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

    _make_meter(client, auth_headers, "aaa_storage", "AAA Storage", "gb", unit_price="2.00")
    _make_meter(client, auth_headers, "zzz_bandwidth", "ZZZ Bandwidth", "gb", unit_price="2.00")

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
    assert Decimal(str(invoice.subtotal)) == Decimal("80.00")
    # Usage invoices are real tax invoices (plan product's tax rate).
    assert Decimal(str(invoice.total)) == Decimal(str(invoice.subtotal)) + Decimal(str(invoice.tax_amount))
    assert Decimal(str(invoice.tax_amount)) > 0


def test_finalize_usage_with_unpriced_meter_rates_zero_and_raises_no_invoice(client, tenant, auth_headers, db):
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

    resp = client.post(
        f"/api/v1/meters/subscriptions/{sub_id}/billing-cycles/{cycle.id}/finalize-usage",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    agg = resp.json()[0]
    # The meter has no price: usage is recorded but rated at 0 (never at the plan price).
    assert Decimal(agg["total_quantity"]) == Decimal("3")
    assert Decimal(agg["rated_amount"]) == Decimal("0.00")
    assert agg["invoice_id"] is None


# ---------------------------------------------------------------------------
# Regression: generate_period_invoice must never re-bill a METERED item on a
# regular renewal invoice - it's already billed on its own separate usage
# invoice by finalize_usage_for_cycle. See subscription_service.py's
# active_items filter.
# ---------------------------------------------------------------------------

def _flat_product_and_plan(client, auth_headers, unit_amount="5.00"):
    """A FLAT-pricing plan, matching the real-world setup that reproduced the bug
    (tenant.product_with_plan defaults to PER_UNIT, which doesn't exercise the
    same fallback path)."""
    prod_resp = client.post(
        "/api/v1/products",
        json={"name": "Metered Regression Product", "sku": f"MRP-{Decimal(unit_amount)}", "type": "subscription", "tax_rate_pct": "0"},
        headers=auth_headers,
    )
    assert prod_resp.status_code == 201, prod_resp.text
    product_id = prod_resp.json()["id"]

    plan_resp = client.post(
        "/api/v1/plans",
        json={
            "product_id": product_id,
            "name": "Metered Regression Plan",
            "code": f"MRP-M-{unit_amount}",
            "billing_interval": "monthly",
            "interval_count": 1,
            "pricing_model": "flat",
            "unit_amount": unit_amount,
            "currency": "INR",
        },
        headers=auth_headers,
    )
    assert plan_resp.status_code == 201, plan_resp.text
    return plan_resp.json()


def _current_cycle(db, sub_id):
    from backend.app.models.subscriptions import Subscription

    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    return db.query(BillingCycle).filter(
        BillingCycle.subscription_id == sub_id,
        BillingCycle.period_start == sub.current_period_start,
    ).first()


def test_metered_finalization_creates_correct_draft_usage_invoice(client, tenant, auth_headers, db):
    """(1) Usage finalization itself: quantity, rated amount, and the separate
    usage invoice are all correct and untouched by the renewal-side fix."""
    from backend.app.models.invoices import Invoice, InvoiceStatus

    customer = tenant.customer()
    plan = _flat_product_and_plan(client, auth_headers, unit_amount="5.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_calls", "API Calls", "call", unit_price="5.00")

    for qty, key in ((200, "reg-evt-1"), (150, "reg-evt-2"), (150, "reg-evt-3")):
        r = client.post(
            "/api/v1/meters/events",
            json={
                "meter_code": "api_calls",
                "customer_id": customer.id,
                "subscription_id": sub_id,
                "quantity": qty,
                "idempotency_key": key,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text

    cycle = _current_cycle(db, sub_id)
    assert cycle is not None

    resp = client.post(
        f"/api/v1/meters/subscriptions/{sub_id}/billing-cycles/{cycle.id}/finalize-usage",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    agg = resp.json()[0]
    assert Decimal(agg["total_quantity"]) == Decimal("500")
    assert Decimal(agg["rated_amount"]) == Decimal("2500.00")
    assert agg["invoice_id"] is not None

    usage_invoice = db.query(Invoice).filter(Invoice.id == agg["invoice_id"]).first()
    assert usage_invoice is not None
    assert usage_invoice.status == InvoiceStatus.DRAFT
    assert Decimal(str(usage_invoice.subtotal)) == Decimal("2500.00")


def test_renewal_after_usage_finalization_excludes_metered_item(client, tenant, auth_headers, db):
    """(2) The regular renewal invoice must contain only the PLAN line - no
    phantom METERED duplicate - after usage has been finalized for the period."""
    from backend.app.services.subscription_service import renew_subscription
    from backend.app.models.subscriptions import Subscription
    from backend.app.models.invoices import Invoice

    customer = tenant.customer()
    plan = _flat_product_and_plan(client, auth_headers, unit_amount="5.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_calls", "API Calls", "call")

    client.post(
        "/api/v1/meters/events",
        json={
            "meter_code": "api_calls",
            "customer_id": customer.id,
            "subscription_id": sub_id,
            "quantity": 500,
            "idempotency_key": "renewal-evt-1",
        },
        headers=auth_headers,
    )
    cycle = _current_cycle(db, sub_id)
    finalize_resp = client.post(
        f"/api/v1/meters/subscriptions/{sub_id}/billing-cycles/{cycle.id}/finalize-usage",
        headers=auth_headers,
    )
    assert finalize_resp.status_code == 200, finalize_resp.text

    invoices_before = db.query(Invoice).filter(Invoice.subscription_id == sub_id).count()

    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    outcome = renew_subscription(db, sub)
    assert outcome == "renewed"
    db.commit()

    invoices_after = db.query(Invoice).filter(Invoice.subscription_id == sub_id).count()
    assert invoices_after == invoices_before + 1

    renewal_invoice = (
        db.query(Invoice)
        .filter(Invoice.subscription_id == sub_id)
        .order_by(Invoice.created_at.desc())
        .first()
    )
    assert len(renewal_invoice.items) == 1
    item = renewal_invoice.items[0]
    assert Decimal(str(item.quantity)) == Decimal("1")
    assert Decimal(str(item.amount)) == Decimal("5.00")
    assert Decimal(str(renewal_invoice.total)) == Decimal("5.00")


def test_second_renewal_with_no_new_usage_still_excludes_metered_item(client, tenant, auth_headers, db):
    """(3) A second renewal, with no new usage recorded, must not resurrect the
    stale METERED item either - it's excluded unconditionally, not just once."""
    from backend.app.services.subscription_service import renew_subscription
    from backend.app.models.subscriptions import Subscription
    from backend.app.models.invoices import Invoice

    customer = tenant.customer()
    plan = _flat_product_and_plan(client, auth_headers, unit_amount="5.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_calls", "API Calls", "call")

    client.post(
        "/api/v1/meters/events",
        json={
            "meter_code": "api_calls",
            "customer_id": customer.id,
            "subscription_id": sub_id,
            "quantity": 500,
            "idempotency_key": "second-renewal-evt-1",
        },
        headers=auth_headers,
    )
    cycle = _current_cycle(db, sub_id)
    client.post(
        f"/api/v1/meters/subscriptions/{sub_id}/billing-cycles/{cycle.id}/finalize-usage",
        headers=auth_headers,
    )

    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    assert renew_subscription(db, sub) == "renewed"
    db.commit()

    # Second renewal, no new usage events recorded in between.
    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    assert renew_subscription(db, sub) == "renewed"
    db.commit()

    renewal_invoice = (
        db.query(Invoice)
        .filter(Invoice.subscription_id == sub_id)
        .order_by(Invoice.created_at.desc())
        .first()
    )
    assert len(renewal_invoice.items) == 1
    assert Decimal(str(renewal_invoice.items[0].quantity)) == Decimal("1")
    assert Decimal(str(renewal_invoice.total)) == Decimal("5.00")


def test_non_metered_subscription_renewal_unchanged(client, tenant, auth_headers, db):
    """(4) A subscription with no meters/usage at all renews exactly as before -
    zero behavior change for the common, non-metered case."""
    from backend.app.services.subscription_service import renew_subscription
    from backend.app.models.subscriptions import Subscription
    from backend.app.models.invoices import Invoice

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    sub_id = _subscription(client, auth_headers, customer, plan)

    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    assert renew_subscription(db, sub) == "renewed"
    db.commit()

    renewal_invoice = (
        db.query(Invoice)
        .filter(Invoice.subscription_id == sub_id)
        .order_by(Invoice.created_at.desc())
        .first()
    )
    assert len(renewal_invoice.items) == 1
    # tenant.product_with_plan's product carries an 18% tax rate: 1000 * 1.18
    assert Decimal(str(renewal_invoice.total)) == Decimal("1180.00")


def test_plan_and_addon_items_still_appear_after_metered_filter(client, tenant, auth_headers, db):
    """(5) PLAN and ADDON items are untouched by the METERED exclusion - both
    still appear on the renewal invoice."""
    from backend.app.services.subscription_service import renew_subscription
    from backend.app.models.subscriptions import Subscription
    from backend.app.models.invoices import Invoice
    from backend.app.models.billing_cycles import SubscriptionItem, SubscriptionItemType, SubscriptionItemStatus

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    sub_id = _subscription(client, auth_headers, customer, plan)

    db.add(
        SubscriptionItem(
            organization_id=tenant.organization.id,
            subscription_id=sub_id,
            item_type=SubscriptionItemType.ADDON,
            quantity=Decimal("2"),
            unit_price=Decimal("50.00"),
            status=SubscriptionItemStatus.ACTIVE,
        )
    )
    db.commit()

    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    assert renew_subscription(db, sub) == "renewed"
    db.commit()

    renewal_invoice = (
        db.query(Invoice)
        .filter(Invoice.subscription_id == sub_id)
        .order_by(Invoice.created_at.desc())
        .first()
    )
    assert len(renewal_invoice.items) == 2
    amounts = sorted(Decimal(str(i.amount)) for i in renewal_invoice.items)
    assert amounts == [Decimal("100.00"), Decimal("1000.00")]


def test_usage_event_idempotency_unaffected_by_renewal_fix(client, tenant, auth_headers):
    """(6) Usage-event idempotency is untouched by the renewal-side filter change."""
    customer = tenant.customer()
    plan = _flat_product_and_plan(client, auth_headers, unit_amount="5.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_calls", "API Calls", "call")

    first = client.post(
        "/api/v1/meters/events",
        json={
            "meter_code": "api_calls",
            "customer_id": customer.id,
            "subscription_id": sub_id,
            "quantity": 200,
            "idempotency_key": "idem-check-1",
        },
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text

    duplicate = client.post(
        "/api/v1/meters/events",
        json={
            "meter_code": "api_calls",
            "customer_id": customer.id,
            "subscription_id": sub_id,
            "quantity": 999999,
            "idempotency_key": "idem-check-1",
        },
        headers=auth_headers,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == first.json()["id"]
    assert duplicate.json()["quantity"] == first.json()["quantity"] == "200.0000"


# --- production-readiness regressions ---------------------------------------------------------


def _event(code, customer_id, sub_id, qty, key, ts=None):
    body = {"meter_code": code, "customer_id": customer_id, "subscription_id": sub_id, "quantity": qty, "idempotency_key": key}
    if ts is not None:
        body["timestamp"] = ts
    return body


def test_viewer_cannot_ingest_usage(client, tenant, auth_headers):
    from backend.app.models import MemberRole

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="10.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_units", "API Units", "unit", unit_price="1.00")
    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    resp = client.post("/api/v1/meters/events", json=_event("api_units", customer.id, sub_id, 1, "v-1"), headers=viewer)
    assert resp.status_code == 403


def test_usage_rejected_for_other_customers_subscription(client, tenant, auth_headers):
    customer = tenant.customer()
    other = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="10.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_units", "API Units", "unit", unit_price="1.00")
    resp = client.post("/api/v1/meters/events", json=_event("api_units", other.id, sub_id, 1, "x-1"), headers=auth_headers)
    assert resp.status_code == 422
    resp = client.post(
        "/api/v1/meters/events", json=_event("api_units", customer.id, "no-such-sub", 1, "x-2"), headers=auth_headers
    )
    assert resp.status_code == 404


def test_batch_ingestion_is_atomic(client, tenant, auth_headers, db):
    from backend.app.models.meters import UsageEvent

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="10.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_units", "API Units", "unit", unit_price="1.00")
    resp = client.post(
        "/api/v1/meters/events/batch",
        json={"events": [_event("api_units", customer.id, sub_id, 1, "b-1"), _event("missing_meter", customer.id, sub_id, 1, "b-2")]},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert db.query(UsageEvent).filter(UsageEvent.idempotency_key == "b-1", UsageEvent.subscription_id == sub_id).count() == 0


def test_duplicate_meter_code_is_case_insensitive(client, tenant, auth_headers):
    _make_meter(client, auth_headers, "api_calls", "API Calls", "call")
    resp = client.post(
        "/api/v1/meters",
        json={"code": "API_Calls", "name": "Dup", "unit_name": "call", "aggregation_type": "sum"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_finalize_rejects_cycle_of_another_subscription(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="10.00")
    _, plan2 = tenant.product_with_plan(unit_amount="10.00")
    sub_a = _subscription(client, auth_headers, customer, plan)
    sub_b = _subscription(client, auth_headers, customer, plan2)
    _make_meter(client, auth_headers, "api_units", "API Units", "unit", unit_price="1.00")
    cycle_b = _open_cycle(db, tenant, sub_b)
    resp = client.post(
        f"/api/v1/meters/subscriptions/{sub_a}/billing-cycles/{cycle_b.id}/finalize-usage", headers=auth_headers
    )
    assert resp.status_code == 422


def test_billing_cycle_listing_and_half_open_window(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="10.00")
    sub_id = _subscription(client, auth_headers, customer, plan)
    _make_meter(client, auth_headers, "api_units", "API Units", "unit", unit_price="1.00")

    cycles = client.get(f"/api/v1/meters/billing-cycles?subscription_id={sub_id}", headers=auth_headers)
    assert cycles.status_code == 200, cycles.text
    assert len(cycles.json()) >= 1 and cycles.json()[0]["subscription_id"] == sub_id

    cycle = _open_cycle(db, tenant, sub_id)  # 2026-01-01 .. 2026-12-31
    inside = "2026-12-30T12:00:00+00:00"
    boundary = "2026-12-31T08:00:00+00:00"  # belongs to the NEXT period
    for ts, key in ((inside, "hw-1"), (boundary, "hw-2")):
        r = client.post("/api/v1/meters/events", json=_event("api_units", customer.id, sub_id, 5, key, ts), headers=auth_headers)
        assert r.status_code == 201, r.text
    resp = client.post(
        f"/api/v1/meters/subscriptions/{sub_id}/billing-cycles/{cycle.id}/finalize-usage", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()[0]["total_quantity"]) == Decimal("5")


def test_meter_price_can_be_updated(client, tenant, auth_headers):
    meter = _make_meter(client, auth_headers, "gb_stored", "GB Stored", "gb")
    assert meter["unit_price"] is None
    resp = client.patch(f"/api/v1/meters/{meter['id']}", json={"unit_price": "0.2500"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert Decimal(str(resp.json()["unit_price"])) == Decimal("0.25")

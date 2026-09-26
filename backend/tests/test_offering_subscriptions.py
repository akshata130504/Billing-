"""Plans & Pricing (catalog offerings) are subscribable, through a linked legacy plan.

Covers: subscribe to flat / per-unit / volume / tiered offerings (engine pricing, GST,
currency, interval), price books, renewal, plan changes between legacy and offering
plans, inactive / one-time / cross-tenant offerings rejected, no duplicate linked plans,
and legacy regression.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from backend.app.models import Invoice, InvoiceStatus, MemberRole, Plan, Product
from backend.app.models.billing_cycles import PriceSnapshot, SubscriptionItem, SubscriptionItemType
from backend.app.models.subscriptions import Subscription
from backend.app.services import subscription_service
from backend.tests.conftest import Tenant

OFFERINGS = "/api/v1/catalog/offerings"
PRICE_BOOKS = "/api/v1/catalog/price-books"
SUBS = "/api/v1/subscriptions"


def _offering(client, headers, **overrides):
    data = {
        "name": f"Plan {uuid.uuid4().hex[:6]}",
        "sku": f"PP-{uuid.uuid4().hex[:8].upper()}",
        "type": "plan",
        "category": "Subscriptions",
        "unit": "seat",
        "currency": "INR",
        "pricing_model": "per_unit",
        "base_price": "500.00",
        "tax_rate_pct": "18.00",
        "billing_frequency": "monthly",
        "is_active": True,
    }
    data.update(overrides)
    res = client.post(OFFERINGS, json=data, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _subscribe(client, headers, customer_id, **body):
    payload = {"customer_id": customer_id, "quantity": 1, **body}
    return client.post(SUBS, json=payload, headers=headers)


def _sub_invoices(db, sub_id):
    db.expire_all()
    return list(db.scalars(select(Invoice).where(Invoice.subscription_id == sub_id).order_by(Invoice.created_at)))


VOLUME_TIERS = [
    {"min_qty": 1, "max_qty": 10, "unit_price": 100},
    {"min_qty": 11, "max_qty": None, "unit_price": 80},
]
TIERED_TIERS = [
    {"min_qty": 0, "max_qty": 10, "unit_price": 100},
    {"min_qty": 11, "max_qty": None, "unit_price": 50},
]


def test_plan_options_list_both_sources(client, tenant, auth_headers):
    _, legacy = tenant.product_with_plan(unit_amount="999.00")
    recurring = _offering(client, auth_headers)
    one_time = _offering(client, auth_headers, billing_frequency="one_time")
    archived = _offering(client, auth_headers)
    assert client.delete(f"{OFFERINGS}/{archived['id']}", headers=auth_headers).status_code == 204

    res = client.get(f"{SUBS}/plan-options", headers=tenant.headers_for_role(MemberRole.VIEWER))
    assert res.status_code == 200, res.text
    by_id = {o["id"]: o for o in res.json()}
    assert by_id[legacy.id]["source"] == "plan"
    assert by_id[recurring["id"]]["source"] == "offering"
    assert by_id[recurring["id"]]["offering_id"] == recurring["id"]
    assert one_time["id"] not in by_id
    assert archived["id"] not in by_id


def test_subscribe_per_unit_offering_bills_engine_price_with_gst(client, tenant, auth_headers, db):
    customer = tenant.customer()
    offering = _offering(client, auth_headers, base_price="500.00", tax_rate_pct="18.00", billing_frequency="quarterly")
    res = _subscribe(client, auth_headers, customer.id, offering_id=offering["id"], quantity=3)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "active"
    assert body["plan"]["source"] == "offering"
    assert body["plan"]["offering_id"] == offering["id"]
    assert body["billing_frequency"] == "quarterly"
    assert body["currency"] == "INR"
    assert body["unit_price"] == "500.00"
    assert body["subtotal"] == "1500.00"
    assert body["tax_amount"] == "270.00"
    assert date.fromisoformat(body["current_period_end"]) == subscription_service.add_months(
        date.fromisoformat(body["current_period_start"]), 3
    )

    invoices = _sub_invoices(db, body["id"])
    assert len(invoices) == 1
    inv = invoices[0]
    assert inv.subtotal == Decimal("1500.00")
    assert inv.tax_amount == Decimal("270.00")
    assert inv.total == Decimal("1770.00")
    assert inv.items[0].offering_id == offering["id"]

    plan = db.get(Plan, body["plan"]["id"])
    assert plan.offering_id == offering["id"]
    assert plan.product.tax_rate_pct == Decimal("18.00")
    assert plan.product.offering_id == offering["id"]


def test_subscribe_flat_offering_ignores_quantity(client, tenant, auth_headers, db):
    customer = tenant.customer()
    offering = _offering(client, auth_headers, pricing_model="flat", base_price="2400.00", billing_frequency="yearly")
    res = _subscribe(client, auth_headers, customer.id, offering_id=offering["id"], quantity=5)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["subtotal"] == "2400.00"
    assert body["billing_frequency"] == "yearly"
    assert _sub_invoices(db, body["id"])[0].subtotal == Decimal("2400.00")


def test_subscribe_volume_offering_uses_pricing_engine(client, tenant, auth_headers, db):
    customer = tenant.customer()
    offering = _offering(client, auth_headers, pricing_model="volume", base_price="100.00", pricing_tiers=VOLUME_TIERS)
    res = _subscribe(client, auth_headers, customer.id, offering_id=offering["id"], quantity=12)
    assert res.status_code == 201, res.text
    body = res.json()
    # volume: all 12 units at the 11+ bracket price
    assert body["subtotal"] == "960.00"
    assert body["plan"]["offering_pricing_model"] == "volume"
    inv = _sub_invoices(db, body["id"])[0]
    assert inv.subtotal == Decimal("960.00")
    assert inv.tax_amount == Decimal("172.80")

    item = db.scalars(select(SubscriptionItem).where(SubscriptionItem.subscription_id == body["id"])).one()
    assert item.price_snapshot.metadata_["offering_pricing_model"] == "volume"
    assert item.price_snapshot.metadata_["quantity"] == 12


def test_subscribe_tiered_offering_and_quantity_change_reprices(client, tenant, auth_headers, db):
    customer = tenant.customer()
    offering = _offering(client, auth_headers, pricing_model="tiered", base_price="100.00", pricing_tiers=TIERED_TIERS)
    res = _subscribe(client, auth_headers, customer.id, offering_id=offering["id"], quantity=5)
    assert res.status_code == 201, res.text
    sub_id = res.json()["id"]
    assert res.json()["subtotal"] == "500.00"

    # 5 -> 15 seats: engine price for 15 = 10 x 100 + 5 x 50 = 1250 per period.
    change = client.post(
        f"{SUBS}/{sub_id}/changes", json={"target_quantity": "15", "effective_type": "immediate"}, headers=auth_headers
    )
    assert change.status_code == 201, change.text
    assert change.json()["new_plan_amount"] == "1250.00"
    sub = client.get(f"{SUBS}/{sub_id}", headers=auth_headers).json()
    assert sub["quantity"] == 15
    assert sub["subtotal"] == "1250.00"


def test_price_book_applies_to_offering_subscription(client, tenant, auth_headers):
    customer = tenant.customer()
    offering = _offering(client, auth_headers, base_price="1000.00")
    book = client.post(
        PRICE_BOOKS,
        json={
            "name": f"Partner {uuid.uuid4().hex[:6]}",
            "currency": "INR",
            "status": "active",
            "entries": [{"offering_id": offering["id"], "discount_pct": "10"}],
        },
        headers=auth_headers,
    )
    assert book.status_code == 201, book.text
    res = _subscribe(client, auth_headers, customer.id, offering_id=offering["id"], quantity=2, price_book_id=book.json()["id"])
    assert res.status_code == 201, res.text
    assert res.json()["unit_price"] == "900.00"
    assert res.json()["subtotal"] == "1800.00"


def test_linked_plan_is_reused_not_duplicated(client, tenant, auth_headers, db):
    offering = _offering(client, auth_headers)
    first = _subscribe(client, auth_headers, tenant.customer().id, offering_id=offering["id"])
    second = _subscribe(client, auth_headers, tenant.customer().id, offering_id=offering["id"])
    assert first.status_code == 201 and second.status_code == 201, (first.text, second.text)
    assert first.json()["plan"]["id"] == second.json()["plan"]["id"]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Plan).where(Plan.offering_id == offering["id"])) == 1
    assert db.scalar(select(func.count()).select_from(Product).where(Product.offering_id == offering["id"])) == 1
    # Linked plans/products stay out of the legacy catalog listings.
    plan_ids = {p["id"] for p in client.get("/api/v1/plans?page_size=100", headers=auth_headers).json()["items"]}
    assert first.json()["plan"]["id"] not in plan_ids
    # ...and cannot be edited behind the offering's back.
    patch = client.patch(f"/api/v1/plans/{first.json()['plan']['id']}", json={"unit_amount": "1.00"}, headers=auth_headers)
    assert patch.status_code == 409, patch.text


def test_inactive_one_time_and_bundle_offerings_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    archived = _offering(client, auth_headers)
    assert client.delete(f"{OFFERINGS}/{archived['id']}", headers=auth_headers).status_code == 204
    res = _subscribe(client, auth_headers, customer.id, offering_id=archived["id"])
    assert res.status_code == 422, res.text
    assert "inactive" in res.text

    one_time = _offering(client, auth_headers, billing_frequency="one_time")
    res = _subscribe(client, auth_headers, customer.id, offering_id=one_time["id"])
    assert res.status_code == 422, res.text

    both = _subscribe(client, auth_headers, customer.id, offering_id=one_time["id"], plan_id="x")
    assert both.status_code == 422


def test_archiving_offering_blocks_new_subscriptions_via_linked_plan(client, tenant, auth_headers, db):
    offering = _offering(client, auth_headers)
    first = _subscribe(client, auth_headers, tenant.customer().id, offering_id=offering["id"])
    assert first.status_code == 201, first.text
    linked_plan_id = first.json()["plan"]["id"]
    assert client.delete(f"{OFFERINGS}/{offering['id']}", headers=auth_headers).status_code == 204
    db.expire_all()
    assert db.get(Plan, linked_plan_id).is_active is False
    res = _subscribe(client, auth_headers, tenant.customer().id, plan_id=linked_plan_id)
    assert res.status_code == 422, res.text
    # The existing subscription keeps renewing on its frozen terms.
    sub = db.get(Subscription, first.json()["id"])
    sub.next_billing_date = date.today()
    db.commit()
    assert client.post(f"{SUBS}/{sub.id}/renew", headers=auth_headers).status_code == 200


def test_cross_tenant_offering_rejected(client, tenant, auth_headers, db):
    other = Tenant(db, uuid.uuid4().hex[:8])
    foreign = _offering(client, other.headers())
    customer = tenant.customer()
    res = _subscribe(client, auth_headers, customer.id, offering_id=foreign["id"])
    assert res.status_code == 404, res.text
    _, legacy = tenant.product_with_plan()
    sub_id = _subscribe(client, auth_headers, customer.id, plan_id=legacy.id).json()["id"]
    change = client.post(f"{SUBS}/{sub_id}/changes", json={"target_offering_id": foreign["id"]}, headers=auth_headers)
    assert change.status_code == 404, change.text
    # Nothing was linked into either tenant.
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Plan).where(Plan.offering_id == foreign["id"])) == 0
    # A foreign price book is not usable either.
    own = _offering(client, auth_headers)
    book = client.post(
        PRICE_BOOKS, json={"name": f"B {uuid.uuid4().hex[:6]}", "currency": "INR", "status": "active"}, headers=other.headers()
    ).json()
    res = _subscribe(client, auth_headers, customer.id, offering_id=own["id"], price_book_id=book["id"])
    assert res.status_code == 404, res.text


def test_offering_subscription_renews_at_contracted_price(client, tenant, auth_headers, db):
    customer = tenant.customer()
    offering = _offering(client, auth_headers, pricing_model="volume", base_price="100.00", pricing_tiers=VOLUME_TIERS)
    res = _subscribe(client, auth_headers, customer.id, offering_id=offering["id"], quantity=12)
    assert res.status_code == 201, res.text
    sub_id = res.json()["id"]
    # A later catalog price change must not touch the contracted renewal price.
    upd = client.patch(f"{OFFERINGS}/{offering['id']}", json={"pricing_tiers": [{"min_qty": 1, "unit_price": 1}]}, headers=auth_headers)
    assert upd.status_code == 200, upd.text

    sub = db.get(Subscription, sub_id)
    sub.next_billing_date = date.today()
    db.commit()
    renew = client.post(f"{SUBS}/{sub_id}/renew", headers=auth_headers)
    assert renew.status_code == 200, renew.text
    invoices = _sub_invoices(db, sub_id)
    assert len(invoices) == 2
    assert invoices[-1].subtotal == Decimal("960.00")
    assert invoices[-1].total == Decimal("1132.80")


def test_change_between_legacy_and_offering_plans(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, legacy = tenant.product_with_plan(unit_amount="1000.00")
    offering = _offering(client, auth_headers, base_price="1500.00")
    res = _subscribe(client, auth_headers, customer.id, plan_id=legacy.id, quantity=2)
    assert res.status_code == 201, res.text
    sub_id = res.json()["id"]

    preview = client.post(
        f"{SUBS}/{sub_id}/changes/preview", json={"target_offering_id": offering["id"]}, headers=auth_headers
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["change_type"] == "upgrade"

    up = client.post(
        f"{SUBS}/{sub_id}/changes", json={"target_offering_id": offering["id"], "effective_type": "immediate"}, headers=auth_headers
    )
    assert up.status_code == 201, up.text
    assert up.json()["change_type"] == "upgrade"
    body = client.get(f"{SUBS}/{sub_id}", headers=auth_headers).json()
    assert body["plan"]["source"] == "offering"
    assert body["unit_price"] == "1500.00"
    assert body["subtotal"] == "3000.00"

    down = client.post(
        f"{SUBS}/{sub_id}/changes", json={"target_plan_id": legacy.id, "effective_type": "immediate"}, headers=auth_headers
    )
    assert down.status_code == 201, down.text
    assert down.json()["change_type"] == "downgrade"
    body = client.get(f"{SUBS}/{sub_id}", headers=auth_headers).json()
    assert body["plan"]["source"] == "plan"
    assert body["plan"]["id"] == legacy.id
    assert body["unit_price"] == "1000.00"

    # Renewal after the round trip bills the legacy plan price.
    sub = db.get(Subscription, sub_id)
    db.refresh(sub)
    sub.next_billing_date = date.today()
    db.commit()
    assert client.post(f"{SUBS}/{sub_id}/renew", headers=auth_headers).status_code == 200
    last = _sub_invoices(db, sub_id)[-1]
    assert last.period_start is not None
    assert last.subtotal == Decimal("2000.00")


def test_change_to_inactive_offering_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    _, legacy = tenant.product_with_plan(unit_amount="1000.00")
    offering = _offering(client, auth_headers)
    assert client.delete(f"{OFFERINGS}/{offering['id']}", headers=auth_headers).status_code == 204
    sub_id = _subscribe(client, auth_headers, customer.id, plan_id=legacy.id).json()["id"]
    res = client.post(f"{SUBS}/{sub_id}/changes", json={"target_offering_id": offering["id"]}, headers=auth_headers)
    assert res.status_code == 422, res.text


def test_legacy_subscription_unchanged(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    res = _subscribe(client, auth_headers, customer.id, plan_id=plan.id, quantity=2)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["plan"]["source"] == "plan"
    assert body["plan"]["offering_id"] is None
    assert body["subtotal"] == "2000.00"
    assert body["tax_amount"] == "360.00"
    item = db.scalars(select(SubscriptionItem).where(SubscriptionItem.subscription_id == body["id"])).one()
    assert item.item_type == SubscriptionItemType.PLAN
    assert item.price_snapshot.metadata_ is None
    assert item.price_snapshot.unit_amount == Decimal("1000.00")
    assert _sub_invoices(db, body["id"])[0].total == Decimal("2360.00")

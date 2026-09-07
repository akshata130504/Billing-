"""Products and plans API tests."""
import uuid
from datetime import date, timedelta

from backend.app.models import AuditLog, MemberRole, Quote, QuoteItem, Subscription, SubscriptionStatus

PRODUCTS = "/api/v1/products"
PLANS = "/api/v1/plans"


def _product(**overrides):
    data = {"name": "Cloud Hosting", "sku": f"HOST-{uuid.uuid4().hex[:6]}", "type": "subscription", "tax_rate_pct": "18"}
    data.update(overrides)
    return data


def test_create_product_and_plan(client, auth_headers, db):
    resp = client.post(PRODUCTS, json=_product(), headers=auth_headers)
    assert resp.status_code == 201, resp.text
    product = resp.json()
    assert product["type"] == "subscription"
    assert product["tax_rate_pct"] == "18.00"
    assert product["plans"] == []
    assert product["is_active"] is True

    resp = client.post(
        PLANS,
        json={
            "product_id": product["id"],
            "name": "Starter",
            "code": f"STARTER-{uuid.uuid4().hex[:4]}",
            "billing_interval": "monthly",
            "pricing_model": "per_unit",
            "unit_amount": "999.50",
            "trial_days": 14,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    plan = resp.json()
    assert plan["unit_amount"] == "999.50"
    assert plan["setup_fee"] == "0.00"
    assert plan["currency"] == "INR"
    assert plan["interval_count"] == 1
    assert plan["active_subscriptions"] == 0

    detail = client.get(f"{PRODUCTS}/{product['id']}", headers=auth_headers).json()
    assert [p["id"] for p in detail["plans"]] == [plan["id"]]

    assert db.query(AuditLog).filter_by(entity_id=product["id"], action="PRODUCT_CREATED").count() == 1
    assert db.query(AuditLog).filter_by(entity_id=plan["id"], action="PLAN_CREATED").count() == 1


def test_product_sku_generated_when_missing_and_duplicate_rejected(client, auth_headers):
    resp = client.post(PRODUCTS, json={"name": "No SKU"}, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["sku"].startswith("SKU-")
    sku = f"DUP-{uuid.uuid4().hex[:5]}"
    assert client.post(PRODUCTS, json=_product(sku=sku), headers=auth_headers).status_code == 201
    resp = client.post(PRODUCTS, json=_product(sku=sku.lower()), headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


def test_plan_code_unique_and_product_must_exist(client, auth_headers, tenant):
    product, plan = tenant.product_with_plan()
    body = {
        "product_id": product.id,
        "name": "Dup",
        "code": plan.code,
        "billing_interval": "yearly",
        "pricing_model": "flat",
        "unit_amount": "10",
    }
    assert client.post(PLANS, json=body, headers=auth_headers).status_code == 409
    body.update(code="X-" + uuid.uuid4().hex[:5], product_id=str(uuid.uuid4()))
    assert client.post(PLANS, json=body, headers=auth_headers).status_code == 404
    body.update(billing_interval="weekly", product_id=product.id)
    assert client.post(PLANS, json=body, headers=auth_headers).status_code == 422


def test_list_products_filters_and_active_subscription_counts(client, tenant, auth_headers, db):
    product, plan = tenant.product_with_plan()
    other, _ = tenant.product_with_plan()
    customer = tenant.customer()
    today = date.today()
    for status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.CANCELLED):
        db.add(
            Subscription(
                organization_id=tenant.organization.id,
                subscription_number=f"SUB-{uuid.uuid4().hex[:6]}",
                customer_id=customer.id,
                plan_id=plan.id,
                status=status,
                start_date=today,
                current_period_start=today,
                current_period_end=today + timedelta(days=30),
            )
        )
    db.commit()

    resp = client.get(PRODUCTS, headers=auth_headers, params={"search": product.sku})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["plans"][0]["active_subscriptions"] == 2

    resp = client.get(PLANS, headers=auth_headers, params={"product_id": other.id})
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["active_subscriptions"] == 0

    resp = client.get(PLANS, headers=auth_headers, params={"billing_interval": "yearly"})
    assert resp.json()["total"] == 0

    resp = client.get(PRODUCTS, headers=auth_headers, params={"is_active": "false"})
    assert resp.json()["total"] == 0


def test_update_product_and_plan(client, tenant, auth_headers, db):
    product, plan = tenant.product_with_plan()
    resp = client.patch(f"{PRODUCTS}/{product.id}", json={"name": "Renamed", "is_active": False}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Renamed"
    assert resp.json()["is_active"] is False
    resp = client.patch(f"{PLANS}/{plan.id}", json={"unit_amount": "1234.5", "trial_days": 7}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["unit_amount"] == "1234.50"
    assert resp.json()["trial_days"] == 7
    log = db.query(AuditLog).filter_by(entity_id=plan.id, action="PLAN_UPDATED").one()
    assert log.before_state["unit_amount"] != log.after_state["unit_amount"]


def test_delete_guards(client, tenant, db):
    admin = tenant.headers_for_role(MemberRole.ADMIN)
    finance = tenant.headers_for_role(MemberRole.FINANCE)
    product, plan = tenant.product_with_plan()
    customer = tenant.customer()
    today = date.today()
    db.add(
        Subscription(
            organization_id=tenant.organization.id,
            subscription_number=f"SUB-{uuid.uuid4().hex[:6]}",
            customer_id=customer.id,
            plan_id=plan.id,
            status=SubscriptionStatus.CANCELLED,
            start_date=today,
            current_period_start=today,
            current_period_end=today + timedelta(days=30),
        )
    )
    db.commit()

    assert client.delete(f"{PLANS}/{plan.id}", headers=finance).status_code == 403
    resp = client.delete(f"{PLANS}/{plan.id}", headers=admin)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "INVALID_STATE"
    resp = client.delete(f"{PRODUCTS}/{product.id}", headers=admin)
    assert resp.status_code == 409

    # product referenced only by a quote item
    quoted, _ = tenant.product_with_plan()
    quote = Quote(
        organization_id=tenant.organization.id,
        quote_number=f"QT-{uuid.uuid4().hex[:6]}",
        customer_id=customer.id,
        issue_date=today,
    )
    db.add(quote)
    db.flush()
    db.add(
        QuoteItem(
            organization_id=tenant.organization.id,
            quote_id=quote.id,
            product_id=quoted.id,
            description="x",
            quantity=1,
            unit_price=10,
            amount=10,
        )
    )
    db.commit()
    assert client.delete(f"{PRODUCTS}/{quoted.id}", headers=admin).status_code == 409

    # free product / plan can be deleted
    free_product, free_plan = tenant.product_with_plan()
    assert client.delete(f"{PLANS}/{free_plan.id}", headers=admin).status_code == 204
    assert client.delete(f"{PRODUCTS}/{free_product.id}", headers=admin).status_code == 204
    assert client.get(f"{PRODUCTS}/{free_product.id}", headers=admin).status_code == 404
    assert db.query(AuditLog).filter_by(entity_id=free_product.id, action="PRODUCT_DELETED").count() == 1
    assert db.query(AuditLog).filter_by(entity_id=free_plan.id, action="PLAN_DELETED").count() == 1


def test_catalog_tenant_isolation(client, tenant, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    product, plan = other.product_with_plan()
    headers = tenant.headers()
    assert client.get(f"{PRODUCTS}/{product.id}", headers=headers).status_code == 404
    assert client.get(f"{PLANS}/{plan.id}", headers=headers).status_code == 404
    assert client.get(PRODUCTS, headers=headers).json()["total"] == 0

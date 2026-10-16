"""Subscription creation cannot be duplicated by retries or by a past-due sibling.

QA (new-bugs PDF, "Subscriptions List"): the same customer ended up subscribed to the same plan
several times. A retried POST (double click, 401-refresh replay) and a past-due subscription to the
same plan were the two remaining ways in.
"""
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.models import Subscription, SubscriptionStatus

API = "/api/v1/subscriptions"


def _count(db, customer_id):
    db.expire_all()
    return db.scalar(select(func.count(Subscription.id)).where(Subscription.customer_id == customer_id))


def test_same_idempotency_key_returns_the_original_subscription(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="500.00")
    body = {"customer_id": customer.id, "plan_id": plan.id, "quantity": 1}
    headers = {**auth_headers, "Idempotency-Key": "sub-create-retry-1"}

    first = client.post(API, headers=headers, json=body)
    again = client.post(API, headers=headers, json=body)

    assert first.status_code == 201, first.text
    assert again.status_code == 201, again.text
    assert again.json()["id"] == first.json()["id"]
    assert _count(db, customer.id) == 1


def test_idempotency_key_reused_with_a_different_body_is_rejected(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="500.00")
    headers = {**auth_headers, "Idempotency-Key": "sub-create-retry-2"}

    assert client.post(API, headers=headers, json={"customer_id": customer.id, "plan_id": plan.id}).status_code == 201
    res = client.post(API, headers=headers, json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 2})
    assert res.status_code == 409, res.text
    assert _count(db, customer.id) == 1


def test_past_due_subscription_blocks_a_second_one_to_the_same_plan(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="500.00")
    first = client.post(API, headers=auth_headers, json={"customer_id": customer.id, "plan_id": plan.id})
    assert first.status_code == 201, first.text
    sub = db.get(Subscription, first.json()["id"])
    sub.status = SubscriptionStatus.PAST_DUE
    db.commit()

    res = client.post(API, headers=auth_headers, json={"customer_id": customer.id, "plan_id": plan.id})
    assert res.status_code == 422, res.text
    assert "past-due subscription" in res.json()["error"]["message"]
    assert _count(db, customer.id) == 1

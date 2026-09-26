"""Real-concurrency tests for one-shot transitions (PostgreSQL only).

Each operation is fired from several threads at once (own TestClient / session each,
released by a barrier). The state change must happen once AND be audited once; the
losers get 409 (or, for quote -> subscription, the same subscription back).
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from backend.app.core.database import engine
from backend.app.models import Invoice, Plan, Quote, QuoteStatus
from backend.app.models.catalog_cpq import CPQDeal
from backend.app.models.governance import AuditLog
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.tests.test_postgres_concurrency import fresh, run_concurrently, thread_client

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="real row-lock concurrency needs PostgreSQL (set TEST_DATABASE_URL)",
)

SUBS = "/api/v1/subscriptions"
QUOTES = "/api/v1/quotes"


def _audits(action, entity_id):
    with fresh() as s:
        return s.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == entity_id)
        )


def _count(model, *where):
    with fresh() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


def test_concurrent_activation_audits_once(client, tenant):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1200.00")
    headers = tenant.headers()
    res = client.post(SUBS, headers=headers, json={"customer_id": customer.id, "plan_id": plan.id, "status": "draft"})
    assert res.status_code == 201, res.text
    sub_id = res.json()["id"]

    codes, errors = run_concurrently(
        lambda _i: thread_client().post(f"{SUBS}/{sub_id}/activate", headers=headers).status_code, n=4
    )
    assert errors == [None] * 4, errors
    assert codes.count(200) == 1, codes
    assert all(c in (200, 409) for c in codes), codes
    assert _audits("SUBSCRIPTION_ACTIVATED", sub_id) == 1
    assert _count(Invoice, Invoice.subscription_id == sub_id) == 1


def test_concurrent_trial_conversion_audits_once(client, tenant):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="2500.00", trial_days=14)
    headers = tenant.headers()
    res = client.post(SUBS, headers=headers, json={"customer_id": customer.id, "plan_id": plan.id})
    assert res.json()["status"] == "trialing"
    sub_id = res.json()["id"]

    codes, errors = run_concurrently(
        lambda _i: thread_client()
        .post(f"/api/v1/trials/{sub_id}/convert", headers=headers, json={"generate_first_invoice": True})
        .status_code,
        n=4,
    )
    assert errors == [None] * 4, errors
    assert codes.count(200) == 1, codes
    assert all(c in (200, 409, 422) for c in codes), codes
    assert _audits("TRIAL_CONVERTED", sub_id) == 1
    assert _count(Invoice, Invoice.subscription_id == sub_id) == 1


def _accepted_quote(client, headers, customer, items):
    res = client.post(QUOTES, headers=headers, json={"customer_id": customer.id, "title": "Race", "items": items})
    assert res.status_code == 201, res.text
    qid = res.json()["id"]
    assert client.post(f"{QUOTES}/{qid}/send", headers=headers).status_code == 200
    assert client.post(f"{QUOTES}/{qid}/mark-accepted", headers=headers, json={}).status_code == 200
    return qid


def test_concurrent_quote_to_invoice_audits_once(client, tenant):
    customer = tenant.customer()
    headers = tenant.headers()
    qid = _accepted_quote(
        client, headers, customer, [{"description": "Work", "quantity": "1", "unit_price": "1000.00", "tax_rate_pct": "18"}]
    )
    codes, errors = run_concurrently(
        lambda _i: thread_client().post(f"{QUOTES}/{qid}/convert", headers=headers, json={}).status_code, n=3
    )
    assert errors == [None] * 3, errors
    assert sorted(codes) == [201, 409, 409], codes
    assert _audits("QUOTE_CONVERTED", qid) == 1


def test_concurrent_quote_to_subscription_creates_one(client, tenant):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    headers = tenant.headers()
    qid = _accepted_quote(
        client, headers, customer,
        [{"plan_id": plan.id, "description": "Seats", "quantity": "2", "unit_price": "950.00", "tax_rate_pct": "18"}],
    )

    def convert(_i):
        r = thread_client().post(f"{QUOTES}/{qid}/convert-to-subscription", headers=headers, json={})
        return r.status_code, (r.json().get("id") if r.status_code in (200, 201) else r.text)

    results, errors = run_concurrently(convert, n=4)
    assert errors == [None] * 4, errors
    codes = [c for c, _ in results]
    assert codes.count(201) == 1, results
    assert all(c in (200, 201) for c in codes), results
    sub_ids = {sid for _, sid in results}
    assert len(sub_ids) == 1, results
    sub_id = sub_ids.pop()
    assert _count(Subscription, Subscription.customer_id == customer.id) == 1
    assert _count(Invoice, Invoice.customer_id == customer.id) == 1
    assert _audits("QUOTE_CONVERTED", qid) == 1
    assert _audits("SUBSCRIPTION_CREATED", sub_id) == 1
    with fresh() as s:
        quote = s.get(Quote, qid)
        assert quote.status == QuoteStatus.CONVERTED
        assert quote.converted_subscription_id == sub_id


def test_concurrent_cpq_deal_conversion_audits_once(client, tenant):
    headers = tenant.headers()
    offering = client.post(
        "/api/v1/catalog/offerings",
        headers=headers,
        json={"name": "Node", "sku": f"N-{uuid.uuid4().hex[:6]}", "type": "product", "currency": "INR",
              "pricing_model": "per_unit", "base_price": "100.00", "tax_rate_pct": "18.00"},
    ).json()
    customer = tenant.customer()
    deal = client.post(
        "/api/v1/cpq/deals",
        headers=headers,
        json={"title": "Deal", "customer_id": customer.id, "items": [{"offering_id": offering["id"], "quantity": 2}]},
    ).json()
    assert deal["status"] == "configured", deal

    codes, errors = run_concurrently(
        lambda _i: thread_client().post(f"/api/v1/cpq/deals/{deal['id']}/convert-quote", headers=headers).status_code, n=3
    )
    assert errors == [None] * 3, errors
    assert len([c for c in codes if c in (200, 201)]) == 1, codes
    assert all(c in (200, 201, 409) for c in codes), codes
    assert _audits("CPQ_DEAL_CONVERTED", deal["id"]) == 1
    with fresh() as s:
        assert s.get(CPQDeal, deal["id"]).converted_quote_id is not None
        assert s.scalar(select(func.count()).select_from(Quote).where(Quote.customer_id == customer.id)) == 1


def test_concurrent_first_subscribe_to_offering_links_one_plan(client, tenant):
    headers = tenant.headers()
    offering = client.post(
        "/api/v1/catalog/offerings",
        headers=headers,
        json={"name": "Team", "sku": f"T-{uuid.uuid4().hex[:6]}", "type": "plan", "currency": "INR",
              "pricing_model": "per_unit", "base_price": "400.00", "tax_rate_pct": "18.00", "billing_frequency": "monthly"},
    ).json()
    customers = [tenant.customer() for _ in range(3)]

    codes, errors = run_concurrently(
        lambda i: thread_client()
        .post(SUBS, headers=headers, json={"customer_id": customers[i].id, "offering_id": offering["id"], "quantity": 1})
        .status_code,
        n=3,
    )
    assert errors == [None] * 3, errors
    assert codes == [201, 201, 201], codes
    assert _count(Plan, Plan.offering_id == offering["id"]) == 1
    with fresh() as s:
        plan_ids = set(
            s.scalars(select(Subscription.plan_id).where(Subscription.customer_id.in_([c.id for c in customers])))
        )
    assert len(plan_ids) == 1

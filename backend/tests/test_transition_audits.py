"""One-shot transitions audit exactly once: a repeated activation / conversion is rejected
(or returns the existing result) without writing a second audit entry."""
import uuid

from sqlalchemy import func, select

from backend.app.models.governance import AuditLog
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.services import subscription_service

SUBS = "/api/v1/subscriptions"


def _audit_count(db, action, entity_id):
    db.expire_all()
    return db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == entity_id)
    )


def test_repeated_activation_audits_once(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1200.00")
    res = client.post(SUBS, json={"customer_id": customer.id, "plan_id": plan.id, "status": "draft"}, headers=auth_headers)
    assert res.status_code == 201, res.text
    sub_id = res.json()["id"]
    assert client.post(f"{SUBS}/{sub_id}/activate", headers=auth_headers).status_code == 200
    assert client.post(f"{SUBS}/{sub_id}/activate", headers=auth_headers).status_code == 409
    assert _audit_count(db, "SUBSCRIPTION_ACTIVATED", sub_id) == 1


def test_stale_activation_object_does_not_reactivate(client, tenant, auth_headers, db):
    """A request that loaded the subscription while it was still a draft (the losing side
    of a race) must not activate/audit it again once another request has activated it."""
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="700.00")
    res = client.post(SUBS, json={"customer_id": customer.id, "plan_id": plan.id, "status": "draft"}, headers=auth_headers)
    sub_id = res.json()["id"]
    stale = subscription_service.get_subscription(db, tenant.organization.id, sub_id)
    assert stale.status == SubscriptionStatus.DRAFT
    assert client.post(f"{SUBS}/{sub_id}/activate", headers=auth_headers).status_code == 200

    from backend.app.api.deps import CurrentContext
    from backend.app.core.exceptions import InvalidStateError
    from backend.app.models import Membership

    membership = db.scalars(select(Membership).where(Membership.user_id == tenant.owner.id)).first()
    ctx = CurrentContext(user=tenant.owner, organization=tenant.organization, membership=membership, ip_address=None, user_agent=None)
    try:
        subscription_service.activate_subscription(db, ctx, stale)
        raise AssertionError("stale activation should be rejected")
    except InvalidStateError:
        db.rollback()
    assert _audit_count(db, "SUBSCRIPTION_ACTIVATED", sub_id) == 1


def test_repeated_trial_conversion_audits_once(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="2500.00", trial_days=14)
    res = client.post(SUBS, json={"customer_id": customer.id, "plan_id": plan.id}, headers=auth_headers)
    assert res.json()["status"] == "trialing"
    sub_id = res.json()["id"]
    first = client.post(f"/api/v1/trials/{sub_id}/convert", json={"generate_first_invoice": True}, headers=auth_headers)
    assert first.status_code == 200, first.text
    second = client.post(f"/api/v1/trials/{sub_id}/convert", json={"generate_first_invoice": True}, headers=auth_headers)
    assert second.status_code in (409, 422), second.text
    assert _audit_count(db, "TRIAL_CONVERTED", sub_id) == 1


def test_scheduler_trial_conversion_skips_already_converted(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="900.00", trial_days=7)
    sub_id = client.post(SUBS, json={"customer_id": customer.id, "plan_id": plan.id}, headers=auth_headers).json()["id"]
    stale = db.get(Subscription, sub_id)
    assert stale.status == SubscriptionStatus.TRIALING
    assert client.post(f"/api/v1/trials/{sub_id}/convert", json={}, headers=auth_headers).status_code == 200
    # The scheduler still holds the stale TRIALING object: it must not convert/audit again.
    assert subscription_service.convert_trial(db, stale) is None
    db.commit()
    assert _audit_count(db, "TRIAL_CONVERTED", sub_id) == 1


def test_repeated_cpq_deal_conversion_audits_once(client, tenant, auth_headers, db):
    offering = client.post(
        "/api/v1/catalog/offerings",
        json={"name": "Node", "sku": f"N-{uuid.uuid4().hex[:6]}", "type": "product", "currency": "INR",
              "pricing_model": "per_unit", "base_price": "100.00", "tax_rate_pct": "18.00"},
        headers=auth_headers,
    ).json()
    customer = tenant.customer()
    deal = client.post(
        "/api/v1/cpq/deals",
        json={"title": "Deal", "customer_id": customer.id, "items": [{"offering_id": offering["id"], "quantity": 2}]},
        headers=auth_headers,
    ).json()
    assert deal["status"] == "configured", deal
    assert client.post(f"/api/v1/cpq/deals/{deal['id']}/convert-quote", headers=auth_headers).status_code in (200, 201)
    assert client.post(f"/api/v1/cpq/deals/{deal['id']}/convert-quote", headers=auth_headers).status_code == 409
    assert _audit_count(db, "CPQ_DEAL_CONVERTED", deal["id"]) == 1

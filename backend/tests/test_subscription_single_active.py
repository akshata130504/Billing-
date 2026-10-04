"""One live (active / trialing / paused) subscription per (organization, customer, plan)."""
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select

from backend.app.core.tenant_context import tenant_context
from backend.app.models import AuditLog, Subscription, SubscriptionStatus

SUBS = "/api/v1/subscriptions"


def _insert(db, tenant, customer, plan, status):
    with tenant_context(tenant.organization.id):
        sub = Subscription(
            organization_id=tenant.organization.id,
            subscription_number=f"SUB-{uuid.uuid4().hex[:8].upper()}",
            customer_id=customer.id,
            plan_id=plan.id,
            status=status,
            quantity=1,
            start_date=date.today(),
            current_period_start=date.today(),
            current_period_end=date.today() + timedelta(days=30),
            next_billing_date=date.today() + timedelta(days=30),
            currency="INR",
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub


def _create(client, h, customer, plan):
    return client.post(SUBS, headers=h, json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1})


def _audit_count(db, tenant, action, entity_id):
    with tenant_context(tenant.organization.id):
        return db.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.organization_id == tenant.organization.id,
                AuditLog.action == action,
                AuditLog.entity_id == entity_id,
            )
        )


def _live_count(db, tenant, customer, plan):
    db.expire_all()
    with tenant_context(tenant.organization.id):
        return db.scalar(
            select(func.count()).select_from(Subscription).where(
                Subscription.organization_id == tenant.organization.id,
                Subscription.customer_id == customer.id,
                Subscription.plan_id == plan.id,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
            )
        )


def test_create_blocked_while_same_plan_subscription_is_paused(client, tenant, db):
    h = tenant.headers()
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    a = _create(client, h, customer, plan).json()
    assert client.post(f"{SUBS}/{a['id']}/pause", headers=h).status_code == 200
    res = _create(client, h, customer, plan)
    assert res.status_code == 422, res.text
    assert "paused" in res.json()["error"]["message"]
    assert _live_count(db, tenant, customer, plan) == 0


def test_resume_refused_when_other_active_exists(client, tenant, db):
    h = tenant.headers()
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    paused = _insert(db, tenant, customer, plan, SubscriptionStatus.PAUSED)
    _insert(db, tenant, customer, plan, SubscriptionStatus.ACTIVE)
    res = client.post(f"{SUBS}/{paused.id}/resume", headers=h)
    assert res.status_code == 422, res.text
    db.expire_all()
    assert db.get(Subscription, paused.id).status == SubscriptionStatus.PAUSED
    assert _audit_count(db, tenant, "SUBSCRIPTION_RESUMED", paused.id) == 0
    assert _live_count(db, tenant, customer, plan) == 1


def test_resume_refused_when_other_trialing_exists(client, tenant, db):
    h = tenant.headers()
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    paused = _insert(db, tenant, customer, plan, SubscriptionStatus.PAUSED)
    _insert(db, tenant, customer, plan, SubscriptionStatus.TRIALING)
    assert client.post(f"{SUBS}/{paused.id}/resume", headers=h).status_code == 422
    db.expire_all()
    assert db.get(Subscription, paused.id).status == SubscriptionStatus.PAUSED


def test_resume_without_conflict_succeeds_and_audits(client, tenant, db):
    h = tenant.headers()
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    a = _create(client, h, customer, plan).json()
    assert client.post(f"{SUBS}/{a['id']}/pause", headers=h).status_code == 200
    res = client.post(f"{SUBS}/{a['id']}/resume", headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "active"
    assert _audit_count(db, tenant, "SUBSCRIPTION_RESUMED", a["id"]) == 1
    assert _live_count(db, tenant, customer, plan) == 1
    # Resuming again is a clean state error, not a second audit row.
    assert client.post(f"{SUBS}/{a['id']}/resume", headers=h).status_code == 409
    assert _audit_count(db, tenant, "SUBSCRIPTION_RESUMED", a["id"]) == 1


def test_different_plan_for_same_customer_is_allowed(client, tenant, db):
    h = tenant.headers()
    customer = tenant.customer()
    _, plan1 = tenant.product_with_plan()
    _, plan2 = tenant.product_with_plan()
    a = _create(client, h, customer, plan1).json()
    assert client.post(f"{SUBS}/{a['id']}/pause", headers=h).status_code == 200
    # Same customer, other plan: allowed while plan1's subscription is paused.
    assert _create(client, h, customer, plan2).status_code == 201
    # And resuming plan1's paused subscription is not blocked by the plan2 one.
    assert client.post(f"{SUBS}/{a['id']}/resume", headers=h).status_code == 200


def test_activate_draft_conflicting_with_active_or_paused_rejected(client, tenant, db):
    h = tenant.headers()
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    # A DRAFT can always exist (exempt).
    draft = _insert(db, tenant, customer, plan, SubscriptionStatus.DRAFT)
    paused = _insert(db, tenant, customer, plan, SubscriptionStatus.PAUSED)
    res = client.post(f"{SUBS}/{draft.id}/activate", headers=h)
    assert res.status_code == 422, res.text
    assert "paused" in res.json()["error"]["message"]
    paused.status = SubscriptionStatus.ACTIVE
    db.commit()
    res = client.post(f"{SUBS}/{draft.id}/activate", headers=h)
    assert res.status_code == 422, res.text
    db.expire_all()
    assert db.get(Subscription, draft.id).status == SubscriptionStatus.DRAFT
    assert _live_count(db, tenant, customer, plan) == 1


def test_activate_draft_without_conflict_still_works(client, tenant, db):
    h = tenant.headers()
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    draft = _insert(db, tenant, customer, plan, SubscriptionStatus.DRAFT)
    assert client.post(f"{SUBS}/{draft.id}/activate", headers=h).status_code == 200


def test_trial_conversion_regression(tenant, db):
    from backend.app.services import subscription_service

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(trial_days=7)
    trial = _insert(db, tenant, customer, plan, SubscriptionStatus.TRIALING)
    with tenant_context(tenant.organization.id):
        subscription_service.convert_trial(db, db.get(Subscription, trial.id))
        db.commit()
    db.expire_all()
    assert db.get(Subscription, trial.id).status == SubscriptionStatus.ACTIVE


def test_trial_conversion_skipped_when_duplicate_live_exists(tenant, db):
    from backend.app.services import subscription_service

    customer = tenant.customer()
    _, plan = tenant.product_with_plan(trial_days=7)
    trial = _insert(db, tenant, customer, plan, SubscriptionStatus.TRIALING)
    _insert(db, tenant, customer, plan, SubscriptionStatus.ACTIVE)
    with tenant_context(tenant.organization.id):
        assert subscription_service.convert_trial(db, db.get(Subscription, trial.id)) is None
        db.commit()
    db.expire_all()
    assert db.get(Subscription, trial.id).status == SubscriptionStatus.TRIALING


def test_dunning_reactivate_conflict_rejected_and_non_conflict_audited(client, tenant, db):
    h = tenant.headers()
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    cancelled = _insert(db, tenant, customer, plan, SubscriptionStatus.CANCELLED)
    active = _insert(db, tenant, customer, plan, SubscriptionStatus.ACTIVE)
    res = client.post(f"/api/v1/dunning/subscriptions/{cancelled.id}/reactivate", headers=h)
    assert res.status_code == 422, res.text
    db.expire_all()
    assert db.get(Subscription, cancelled.id).status == SubscriptionStatus.CANCELLED
    assert _audit_count(db, tenant, "SUBSCRIPTION_REACTIVATED", cancelled.id) == 0
    assert _live_count(db, tenant, customer, plan) == 1

    active.status = SubscriptionStatus.CANCELLED
    db.commit()
    res = client.post(f"/api/v1/dunning/subscriptions/{cancelled.id}/reactivate", headers=h)
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.get(Subscription, cancelled.id).status == SubscriptionStatus.ACTIVE
    assert _audit_count(db, tenant, "SUBSCRIPTION_REACTIVATED", cancelled.id) == 1


def test_other_tenants_subscription_never_conflicts(client, tenant, db):
    from backend.app.services import subscription_service
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    other_customer = other.customer()
    _, other_plan = other.product_with_plan()
    _insert(db, other, other_customer, other_plan, SubscriptionStatus.ACTIVE)

    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    assert _create(client, tenant.headers(), customer, plan).status_code == 201

    # The check is scoped by organization: the other org's rows are invisible to this one.
    with tenant_context(tenant.organization.id):
        subscription_service.assert_no_conflicting_subscription(
            db, tenant.organization.id, other_customer.id, other_plan.id
        )

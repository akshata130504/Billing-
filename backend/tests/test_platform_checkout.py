"""Stage 3: Owner-initiated checkout of a Rooman plan with Rooman's own Razorpay account.

Razorpay is never called: the provider functions are replaced by a recording fake, and the SDK client
itself is replaced by one that fails the test if anything reaches it. Plans are published only
inside these tests; the shipped catalog stays all-draft.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.core.config import settings
from backend.app.core.plan_catalog import CATALOG_PATH, load_catalog
from backend.app.core.tenant_context import system_context, tenant_context
from backend.app.models import (
    MemberRole,
    Organization,
    PlatformCheckoutAttempt,
    PlatformPayment,
    PlatformNotification,
    PlatformPaymentReview,
    PlatformProviderPlan,
    PlatformSubscription,
)
from backend.app.models.subscription_access import OrganizationEntitlement
from backend.app.services import (
    platform_checkout_service as checkout,
    platform_razorpay as provider,
    platform_subscription_service as subs,
    razorpay_gateway,
)

API = "/api/v1"
URL = f"{API}/subscription-checkout"
KEY_ID = "rzp_test_RoomanCheckoutDummy"
SECRET = "dummy-rooman-checkout-secret-xyz"
UTC = timezone.utc


def _catalog(**changes):
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    for plan in raw["plans"]:
        change = changes.get(plan["code"])
        if change:
            status = change if isinstance(change, str) else change.get("status", "published")
            plan["status"] = status
            if status == "published":
                plan.update(tax_treatment="exclusive", approved_by="Test approver", approved_on="2026-10-13")
            if isinstance(change, dict) and "amount_minor" in change:
                plan["price"]["amount_minor"] = change["amount_minor"]
    return load_catalog(raw)


def _use_catalog(monkeypatch, cat):
    monkeypatch.setattr(subs, "catalog", lambda: cat)
    monkeypatch.setattr(checkout, "catalog", lambda: cat)


class FakeProvider:
    def __init__(self):
        self.plans, self.subscriptions, self.plan_lookups, self.sub_lookups = [], [], [], []
        self.fail_plan = self.fail_sub = None  # an exception class to raise once
        self.found_plan = self.found_sub = None

    def create_plan(self, **kw):
        self.plans.append(kw)
        if self.fail_plan:
            exc, self.fail_plan = self.fail_plan, None
            raise exc("simulated")
        return {"id": f"plan_{uuid.uuid4().hex[:14]}", "period": provider.PERIODS[kw["interval"]],
                "interval": kw["interval_count"], "item": {"amount": kw["amount_minor"], "currency": kw["currency"]},
                "notes": kw["notes"]}

    def create_subscription(self, **kw):
        self.subscriptions.append(kw)
        if self.fail_sub:
            exc, self.fail_sub = self.fail_sub, None
            raise exc("simulated")
        return {"id": f"sub_{uuid.uuid4().hex[:14]}", "status": "created", "plan_id": kw["plan_id"], "notes": kw["notes"]}

    def find_plan(self, ref, created_after):
        self.plan_lookups.append(ref)
        return self.found_plan(ref) if callable(self.found_plan) else self.found_plan

    def find_subscription(self, plan_id, attempt_id, created_after):
        self.sub_lookups.append(attempt_id)
        return self.found_sub(plan_id, attempt_id) if callable(self.found_sub) else self.found_sub


@pytest.fixture(autouse=True)
def isolated(db, monkeypatch):
    with system_context():
        db.query(PlatformNotification).delete()
        db.query(PlatformPaymentReview).delete()  # references the attempts (RESTRICT)
        db.query(PlatformPayment).delete()  # references the attempts (RESTRICT)
        db.query(PlatformCheckoutAttempt).delete()
        db.query(PlatformProviderPlan).delete()
        db.commit()
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", SECRET)
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", False)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_WEBHOOK_SECRET", "dummy-rooman-webhook-secret-xyz")

    def no_network(*a, **k):
        raise AssertionError("a test reached the real Razorpay client")

    monkeypatch.setattr(razorpay_gateway, "_get_client", no_network)


@pytest.fixture
def fake(monkeypatch):
    f = FakeProvider()
    for name in ("create_plan", "create_subscription", "find_plan", "find_subscription"):
        monkeypatch.setattr(provider, name, getattr(f, name))
    return f


@pytest.fixture
def published(monkeypatch):
    cat = _catalog(starter="published", growth="published", business="retired")
    _use_catalog(monkeypatch, cat)
    return cat


def _start(client, tenant, plan="starter", headers=None, **extra):
    return client.post(URL, json={"plan_code": plan, **extra}, headers=headers or tenant.headers())


def _code(resp):
    return resp.json()["error"]["code"]


def _attempts(db, org_id):
    with system_context():
        return db.scalars(select(PlatformCheckoutAttempt).where(PlatformCheckoutAttempt.organization_id == org_id)
                          .order_by(PlatformCheckoutAttempt.created_at)).all()


def _provider_plans(db):
    with system_context():
        return db.scalars(select(PlatformProviderPlan)).all()


def _expired_trial(db, tenant):
    now = datetime.now(UTC)
    db.add(PlatformSubscription(organization_id=tenant.organization.id, state="trialing", reminders_sent=[],
                                trial_started_at=now - timedelta(minutes=30), trial_ends_at=now - timedelta(minutes=15)))
    db.commit()


# --- the happy path -------------------------------------------------------------------------------


def test_owner_starts_checkout_with_catalog_terms_only(client, db, tenant, fake, published):
    r = _start(client, tenant)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["razorpay_key_id"] == KEY_ID and body["razorpay_subscription_id"].startswith("sub_")
    assert body["reused"] is False
    assert body["plan"] == {"code": "starter", "name": "Starter", "description": published.plan("starter").description,
                            "amount_minor": 79900, "currency": "INR", "interval": "month", "interval_count": 1,
                            "tax_treatment": "exclusive", "seat_limit": 3, "sandbox": False}
    assert SECRET not in r.text
    # Provider requests come from the catalog and carry our references.
    [plan_call] = fake.plans
    assert (plan_call["amount_minor"], plan_call["currency"], plan_call["interval"], plan_call["interval_count"]) == (
        79900, "INR", "month", 1)
    [sub_call] = fake.subscriptions
    attempt = _attempts(db, tenant.organization.id)[0]
    assert sub_call["notes"]["checkout_attempt_id"] == attempt.id
    assert sub_call["notes"]["organization_id"] == tenant.organization.id
    assert sub_call["total_count"] == settings.PLATFORM_SUBSCRIPTION_TOTAL_COUNT
    assert sub_call["plan_id"] == attempt.provider_plan_id
    assert attempt.status == "created" and attempt.mode == "test" and attempt.provider_subscription_id == body["razorpay_subscription_id"]
    assert (attempt.amount_minor, attempt.seat_limit, attempt.catalog_version) == (79900, 3, published.version)
    assert abs(sub_call["expire_by"] - int(checkout._aware(attempt.expires_at).timestamp())) <= 1


def test_browser_cannot_supply_prices_or_contents(client, tenant, fake, published):
    for extra in ({"amount_minor": 100}, {"seat_limit": 50}, {"modules": ["dunning"]}, {"interval": "year"}):
        r = _start(client, tenant, **extra)
        assert r.status_code == 422, extra
    assert client.post(URL, json={"plan_code": "Starter Plan"}, headers=tenant.headers()).status_code == 422
    assert fake.plans == [] and fake.subscriptions == []


def test_checkout_grants_nothing_and_keeps_the_expired_trial_read_only(client, db, tenant, fake, published):
    _expired_trial(db, tenant)
    customer_body = {"display_name": "Acme", "email": "acme@example.test"}
    assert _code(client.post(f"{API}/customers", json=customer_body, headers=tenant.headers())) == "TRIAL_EXPIRED"
    r = _start(client, tenant)
    assert r.status_code == 201, r.text  # the purchase route is reachable while read-only
    assert _code(client.post(f"{API}/customers", json=customer_body, headers=tenant.headers())) == "TRIAL_EXPIRED"
    db.expire_all()
    org = db.get(Organization, tenant.organization.id)
    assert org.module_access == "unrestricted" and org.seat_limit is None
    with tenant_context(org.id):
        assert db.scalars(select(OrganizationEntitlement).where(OrganizationEntitlement.organization_id == org.id)).all() == []
    assert subs.get_subscription(db, org.id).state == "trialing"
    assert subs.access_for(db, org.id).state == "trial_expired"
    me = client.get(f"{API}/auth/me", headers=tenant.headers()).json()
    assert me["subscription"] is None and me["trial"]["state"] == "trial_expired"


# --- who and what ---------------------------------------------------------------------------------


@pytest.mark.parametrize("role", [MemberRole.ADMIN, MemberRole.FINANCE, MemberRole.VIEWER])
def test_only_the_owner_can_start_checkout(client, tenant, fake, published, role):
    r = _start(client, tenant, headers=tenant.headers_for_role(role))
    assert r.status_code == 403
    assert fake.plans == [] and fake.subscriptions == []


def test_unauthenticated_requests_are_refused(client, fake, published):
    assert client.post(URL, json={"plan_code": "starter"}).status_code == 401


def test_draft_retired_and_unknown_plans_are_refused(client, tenant, fake, monkeypatch):
    _use_catalog(monkeypatch, _catalog(business="retired"))  # starter and growth stay draft
    for code in ("starter", "growth", "business", "platinum"):
        r = _start(client, tenant, plan=code)
        assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "PLAN_NOT_AVAILABLE", code
    assert fake.plans == [] and fake.subscriptions == []


def test_shipped_catalog_cannot_be_bought(client, tenant, fake):
    for code in ("starter", "growth", "business"):
        r = _start(client, tenant, plan=code)
        assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "PLAN_NOT_AVAILABLE"
    assert fake.plans == []


def test_already_paid_or_too_many_members_is_refused_before_razorpay(client, db, tenant, fake, published):
    for _ in range(3):
        tenant.add_member(f"m-{uuid.uuid4().hex[:6]}", MemberRole.VIEWER)
    db.commit()  # 4 seats used, Starter has 3
    r = _start(client, tenant, plan="starter")
    assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "SEATS_EXCEED_PLAN"
    subs.activate(db, tenant.organization.id, "growth")
    db.commit()
    r = _start(client, tenant, plan="growth")
    assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "SUBSCRIPTION_ALREADY_ACTIVE"
    assert fake.plans == [] and fake.subscriptions == []


def test_platform_keys_are_required_and_tenant_keys_are_never_used(client, tenant, fake, published, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_TenantFallbackKey")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "tenant-fallback-secret")
    r = _start(client, tenant)
    assert r.status_code == 503 and _code(r) == "GATEWAY_NOT_CONFIGURED"
    assert fake.plans == []


def test_live_keys_are_refused_until_enabled(client, tenant, fake, published, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", "rzp_live_RoomanLiveDummy")
    r = _start(client, tenant)
    assert r.status_code == 503 and _code(r) == "LIVE_CHECKOUT_DISABLED"
    assert fake.plans == []


def test_checkout_waits_for_the_webhook_secret(client, db, tenant, fake, published, monkeypatch):
    # Without the webhook, a payment could only ever be confirmed by the browser callback.
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_WEBHOOK_SECRET", "")
    r = _start(client, tenant)
    assert r.status_code == 503 and _code(r) == "CHECKOUT_NOT_READY"
    assert fake.plans == [] and fake.subscriptions == [] and _attempts(db, tenant.organization.id) == []


# --- provider plans --------------------------------------------------------------------------------


def test_one_provider_plan_per_terms_and_mode(client, db, tenant, fake, published, monkeypatch):
    from backend.tests.conftest import Tenant

    assert _start(client, tenant).status_code == 201
    other = Tenant(db, uuid.uuid4().hex[:8])
    assert _start(client, other).status_code == 201
    assert len(fake.plans) == 1  # the second organization reuses the Starter test-mode plan
    assert len(fake.subscriptions) == 2

    # A price change gets its own provider plan; the old one is never reused for the new terms.
    _use_catalog(monkeypatch, _catalog(starter={"amount_minor": 89900}, growth="published"))
    third = Tenant(db, uuid.uuid4().hex[:8])
    assert _start(client, third).status_code == 201
    assert len(fake.plans) == 2 and fake.plans[1]["amount_minor"] == 89900

    # Live mode never reuses a test-mode plan id.
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", True)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", "rzp_live_RoomanLiveDummy")
    fourth = Tenant(db, uuid.uuid4().hex[:8])
    assert _start(client, fourth).status_code == 201
    rows = _provider_plans(db)
    assert len(fake.plans) == 3
    assert sorted((r.mode, r.amount_minor) for r in rows) == [("live", 89900), ("test", 79900), ("test", 89900)]
    assert len({r.provider_plan_id for r in rows}) == 3


def test_ambiguous_plan_create_is_reconciled_not_repeated(client, db, tenant, fake, published):
    fake.fail_plan = provider.ProviderUnavailable
    r = _start(client, tenant)
    assert r.status_code == 503 and _code(r) == "CHECKOUT_UNAVAILABLE"
    [row] = _provider_plans(db)
    assert row.status == "unknown" and row.attempts == 1 and row.provider_plan_id is None
    assert _attempts(db, tenant.organization.id) == []  # no checkout without a plan

    # Razorpay did create it: the retry finds it by its reference and creates nothing new.
    fake.found_plan = lambda ref: {"id": "plan_FOUNDBYREF00001", "period": "monthly", "interval": 1,
                                   "item": {"amount": 79900, "currency": "INR"}, "notes": {"rooman_plan_ref": ref}}
    r = _start(client, tenant)
    assert r.status_code == 201, r.text
    assert len(fake.plans) == 1 and fake.plan_lookups == [row.reconcile_ref]
    db.expire_all()
    [row] = _provider_plans(db)
    assert row.status == "created" and row.provider_plan_id == "plan_FOUNDBYREF00001"
    assert fake.subscriptions[0]["plan_id"] == "plan_FOUNDBYREF00001"


def test_ambiguous_plan_create_not_found_is_created_once_more(client, db, tenant, fake, published):
    fake.fail_plan = provider.ProviderUnavailable
    assert _start(client, tenant).status_code == 503
    assert _start(client, tenant).status_code == 201  # lookup found nothing -> create again
    assert len(fake.plans) == 2 and len(fake.plan_lookups) == 1
    assert _provider_plans(db)[0].attempts == 2


def test_reconciled_plan_with_other_terms_is_refused(client, db, tenant, fake, published):
    fake.fail_plan = provider.ProviderUnavailable
    assert _start(client, tenant).status_code == 503
    fake.found_plan = {"id": "plan_WRONGTERMS0001", "period": "monthly", "interval": 1,
                       "item": {"amount": 100, "currency": "INR"}}
    r = _start(client, tenant)
    assert r.status_code == 502 and _code(r) == "GATEWAY_ERROR"
    assert _provider_plans(db)[0].provider_plan_id is None


def test_an_in_flight_plan_create_blocks_a_second_create(client, db, tenant, fake, published):
    with system_context():
        db.add(PlatformProviderPlan(
            provider="razorpay", mode="test", plan_code="starter",
            fingerprint=checkout.billing_fingerprint(published.plan("starter")), amount_minor=79900, currency="INR",
            billing_interval="month", billing_interval_count=1, status="pending", reconcile_ref=uuid.uuid4().hex,
            attempts=1, last_attempt_at=datetime.now(UTC)))
        db.commit()
    r = _start(client, tenant)
    assert r.status_code == 503 and _code(r) == "CHECKOUT_UNAVAILABLE"
    assert fake.plans == [] and fake.plan_lookups == []


def test_rejected_plan_create_fails_cleanly(client, db, tenant, fake, published):
    fake.fail_plan = provider.ProviderRejected
    r = _start(client, tenant)
    assert r.status_code == 502 and _code(r) == "GATEWAY_ERROR"
    assert _provider_plans(db)[0].status == "failed"


# --- checkout attempts ---------------------------------------------------------------------------


def test_same_plan_again_returns_the_open_checkout(client, db, tenant, fake, published):
    first = _start(client, tenant).json()
    again = _start(client, tenant).json()
    assert again["reused"] is True and again["razorpay_subscription_id"] == first["razorpay_subscription_id"]
    assert again["checkout_attempt_id"] == first["checkout_attempt_id"]
    assert len(fake.subscriptions) == 1 and len(_attempts(db, tenant.organization.id)) == 1


def test_other_plan_waits_until_the_open_checkout_expires(client, db, tenant, fake, published):
    _start(client, tenant, plan="starter")
    r = _start(client, tenant, plan="growth")
    assert r.status_code == 409 and r.json()["error"]["details"]["code"] == "CHECKOUT_IN_PROGRESS"
    assert r.json()["error"]["details"]["plan_code"] == "starter"
    [attempt] = _attempts(db, tenant.organization.id)
    with system_context():
        attempt.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    r = _start(client, tenant, plan="growth")
    assert r.status_code == 201, r.text
    states = [(a.plan_code, a.status) for a in _attempts(db, tenant.organization.id)]
    assert states == [("starter", "expired"), ("growth", "created")]


def test_ambiguous_subscription_create_is_reconciled(client, db, tenant, fake, published):
    fake.fail_sub = provider.ProviderUnavailable
    r = _start(client, tenant)
    assert r.status_code == 503 and _code(r) == "CHECKOUT_UNAVAILABLE"
    [attempt] = _attempts(db, tenant.organization.id)
    assert attempt.status == "unknown" and attempt.provider_subscription_id is None
    assert subs.access_for(db, tenant.organization.id).state == "none"  # nothing granted

    fake.found_sub = lambda plan_id, attempt_id: {"id": "sub_FOUNDBYATTEMPT1", "plan_id": plan_id,
                                                  "notes": {"checkout_attempt_id": attempt_id}}
    r = _start(client, tenant)
    assert r.status_code == 201, r.text
    assert r.json()["razorpay_subscription_id"] == "sub_FOUNDBYATTEMPT1" and r.json()["reused"] is True
    assert len(fake.subscriptions) == 1 and fake.sub_lookups == [attempt.id]


def test_ambiguous_subscription_not_found_starts_a_new_attempt(client, db, tenant, fake, published):
    fake.fail_sub = provider.ProviderUnavailable
    assert _start(client, tenant).status_code == 503
    r = _start(client, tenant)
    assert r.status_code == 201 and r.json()["reused"] is False
    states = [a.status for a in _attempts(db, tenant.organization.id)]
    assert states == ["failed", "created"] and len(fake.subscriptions) == 2


def test_rejected_subscription_create_fails_cleanly(client, db, tenant, fake, published):
    fake.fail_sub = provider.ProviderRejected
    r = _start(client, tenant)
    assert r.status_code == 502 and _code(r) == "GATEWAY_ERROR"
    assert [a.status for a in _attempts(db, tenant.organization.id)] == ["failed"]
    assert _start(client, tenant).status_code == 201  # a failed attempt does not block a new one


def test_an_in_flight_checkout_blocks_a_second_one(client, db, tenant, fake, published):
    with system_context():
        db.add(PlatformCheckoutAttempt(
            organization_id=tenant.organization.id, plan_code="starter", catalog_version=1, fingerprint="x" * 64,
            amount_minor=79900, currency="INR", billing_interval="month", billing_interval_count=1, seat_limit=3,
            provider="razorpay", mode="test", provider_plan_id="plan_X", status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=30)))
        db.commit()
    r = _start(client, tenant)
    assert r.status_code == 503 and fake.subscriptions == [] and fake.sub_lookups == []


def test_one_open_attempt_per_organization_is_enforced_by_the_database(db, tenant):
    def attempt(status):
        return PlatformCheckoutAttempt(
            organization_id=tenant.organization.id, plan_code="starter", catalog_version=1, fingerprint="f" * 64,
            amount_minor=79900, currency="INR", billing_interval="month", billing_interval_count=1, seat_limit=3,
            provider="razorpay", mode="test", status=status, provider_subscription_id=f"sub_{uuid.uuid4().hex[:14]}",
            expires_at=datetime.now(UTC))
    with system_context():
        db.add_all([attempt("failed"), attempt("expired"), attempt("created")])
        db.commit()  # closed attempts never conflict
        db.add(attempt("unknown"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_provider_plan_terms_are_unique_per_mode(db):
    def row(mode):
        return PlatformProviderPlan(provider="razorpay", mode=mode, plan_code="starter", fingerprint="a" * 64,
                                    amount_minor=1, currency="INR", billing_interval="month", billing_interval_count=1,
                                    status="pending", reconcile_ref=uuid.uuid4().hex)
    with system_context():
        db.add_all([row("test"), row("live")])
        db.commit()
        db.add(row("test"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_one_organizations_checkout_never_blocks_another(client, db, tenant, fake, published):
    from backend.tests.conftest import Tenant

    _start(client, tenant, plan="starter")
    other = Tenant(db, uuid.uuid4().hex[:8])
    r = _start(client, other, plan="growth")
    assert r.status_code == 201
    [mine] = _attempts(db, tenant.organization.id)
    [theirs] = _attempts(db, other.organization.id)
    assert mine.organization_id == tenant.organization.id and theirs.organization_id == other.organization.id


# --- the provider module itself (request bodies, timeouts, error classes) -------------------------


class _Resource:
    def __init__(self, result=None, exc=None):
        self.calls, self.result, self.exc = [], result, exc

    def create(self, data, **kw):
        self.calls.append((data, kw))
        if self.exc:
            raise self.exc
        return self.result


class _Client:
    def __init__(self, plan=None, subscription=None):
        self.plan, self.subscription, self.retry_enabled = plan, subscription, True


def test_provider_builds_razorpay_requests_with_timeout_and_no_retry(monkeypatch):
    plan_res = _Resource(result={"id": "plan_ABC"})
    sub_res = _Resource(result={"id": "sub_ABC"})
    client = _Client(plan_res, sub_res)
    seen = []
    monkeypatch.setattr(razorpay_gateway, "_get_client", lambda creds: seen.append(creds) or client)
    provider.create_plan(name="Starter", description="d", amount_minor=79900, currency="INR", interval="month",
                         interval_count=1, notes={"rooman_plan_ref": "r1"})
    provider.create_subscription(plan_id="plan_ABC", total_count=120, expire_by=1800000000, notes={"a": "b"})
    assert plan_res.calls[0][0] == {"period": "monthly", "interval": 1, "notes": {"rooman_plan_ref": "r1"},
                                    "item": {"name": "Starter", "amount": 79900, "currency": "INR", "description": "d"}}
    assert sub_res.calls[0][0] == {"plan_id": "plan_ABC", "total_count": 120, "quantity": 1, "customer_notify": True,
                                   "expire_by": 1800000000, "notes": {"a": "b"}}
    assert all(kw == {"timeout": settings.PLATFORM_RAZORPAY_TIMEOUT_SECONDS} for _, kw in plan_res.calls + sub_res.calls)
    assert client.retry_enabled is False
    assert all(c.key_id == KEY_ID and c.key_secret == SECRET for c in seen)  # Rooman's keys only


def test_provider_classifies_failures(monkeypatch):
    import razorpay
    import requests

    cases = [(razorpay.errors.BadRequestError("bad"), provider.ProviderRejected),
             (razorpay.errors.ServerError("5xx"), provider.ProviderUnavailable),
             (requests.exceptions.Timeout("slow"), provider.ProviderUnavailable),
             (requests.exceptions.ConnectionError("down"), provider.ProviderUnavailable),
             (ValueError("not json"), provider.ProviderUnavailable)]
    for exc, expected in cases:
        client = _Client(plan=_Resource(exc=exc))
        monkeypatch.setattr(razorpay_gateway, "_get_client", lambda creds, c=client: c)
        with pytest.raises(expected):
            provider.create_plan(name="S", description="d", amount_minor=1, currency="INR", interval="month",
                                 interval_count=1, notes={})
    client = _Client(plan=_Resource(result={"no": "id"}))
    monkeypatch.setattr(razorpay_gateway, "_get_client", lambda creds: client)
    with pytest.raises(provider.ProviderUnavailable):
        provider.create_plan(name="S", description="d", amount_minor=1, currency="INR", interval="month",
                             interval_count=1, notes={})

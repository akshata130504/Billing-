"""Stage 6: the sandbox TEST plan - a controlled Razorpay Test Mode purchase without publishing a commercial plan.

The shipped catalog is used as is (Starter / Growth / Business stay drafts; `sandbox_foundation` is the only
sandbox plan). Razorpay is never called: plan / subscription creation and the fetches are fakes, and the SDK
client fails the test if anything reaches it.
"""
import copy
import json
import uuid

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.exceptions import ConflictError
from backend.app.core.plan_catalog import CATALOG_PATH, SANDBOX_MAX_AMOUNT_MINOR, CatalogError, catalog, load_catalog
from backend.app.core.tenant_context import system_context
from backend.app.models import MemberRole, PlatformCheckoutAttempt, PlatformPayment, PlatformNotification, PlatformPaymentReview, PlatformProviderPlan, PlatformWebhookEvent
from backend.app.services import (
    platform_checkout_service as checkout,
    platform_payment_service as payments,
    platform_razorpay as provider,
    platform_subscription_service as subs,
    razorpay_gateway,
)
from backend.tests.test_platform_checkout import KEY_ID, SECRET, _catalog
from backend.tests.test_platform_payment_verification import (
    BUSINESS_ONLY,
    GROWTH_EXTRA,
    STARTER_EXTRA,
    WEBHOOK_SECRET,
    Razorpay,
    _attempt,
    _expired_trial,
    _ledger,
    _modules,
    _org,
    _pay,
    _verify,
    _webhook,
    _write,
)

API = "/api/v1"
URL = f"{API}/subscription-checkout"
SANDBOX_LIST = f"{URL}/sandbox-plans"
SANDBOX = "sandbox_foundation"
LIVE_KEY_ID = "rzp_live_RoomanLiveDummy"


@pytest.fixture(autouse=True)
def isolated(db, monkeypatch):
    with system_context():
        for model in (PlatformNotification, PlatformPaymentReview, PlatformPayment, PlatformWebhookEvent, PlatformCheckoutAttempt, PlatformProviderPlan):
            db.query(model).delete()
        db.commit()
    # The local Test Mode setup the sandbox needs. Each test switches one condition off.
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", SECRET)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", False)
    monkeypatch.setattr(settings, "PLATFORM_SANDBOX_PLANS_ENABLED", True)

    def no_network(*a, **k):
        raise AssertionError("a test reached the real Razorpay client")

    monkeypatch.setattr(razorpay_gateway, "_get_client", no_network)


@pytest.fixture
def rzp(monkeypatch):
    fake = Razorpay()
    for name in ("create_plan", "create_subscription", "find_plan", "find_subscription", "fetch_subscription", "fetch_payment",
                 "list_paid_subscription_invoices"):
        monkeypatch.setattr(provider, name, getattr(fake, name))
    return fake


def _start(client, tenant, plan=SANDBOX, **extra):
    return client.post(URL, json={"plan_code": plan, **extra}, headers=tenant.headers())


def _detail(resp):
    return resp.json()["error"].get("details", {}).get("code")


def _sandbox_codes(client, tenant):
    r = client.get(SANDBOX_LIST, headers=tenant.headers())
    assert r.status_code == 200, r.text
    return {p["code"]: p for p in r.json()["plans"]}


def _provider_plans(db):
    with system_context():
        db.expire_all()
        return db.scalars(select(PlatformProviderPlan)).all()


# --- the catalog -----------------------------------------------------------------------------------


def test_shipped_catalog_keeps_commercial_plans_untouched_and_one_sandbox_plan_apart():
    cat = catalog()
    assert cat.published_plans() == ()  # nothing is sold commercially
    assert [p.code for p in cat.sandbox_plans()] == [SANDBOX]
    expected = {"starter": (79900, 3, ("foundation",)), "growth": (129900, 5, ("foundation", "service_operations")),
                "business": (179900, 10, ("foundation", "service_operations", "recurring_revenue"))}
    for code, (amount, seats, bundles) in expected.items():
        plan = cat.plan(code)
        assert (plan.status, plan.price.amount_minor, plan.seat_limit, plan.bundles, plan.tax_treatment) == (
            "draft", amount, seats, bundles, None)
        assert plan.approved_by is None and not plan.is_sandbox
    sandbox = cat.plan(SANDBOX)
    assert sandbox.is_sandbox and not sandbox.is_published
    assert sandbox.name.startswith("Sandbox") and "TEST MODE" in sandbox.description
    assert sandbox.price.amount_minor == 100 and sandbox.price.currency == "INR" and sandbox.price.interval == "month"
    assert sandbox.bundles == ("foundation",) and sandbox.modules == cat.plan("starter").modules
    assert sandbox.tax_treatment is None and sandbox.approved_by is None and sandbox.approved_on is None


def _raw():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _sandbox_raw(raw):
    return next(p for p in raw["plans"] if p["code"] == SANDBOX)


@pytest.mark.parametrize("change, message", [
    (lambda p: p.update(status="draft"), "status 'sandbox' and a 'sandbox_' code go together"),
    (lambda p: p.update(status="published", tax_treatment="exclusive", approved_by="x", approved_on="2026-10-13"),
     "status 'sandbox' and a 'sandbox_' code go together"),
    (lambda p: p.update(name="Foundation Test"), "name must start with 'Sandbox'"),
    (lambda p: p["price"].update(amount_minor=SANDBOX_MAX_AMOUNT_MINOR + 1), "costs at most"),
    (lambda p: p.update(tax_treatment="inclusive"), "has no tax_treatment"),
    (lambda p: p.update(approved_by="Someone", approved_on="2026-10-13"), "never commercially approved"),
    (lambda p: p.update(bundles=["service_operations"]), "requires bundle foundation"),  # bundle rules still apply
    (lambda p: p.update(bundles=["foundation", "recurring_revenue"], code="sandbox_x") or None, None),
])
def test_catalog_validates_sandbox_plans(change, message):
    raw = _raw()
    change(_sandbox_raw(raw))
    if message is None:
        load_catalog(raw)  # a valid second sandbox shape still loads
        return
    with pytest.raises(CatalogError, match=message):
        load_catalog(raw)


def test_a_commercial_plan_cannot_use_the_sandbox_prefix():
    raw = _raw()
    starter = copy.deepcopy(next(p for p in raw["plans"] if p["code"] == "starter"))
    starter["code"] = "sandbox_starter"
    raw["plans"].append(starter)
    with pytest.raises(CatalogError, match="go together"):
        load_catalog(raw)


# --- when the sandbox is allowed ------------------------------------------------------------------


def test_sandbox_is_allowed_only_with_every_condition(monkeypatch):
    assert provider.sandbox_readiness() is None
    for setting, value, reason in [
        ("PLATFORM_SANDBOX_PLANS_ENABLED", False, "SANDBOX_DISABLED"),
        ("ENVIRONMENT", "production", "SANDBOX_NOT_ALLOWED_IN_THIS_ENVIRONMENT"),
        ("ENVIRONMENT", "staging", "SANDBOX_NOT_ALLOWED_IN_THIS_ENVIRONMENT"),
        ("ENVIRONMENT", "demo", "SANDBOX_NOT_ALLOWED_IN_THIS_ENVIRONMENT"),
        ("PLATFORM_RAZORPAY_KEY_ID", LIVE_KEY_ID, "SANDBOX_NEEDS_TEST_KEYS"),
    ]:
        with monkeypatch.context() as m:
            m.setattr(settings, setting, value)
            assert provider.sandbox_readiness() == reason, setting
    with monkeypatch.context() as m:
        m.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", "")
        m.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", "")
        assert provider.sandbox_readiness() == "PAYMENTS_NOT_CONFIGURED"


def test_the_flag_is_off_by_default():
    from backend.app.core.config import Settings

    assert Settings.model_fields["PLATFORM_SANDBOX_PLANS_ENABLED"].default is False


def test_live_keys_never_allow_the_sandbox_even_with_live_checkout_allowed(monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", LIVE_KEY_ID)
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", True)
    assert provider.checkout_readiness() is None  # live checkout itself would run
    assert provider.sandbox_readiness() == "SANDBOX_NEEDS_TEST_KEYS"
    assert not subs.plan_on_sale(catalog().plan(SANDBOX))


# --- listing --------------------------------------------------------------------------------------


def test_sandbox_plan_is_never_in_the_public_catalog(client):
    r = client.get(f"{API}/public/plans")
    assert r.status_code == 200 and r.json()["plans"] == []
    assert client.get(f"{API}/public/plans/{SANDBOX}").status_code == 404


def test_members_see_the_sandbox_plan_marked_as_test_only(client, tenant):
    plans = _sandbox_codes(client, tenant)
    assert list(plans) == [SANDBOX]
    plan = plans[SANDBOX]
    assert plan["sandbox"] is True and plan["purchasable"] is True and plan["tax_treatment"] is None
    assert plan["price"] == {"amount_minor": 100, "currency": "INR", "interval": "month", "interval_count": 1}
    assert {m["key"] for m in plan["modules"] if not m["base"]} == STARTER_EXTRA
    assert client.get(SANDBOX_LIST).status_code == 401


@pytest.mark.parametrize("setting, value", [
    ("PLATFORM_SANDBOX_PLANS_ENABLED", False),
    ("ENVIRONMENT", "production"),
    ("PLATFORM_RAZORPAY_KEY_ID", LIVE_KEY_ID),
])
def test_sandbox_plan_is_hidden_unless_allowed(client, tenant, monkeypatch, setting, value):
    monkeypatch.setattr(settings, setting, value)
    assert _sandbox_codes(client, tenant) == {}


def test_sandbox_plan_is_shown_but_not_purchasable_without_the_webhook(client, tenant, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_WEBHOOK_SECRET", "")
    assert _sandbox_codes(client, tenant)[SANDBOX]["purchasable"] is False


# --- checkout refuses everything outside the sandbox ----------------------------------------------


@pytest.mark.parametrize("setting, value, status, code", [
    ("PLATFORM_SANDBOX_PLANS_ENABLED", False, 409, "PLAN_NOT_AVAILABLE"),
    ("ENVIRONMENT", "production", 409, "PLAN_NOT_AVAILABLE"),
    ("ENVIRONMENT", "staging", 409, "PLAN_NOT_AVAILABLE"),
    ("PLATFORM_RAZORPAY_KEY_ID", LIVE_KEY_ID, 409, "PLAN_NOT_AVAILABLE"),
    ("PLATFORM_RAZORPAY_WEBHOOK_SECRET", "", 503, "CHECKOUT_NOT_READY"),
])
def test_sandbox_checkout_is_refused_outside_the_sandbox(client, db, tenant, rzp, monkeypatch, setting, value, status, code):
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", True)  # even with live selling switched on
    monkeypatch.setattr(settings, setting, value)
    r = _start(client, tenant)
    assert r.status_code == status, r.text
    assert (_detail(r) if status == 409 else r.json()["error"]["code"]) == code
    assert rzp.plans == [] and rzp.subscriptions == [] and _provider_plans(db) == []


def test_commercial_drafts_stay_unavailable_with_the_sandbox_on(client, tenant, rzp):
    for code in ("starter", "growth", "business"):
        r = _start(client, tenant, plan=code)
        assert r.status_code == 409 and _detail(r) == "PLAN_NOT_AVAILABLE", code
    assert rzp.plans == []


def test_browser_cannot_supply_terms_or_open_the_sandbox(client, tenant, rzp, monkeypatch):
    for extra in ({"amount_minor": 1}, {"modules": ["projects"]}, {"seat_limit": 50}, {"interval": "year"},
                  {"sandbox": True}, {"currency": "USD"}):
        assert _start(client, tenant, **extra).status_code == 422, extra
    monkeypatch.setattr(settings, "PLATFORM_SANDBOX_PLANS_ENABLED", False)
    assert _start(client, tenant, sandbox=True).status_code == 422  # a browser cannot switch the sandbox on
    assert rzp.plans == []


@pytest.mark.parametrize("role", [MemberRole.ADMIN, MemberRole.FINANCE, MemberRole.VIEWER])
def test_only_the_owner_can_buy_the_sandbox_plan(client, tenant, rzp, role):
    headers = tenant.headers_for_role(role)
    assert client.get(SANDBOX_LIST, headers=headers).status_code == 200  # every member may see it
    r = client.post(URL, json={"plan_code": SANDBOX}, headers=headers)
    assert r.status_code == 403
    assert rzp.plans == [] and rzp.subscriptions == []


# --- the purchase, through the normal Stage 3 / 4 path ---------------------------------------------


def test_sandbox_purchase_is_verified_and_grants_only_its_modules(client, db, tenant, rzp):
    _expired_trial(db, tenant)
    r = _start(client, tenant)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["plan"]["code"] == SANDBOX and body["plan"]["sandbox"] is True and body["plan"]["amount_minor"] == 100
    assert body["razorpay_key_id"] == KEY_ID and SECRET not in r.text
    # Provider requests come from the catalog and are marked as sandbox at Razorpay too.
    [plan_call] = rzp.plans
    assert plan_call["amount_minor"] == 100 and plan_call["notes"]["catalog_plan"] == SANDBOX
    assert plan_call["notes"]["rooman_sandbox"] == "true" and plan_call["name"].startswith("Sandbox")
    [sub_call] = rzp.subscriptions
    assert sub_call["notes"]["rooman_sandbox"] == "true" and sub_call["notes"]["plan_code"] == SANDBOX
    attempt = _attempt(db, body["checkout_attempt_id"])
    assert (attempt.mode, attempt.plan_code, attempt.amount_minor, attempt.seat_limit) == ("test", SANDBOX, 100, 3)
    [row] = _provider_plans(db)
    assert (row.mode, row.plan_code) == ("test", SANDBOX)

    # Opening checkout and an authorization unlock nothing.
    assert _write(client, tenant).json()["error"]["code"] == "TRIAL_EXPIRED"
    sid, pid = _pay(rzp, db, body, status="authenticated", paid_count=0, payment_status="authorized")
    assert _verify(client, tenant, pid, sid).json()["status"] == "pending"
    assert _org(db, tenant.organization.id).module_access == "unrestricted"

    # Razorpay confirms the captured first charge: the sandbox plan starts with exactly its contents.
    sid, pid = _pay(rzp, db, body)
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 200 and r.json()["status"] == "active", r.text
    org = _org(db, tenant.organization.id)
    assert org.module_access == "entitled" and org.seat_limit == 3
    assert _modules(db, org.id) == STARTER_EXTRA
    assert not (_modules(db, org.id) & (GROWTH_EXTRA - STARTER_EXTRA)) and not (_modules(db, org.id) & BUSINESS_ONLY)
    assert _write(client, tenant).status_code == 201
    for path in ("/projects", "/subscriptions"):  # Growth / Business modules stay locked (Stage 0 enforcement)
        resp = client.get(f"{API}{path}", headers=tenant.headers())
        assert resp.status_code == 403 and resp.json()["error"]["code"] == "FEATURE_NOT_ENTITLED", path
    me = client.get(f"{API}/auth/me", headers=tenant.headers()).json()
    assert me["subscription"]["plan_code"] == SANDBOX and me["subscription"]["sandbox"] is True
    sub = subs.get_subscription(db, org.id)
    assert sub.provider_mode == "test" and sub.provider_subscription_id == sid


def test_sandbox_purchase_activates_from_a_signed_webhook_once(client, db, tenant, rzp):
    body = _start(client, tenant).json()
    sid, pid = _pay(rzp, db, body)
    event_id = f"evt_{uuid.uuid4().hex}"
    r = _webhook(client, "subscription.charged", sid, pid, event_id=event_id)
    assert r.status_code == 200 and r.json()["status"] == "processed", r.text
    assert _modules(db, tenant.organization.id) == STARTER_EXTRA
    again = _webhook(client, "subscription.charged", sid, pid, event_id=event_id)
    assert again.json()["status"] == "duplicate"
    assert len(_ledger(db)) == 1 and subs.get_subscription(db, tenant.organization.id).provider_paid_count == 1


def test_unsigned_or_wrongly_signed_events_activate_nothing(client, db, tenant, rzp):
    body = _start(client, tenant).json()
    sid, pid = _pay(rzp, db, body)
    r = _webhook(client, "subscription.charged", sid, pid, secret="not-the-webhook-secret")
    assert r.status_code == 400 and _ledger(db) == []
    assert _org(db, tenant.organization.id).module_access == "unrestricted"
    r = _verify(client, tenant, pid, sid, signature="ab" * 32)
    assert r.status_code == 400 and r.json()["error"]["code"] == "PAYMENT_SIGNATURE_INVALID"
    assert subs.get_subscription(db, tenant.organization.id) is None


def test_sandbox_switched_off_before_payment_is_not_activated(client, db, tenant, rzp, monkeypatch):
    body = _start(client, tenant).json()
    sid, pid = _pay(rzp, db, body)
    monkeypatch.setattr(settings, "PLATFORM_SANDBOX_PLANS_ENABLED", False)
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PAYMENT_NEEDS_REVIEW"
    assert _org(db, tenant.organization.id).module_access == "unrestricted" and _modules(db, tenant.organization.id) == set()


# --- test and live never mix ------------------------------------------------------------------------


def test_live_keys_cannot_complete_a_sandbox_checkout(client, db, tenant, rzp, monkeypatch):
    body = _start(client, tenant).json()
    sid, pid = _pay(rzp, db, body)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", LIVE_KEY_ID)
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", True)
    r = _webhook(client, "subscription.charged", sid, pid)
    assert r.status_code == 200 and r.json()["status"] == "needs_review"
    assert rzp.fetches == []  # refused before asking Razorpay with the other mode's keys
    assert subs.get_subscription(db, tenant.organization.id) is None
    assert _attempt(db, body["checkout_attempt_id"]).status == "created"


def test_test_mode_events_cannot_complete_a_live_checkout(client, db, tenant, rzp, monkeypatch):
    cat = _catalog(starter="published")
    for module in (subs, checkout, payments):
        monkeypatch.setattr(module, "catalog", lambda: cat)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", LIVE_KEY_ID)
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", True)
    body = _start(client, tenant, plan="starter").json()
    assert _attempt(db, body["checkout_attempt_id"]).mode == "live"
    sid, pid = _pay(rzp, db, body)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", KEY_ID)  # back to Test Mode keys
    r = _webhook(client, "subscription.charged", sid, pid)
    assert r.json()["status"] == "needs_review"
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PAYMENT_NEEDS_REVIEW"
    assert subs.get_subscription(db, tenant.organization.id) is None


def test_sandbox_and_commercial_provider_plans_never_overlap(client, db, tenant, rzp, monkeypatch):
    from backend.tests.conftest import Tenant

    cat = _catalog(starter="published")
    for module in (subs, checkout, payments):
        monkeypatch.setattr(module, "catalog", lambda: cat)
    assert _start(client, tenant).status_code == 201  # sandbox
    other = Tenant(db, uuid.uuid4().hex[:8])
    assert _start(client, other, plan="starter").status_code == 201  # commercial, same Test Mode keys
    rows = {r.plan_code: r for r in _provider_plans(db)}
    assert set(rows) == {SANDBOX, "starter"}
    assert rows[SANDBOX].fingerprint != rows["starter"].fingerprint
    assert rows[SANDBOX].provider_plan_id != rows["starter"].provider_plan_id
    assert {r.mode for r in rows.values()} == {"test"}
    # A sandbox provider plan is never resolved in Live Mode, whatever the caller passes.
    with pytest.raises(ConflictError) as exc:
        checkout.resolve_provider_plan(db, cat.plan(SANDBOX), "live")
    assert exc.value.details["code"] == "PLAN_NOT_AVAILABLE"
    assert len(rzp.plans) == 2 and len(_provider_plans(db)) == 2


def test_a_sandbox_subscription_is_not_renewed_outside_the_sandbox(db, tenant, monkeypatch):
    # The same `activate` the verified payment path calls; renewals go through the same plan rule.
    sub = subs.activate(db, tenant.organization.id, SANDBOX)
    db.commit()
    assert sub.plan_code == SANDBOX and _modules(db, tenant.organization.id) == STARTER_EXTRA
    assert subs.summary(db, tenant.organization.id)["sandbox"] is True
    monkeypatch.setattr(settings, "PLATFORM_SANDBOX_PLANS_ENABLED", False)
    with pytest.raises(ConflictError) as exc:
        subs.renew(db, tenant.organization.id)
    assert exc.value.details["code"] == "PLAN_NOT_AVAILABLE"
    db.rollback()

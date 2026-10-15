"""Rooman Billing's own plan catalog (core/plan_catalog.json, core/plan_catalog.py) and its read-only API.

The catalog is validated against the module registry when it loads; only published (approved) plans
are ever shown publicly; nothing can modify it through the API; and reading it never changes an
organization's access.
"""
import copy
import json

import pytest

from backend.app.api.v1.endpoints import platform_plans as public_api
from backend.app.core.config import settings
from backend.app.core.entitlements import registry
from backend.app.core.plan_catalog import CATALOG_PATH, CatalogError, catalog, load_catalog, plan_modules
from backend.app.models import Organization
from backend.app.models.platform import PlatformRole
from backend.tests.test_platform_console import Staff

API = "/api/v1"


def _raw():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _plan(raw, code):
    return next(p for p in raw["plans"] if p["code"] == code)


def _bundle(raw, key):
    return next(b for b in raw["bundles"] if b["key"] == key)


def _rejects(raw, message):
    with pytest.raises(CatalogError, match=message):
        load_catalog(raw)


def _published(raw, code, **extra):
    p = _plan(raw, code)
    p.update(status="published", tax_treatment="exclusive", approved_by="Product owner", approved_on="2026-10-12", **extra)
    return raw


# --- the shipped catalog --------------------------------------------------------------------------


def _commercial(cat):
    return [p for p in cat.plans if not p.is_sandbox]


def test_shipped_catalog_has_the_three_draft_candidate_plans():
    cat = catalog()
    commercial = _commercial(cat)
    assert [p.code for p in commercial] == ["starter", "growth", "business"]
    # The only other plan is the sandbox TEST plan (test_platform_sandbox_plans.py), never sold commercially.
    assert [p.code for p in cat.plans if p.is_sandbox] == ["sandbox_foundation"]
    assert all(p.status == "draft" and not p.is_published for p in commercial)
    assert cat.published_plans() == ()
    prices = {p.code: (p.price.amount_minor, p.price.currency, p.price.interval, p.price.interval_count) for p in commercial}
    assert prices == {"starter": (79900, "INR", "month", 1), "growth": (129900, "INR", "month", 1),
                      "business": (179900, "INR", "month", 1)}
    assert {p.code: p.seat_limit for p in commercial} == {"starter": 3, "growth": 5, "business": 10}
    # Tax display and approval are still open decisions.
    assert all(p.tax_treatment is None and p.approved_by is None for p in cat.plans)


def test_plans_are_foundation_plus_cumulative_bundles():
    cat = catalog()
    assert {p.code: p.bundles for p in _commercial(cat)} == {
        "starter": ("foundation",),
        "growth": ("foundation", "service_operations"),
        "business": ("foundation", "service_operations", "recurring_revenue"),
    }
    starter, growth, business = (set(cat.plan(c).modules) for c in ("starter", "growth", "business"))
    assert registry().base_keys <= starter < growth < business
    assert {"customer_portal", "collections", "reconciliation", "expenses", "projects", "timesheets"} == growth - starter
    assert {"subscriptions", "dunning", "customer_lifecycle", "automation"} == business - growth


def test_catalog_is_consistent_with_the_module_registry():
    cat = catalog()
    reg = registry()
    offered = {m for b in cat.bundles for m in b.modules}
    assert offered | set(cat.not_offered) == reg.all_keys  # every module classified exactly once
    assert not offered & set(cat.not_offered)
    assert set(cat.not_offered) == {"ai_billing", "platforms"}
    for plan in cat.plans:
        assert set(plan.modules) <= reg.all_keys
        assert not set(plan.modules) & set(cat.not_offered)
        assert plan_modules(plan) == frozenset(plan.modules) - reg.base_keys


def test_module_dependencies_hold_in_every_plan():
    for plan in catalog().plans:
        mods = set(plan.modules)
        if "timesheets" in mods:
            assert "projects" in mods  # modules.json requires
        if "dunning" in mods:
            assert "subscriptions" in mods  # catalog packaging rule


# --- validation -----------------------------------------------------------------------------------


def test_unknown_module_is_rejected():
    raw = _raw()
    _bundle(raw, "service_operations")["modules"].append("telepathy")
    _rejects(raw, "unknown module 'telepathy'")


def test_module_in_two_bundles_is_rejected():
    raw = _raw()
    _bundle(raw, "recurring_revenue")["modules"].append("expenses")
    _rejects(raw, "module 'expenses' is in bundles")


def test_unclassified_module_is_rejected():
    raw = _raw()
    del raw["not_offered"]["platforms"]
    _rejects(raw, "platforms are in no bundle")


def test_not_offered_module_cannot_also_be_sold():
    raw = _raw()
    raw["not_offered"]["quotes"] = "Not ready"
    _rejects(raw, "both offered and not_offered")


def test_plan_with_unknown_bundle_is_rejected():
    raw = _raw()
    _plan(raw, "growth")["bundles"].append("everything")
    _rejects(raw, "unknown bundle 'everything'")


def test_bundle_dependency_is_enforced():
    raw = _raw()
    _plan(raw, "growth")["bundles"] = ["service_operations"]
    _rejects(raw, "bundle service_operations requires bundle foundation")


def test_plan_without_base_modules_is_rejected():
    raw = _raw()
    _bundle(raw, "service_operations")["requires"] = []
    _plan(raw, "growth")["bundles"] = ["service_operations"]
    _rejects(raw, "leaves out base module")


def test_registry_requirement_is_enforced():
    raw = _raw()
    _bundle(raw, "service_operations")["modules"].remove("projects")
    _bundle(raw, "recurring_revenue")["modules"].append("projects")
    _rejects(raw, "growth leaves out required module\\(s\\) projects")


def test_dunning_without_subscriptions_is_rejected():
    raw = _raw()
    _bundle(raw, "recurring_revenue")["modules"].remove("dunning")
    _bundle(raw, "service_operations")["modules"].append("dunning")
    _rejects(raw, "dunning needs subscriptions")


@pytest.mark.parametrize("amount", [0, -100, 799.0, "79900", True, 10**10])
def test_invalid_price_is_rejected(amount):
    raw = _raw()
    _plan(raw, "starter")["price"]["amount_minor"] = amount
    _rejects(raw, "starter price")


@pytest.mark.parametrize("field, value, message", [
    ("currency", "USD", "currency must be one of INR"),
    ("currency", "inr", "currency must be one of INR"),
    ("interval", "week", "interval must be one of month, year"),
    ("interval_count", 0, "interval_count must be between 1 and 12"),
])
def test_invalid_currency_or_interval_is_rejected(field, value, message):
    raw = _raw()
    _plan(raw, "starter")["price"][field] = value
    _rejects(raw, message)


@pytest.mark.parametrize("seats", [0, -1, 10001, "5", 2.5, None])
def test_invalid_seat_limit_is_rejected(seats):
    raw = _raw()
    _plan(raw, "growth")["seat_limit"] = seats
    _rejects(raw, "growth seat_limit")


@pytest.mark.parametrize("status", ["live", "", None])
def test_unknown_status_is_rejected(status):
    raw = _raw()
    _plan(raw, "starter")["status"] = status
    _rejects(raw, "status must be one of")


def test_published_plan_needs_tax_treatment_and_approval():
    raw = _raw()
    _plan(raw, "starter")["status"] = "published"
    _rejects(raw, "needs a tax_treatment")
    raw = _raw()
    _plan(raw, "starter").update(status="published", tax_treatment="exclusive")
    _rejects(raw, "needs approved_by and approved_on")
    cat = load_catalog(_published(_raw(), "starter"))
    assert [p.code for p in cat.published_plans()] == ["starter"]


def test_duplicate_or_invalid_plan_code_is_rejected():
    raw = _raw()
    raw["plans"].append(copy.deepcopy(_plan(raw, "starter")))
    _rejects(raw, "duplicate plan code")
    raw = _raw()
    _plan(raw, "starter")["code"] = "Starter Plan"
    _rejects(raw, "invalid plan code")


def test_invalid_tax_treatment_is_rejected():
    raw = _raw()
    _plan(raw, "starter")["tax_treatment"] = "gst"
    _rejects(raw, "tax_treatment must be null or one of")


# --- public API -----------------------------------------------------------------------------------


@pytest.fixture
def published_starter(monkeypatch):
    raw = _published(_raw(), "starter")
    _plan(raw, "business")["status"] = "retired"
    cat = load_catalog(raw)
    monkeypatch.setattr(public_api, "catalog", lambda: cat)
    return cat


def test_public_catalog_shows_no_draft_plans(client):
    r = client.get(f"{API}/public/plans")
    assert r.status_code == 200, r.text
    assert r.json() == {"catalog_version": catalog().version, "plans": []}
    for code in ("starter", "growth", "business", "nope"):
        assert client.get(f"{API}/public/plans/{code}").status_code == 404


def test_public_catalog_shows_only_published_plans(client, published_starter):
    body = client.get(f"{API}/public/plans").json()
    assert [p["code"] for p in body["plans"]] == ["starter"]
    starter = body["plans"][0]
    assert starter["price"] == {"amount_minor": 79900, "currency": "INR", "interval": "month", "interval_count": 1}
    assert starter["tax_treatment"] == "exclusive" and starter["seat_limit"] == 3
    assert starter["purchasable"] is False  # checkout is not configured in tests by default
    assert [b["key"] for b in starter["bundles"]] == ["foundation"]
    assert {m["key"] for m in starter["modules"]} == set(catalog().plan("starter").modules)
    assert "status" not in starter and "approved_by" not in starter
    assert client.get(f"{API}/public/plans/starter").json()["code"] == "starter"
    assert client.get(f"{API}/public/plans/growth").status_code == 404  # draft
    assert client.get(f"{API}/public/plans/business").status_code == 404  # retired


@pytest.fixture
def checkout_ready(monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", "rzp_test_RoomanCatalogDummy")
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", "dummy-rooman-catalog-secret")
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_WEBHOOK_SECRET", "dummy-rooman-catalog-webhook")
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", False)


def _purchasable(client):
    return {p["code"]: p["purchasable"] for p in client.get(f"{API}/public/plans").json()["plans"]}


def test_published_plan_is_purchasable_only_when_checkout_is_ready(client, published_starter, checkout_ready):
    assert _purchasable(client) == {"starter": True}
    body = client.get(f"{API}/public/plans").text
    assert "dummy-rooman-catalog" not in body


@pytest.mark.parametrize("setting, value", [
    ("PLATFORM_RAZORPAY_KEY_ID", ""),
    ("PLATFORM_RAZORPAY_KEY_SECRET", ""),
    ("PLATFORM_RAZORPAY_WEBHOOK_SECRET", ""),
    ("PLATFORM_RAZORPAY_KEY_ID", "rzp_live_RoomanCatalogDummy"),  # live keys while live checkout is off
])
def test_plan_is_not_purchasable_when_checkout_is_not_ready(client, published_starter, checkout_ready, monkeypatch,
                                                            setting, value):
    monkeypatch.setattr(settings, setting, value)
    assert _purchasable(client) == {"starter": False}


def test_live_plan_is_purchasable_once_live_checkout_is_allowed(client, published_starter, checkout_ready, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", "rzp_live_RoomanCatalogDummy")
    monkeypatch.setattr(settings, "PLATFORM_CHECKOUT_ALLOW_LIVE", True)
    assert _purchasable(client) == {"starter": True}


def test_draft_plans_are_never_listed_even_when_checkout_is_ready(client, checkout_ready):
    assert _purchasable(client) == {}


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_catalog_cannot_be_modified_through_the_api(client, tenant, method):
    for path in ("/public/plans", "/public/plans/starter", "/platform/plans"):
        r = getattr(client, method)(f"{API}{path}", headers=tenant.headers())
        assert r.status_code == 405, (method, path, r.status_code)


# --- platform console -----------------------------------------------------------------------------


def test_platform_console_sees_every_plan_with_status(db):
    staff = Staff(db, PlatformRole.PLATFORM_SUPPORT)
    r = staff.get("/plans")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [(p["code"], p["status"], p["sandbox"]) for p in body["plans"]] == [
        ("starter", "draft", False), ("growth", "draft", False), ("business", "draft", False),
        ("sandbox_foundation", "sandbox", True)]
    assert [b["key"] for b in body["bundles"]] == ["foundation", "service_operations", "recurring_revenue"]
    assert {m["key"] for m in body["not_offered"]} == {"ai_billing", "platforms"}


def test_platform_catalog_needs_a_platform_session(client, tenant):
    assert client.get(f"{API}/platform/plans").status_code in (401, 403)
    assert client.get(f"{API}/platform/plans", headers=tenant.headers()).status_code in (401, 403)


# --- no side effects on organizations ------------------------------------------------------------


def test_reading_the_catalog_changes_no_organization_access(client, db, tenant, published_starter):
    before = client.get(f"{API}/auth/me", headers=tenant.headers()).json()
    client.get(f"{API}/public/plans")
    client.get(f"{API}/public/plans/starter")
    db.expire_all()
    org = db.get(Organization, tenant.organization.id)
    assert org.module_access == "unrestricted" and org.seat_limit is None
    after = client.get(f"{API}/auth/me", headers=tenant.headers()).json()
    assert after["access"] == before["access"] and after["trial"] == before["trial"]

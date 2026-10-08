"""Tenant-application visual editor (global UI configuration): draft -> publish -> history.

Platform Administrators edit; Operations and Support may only look. Tenants read ONLY the
published configuration through GET /api/v1/ui-config. Content is a strictly typed document
(allow-listed keys, plain text, safe colours), never code/HTML/CSS.
"""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from backend.app.core import grant_scopes
from backend.app.core.config import settings
from backend.app.models.access_grants import GrantScope
from backend.app.models.app_ui import AppUiPage, AppUiVersion
from backend.app.models.platform import PlatformAuditLog
from backend.app.schemas.app_ui import KEYS, PAGE_SCHEMAS
from backend.app.services import app_ui_service
from backend.tests.test_platform_console import ADMIN, OPS, SUPPORT, Staff

P = "/app-ui/pages"
UI = "/api/v1/ui-config"
REPO = Path(__file__).resolve().parents[2]

# One valid, minimal edit per page key, and a second, different one (for version sequences).
EDITS = {
    "theme": ({"schema_version": 1, "brand_600": "#1d4ed8"}, {"schema_version": 1, "brand_600": "#7c3aed"}),
    "navigation": (
        {"schema_version": 1, "sections": [{"key": "workspace", "label": "Home",
                                            "items": [{"key": "overview", "label": "Dashboard"}]}]},
        {"schema_version": 1, "sections": [{"key": "revenue", "label": "Money",
                                            "items": [{"key": "invoices", "icon": "Receipt"}]}]},
    ),
    "overview": ({"schema_version": 1, "header": {"title": "Welcome back"}},
                 {"schema_version": 1, "kpis": [{"key": "mrr", "label": "Monthly recurring"}, {"key": "outstanding"}]}),
    "customers": ({"schema_version": 1, "columns": [{"key": "company", "hidden": True}]},
                  {"schema_version": 1, "stats": [{"key": "active", "label": "Live accounts"}]}),
    "invoices": ({"schema_version": 1, "kpis": [{"key": "paid", "label": "Collected"}]},
                 {"schema_version": 1, "empty": {"title": "Nothing billed yet"}}),
}


@pytest.fixture(autouse=True)
def _clean_app_ui(db):
    """App UI configuration is global (not per test tenant): start every test with nothing configured."""
    db.execute(delete(AppUiPage))
    db.execute(delete(AppUiVersion))
    db.commit()
    yield
    db.rollback()
    db.execute(delete(AppUiPage))
    db.execute(delete(AppUiVersion))
    db.commit()


@pytest.fixture
def admin(db):
    return Staff(db, ADMIN)


@pytest.fixture
def tenant_api():
    from backend.app.main import app

    return TestClient(app)  # the tenant host


def _state(staff, key):
    resp = staff.get(f"{P}/{key}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _rev(staff, key):
    draft = _state(staff, key)["draft"]
    return draft["revision"] if draft else 0


def _save(staff, key, content, revision=None):
    return staff.post(f"{P}/{key}/draft", {"content": content, "revision": _rev(staff, key) if revision is None else revision})


def _publish(staff, key, note="Test publish"):
    return staff.post(f"{P}/{key}/publish", {"revision": _rev(staff, key), "note": note})


def _save_and_publish(staff, key, content, note="Test publish"):
    assert _save(staff, key, content).status_code == 200
    resp = _publish(staff, key, note)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _audit(db, action, **filters):
    db.expire_all()
    stmt = select(PlatformAuditLog).where(PlatformAuditLog.action == action)
    for name, value in filters.items():
        stmt = stmt.where(getattr(PlatformAuditLog, name) == value)
    return db.scalars(stmt.order_by(PlatformAuditLog.occurred_at)).all()


def _drafts(db, key=None):
    db.expire_all()
    stmt = select(AppUiVersion).where(AppUiVersion.state == "draft")
    if key:
        stmt = stmt.where(AppUiVersion.page_key == key)
    return db.scalars(stmt).all()


def _tenant_ui(tenant_api, tenant, **headers):
    return tenant_api.get(UI, headers={**tenant.headers(), **headers})


# --- RBAC ------------------------------------------------------------------------------------------------------


def test_administrator_lists_pages_and_can_edit(admin):
    resp = admin.get(P)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["can_edit"] is True
    assert [i["key"] for i in body["items"]] == list(PAGE_SCHEMAS.keys())
    assert all(i["published_version"] is None and i["has_draft"] is False for i in body["items"])


@pytest.mark.parametrize("role", [OPS, SUPPORT])
def test_operations_and_support_are_read_only_and_denials_are_audited(db, admin, role):
    admin.step_up()
    _save_and_publish(admin, "overview", EDITS["overview"][0])
    assert _save(admin, "overview", EDITS["overview"][1]).status_code == 200
    staff = Staff(db, role)
    staff.step_up()  # even a fresh step-up does not grant writes

    listing = staff.get(P)
    assert listing.status_code == 200 and listing.json()["can_edit"] is False
    assert staff.get(f"{P}/overview").status_code == 200
    assert staff.get(f"{P}/overview").json()["draft"]["revision"] == 1  # they may preview
    assert staff.get(f"{P}/overview/compare").status_code == 200
    assert staff.get(f"{P}/overview/versions").status_code == 200
    assert staff.get(f"{P}/overview/versions/1").status_code == 200

    before = len(_audit(db, "PLATFORM_ACCESS_DENIED", platform_staff_id=staff.id))
    writes = [
        (f"{P}/overview/draft", {"content": EDITS["overview"][0], "revision": 1}),
        (f"{P}/overview/draft/discard", {}),
        (f"{P}/overview/publish", {"revision": 1}),
        (f"{P}/overview/versions/1/rollback", {}),
        (f"{P}/overview/versions/1/restore", {"revision": 1}),
    ]
    for path, body in writes:
        resp = staff.post(path, body)
        assert resp.status_code == 403, (path, resp.text)
        assert resp.json()["error"]["code"] != "STEP_UP_REQUIRED"
    denied = _audit(db, "PLATFORM_ACCESS_DENIED", platform_staff_id=staff.id)
    assert len(denied) - before == len(writes)
    # nothing changed
    state = _state(admin, "overview")
    assert state["draft"]["revision"] == 1 and state["published"]["version"] == 1


def test_anonymous_and_tenant_tokens_cannot_reach_the_editor(tenant):
    from backend.app.main import app

    anon = TestClient(app, base_url=settings.platform_origin)
    for path in (f"/api/v1/platform{P}", f"/api/v1/platform{P}/overview", f"/api/v1/platform{P}/overview/versions"):
        assert anon.get(path).status_code == 401
        assert anon.get(path, headers=tenant.headers()).status_code == 401
    assert anon.post(f"/api/v1/platform{P}/overview/draft", json={"content": {}, "revision": 0}).status_code in (401, 403)
    assert TestClient(app).post(f"/api/v1/platform{P}/overview/draft", headers=tenant.headers(),
                                json={"content": EDITS["overview"][0], "revision": 0}).status_code == 401


# --- tenant read endpoint ----------------------------------------------------------------------------------------


def test_ui_config_requires_a_tenant_session(tenant_api):
    assert tenant_api.get(UI).status_code == 401


def test_ui_config_serves_defaults_then_only_published_content(admin, tenant, tenant_api):
    first = _tenant_ui(tenant_api, tenant)
    assert first.status_code == 200, first.text
    assert first.json()["pages"] == {} and first.json()["versions"] == {}
    assert first.headers["cache-control"] == "private, no-cache"  # always revalidated (ETag), never stale
    etag = first.headers["etag"]
    assert etag and first.json()["etag"] in etag

    # a draft is never served
    assert _save(admin, "overview", {"schema_version": 1, "header": {"title": "Draft only title"}}).status_code == 200
    after_draft = _tenant_ui(tenant_api, tenant)
    assert after_draft.json()["pages"] == {} and "Draft only title" not in after_draft.text
    assert after_draft.headers["etag"] == etag
    assert _tenant_ui(tenant_api, tenant, **{"If-None-Match": etag}).status_code == 304

    admin.step_up()
    assert _publish(admin, "overview").status_code == 200
    live = _tenant_ui(tenant_api, tenant)
    assert live.json()["pages"]["overview"]["header"]["title"] == "Draft only title"
    assert live.json()["versions"] == {"overview": 1}
    assert live.headers["etag"] != etag
    assert _tenant_ui(tenant_api, tenant, **{"If-None-Match": etag}).status_code == 200  # stale tag -> full body
    not_modified = _tenant_ui(tenant_api, tenant, **{"If-None-Match": live.headers["etag"]})
    assert not_modified.status_code == 304 and not_modified.content == b""
    assert not_modified.headers["etag"] == live.headers["etag"]

    # a new draft on top of the live version is still invisible to tenants
    assert _save(admin, "overview", {"schema_version": 1, "header": {"title": "Next draft"}}).status_code == 200
    again = _tenant_ui(tenant_api, tenant)
    assert again.json()["pages"]["overview"]["header"]["title"] == "Draft only title"
    assert "Next draft" not in again.text and again.headers["etag"] == live.headers["etag"]


def test_ui_config_under_an_access_grant(db, tenant, tenant_api, monkeypatch):
    assert grant_scopes.required_scope("GET", UI) == GrantScope.READ_METADATA
    assert grant_scopes.required_scope("HEAD", UI) == GrantScope.READ_METADATA
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert grant_scopes.required_scope(method, UI) is None
    assert grant_scopes.required_scope("GET", "/api/v1/platform/app-ui/pages") is None

    from backend.app.services import access_grant_service
    from backend.tests.test_access_grants import _bearer, _granted

    monkeypatch.setattr("backend.app.services.email.send_email", lambda **kw: True)
    monkeypatch.setattr(access_grant_service, "send_alert", lambda *a, **kw: None)
    support = Staff(db, SUPPORT)
    _, token = _granted(support, tenant, tenant_api)
    resp = tenant_api.get(UI, headers=_bearer(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["pages"] == {}


# --- draft lifecycle (every page) -------------------------------------------------------------------------------


@pytest.mark.parametrize("key", KEYS["pages"])
def test_draft_save_conflict_compare_discard(admin, db, key):
    edit, other = EDITS[key]
    state = _state(admin, key)
    assert state["draft"] is None and state["published"] is None
    assert state["defaults"] == app_ui_service.default_content(key)

    saved = _save(admin, key, edit, revision=0)
    assert saved.status_code == 200, saved.text
    draft = saved.json()["draft"]
    assert draft["revision"] == 1 and draft["state"] == "draft" and draft["version"] is None
    assert draft["changes"]
    assert _audit(db, "APP_UI_DRAFT_SAVED", target_id=key)

    stale = _save(admin, key, other, revision=0)
    assert stale.status_code == 409
    assert stale.json()["error"]["details"]["current_revision"] == 1
    assert _save(admin, key, other, revision=5).status_code == 409

    compare = admin.get(f"{P}/{key}/compare").json()
    assert compare["has_draft"] is True and compare["changes"]
    assert all({"path", "published", "draft"} <= set(c) for c in compare["changes"])

    assert _save(admin, key, other, revision=1).json()["draft"]["revision"] == 2
    assert len(_drafts(db, key)) == 1

    discarded = admin.post(f"{P}/{key}/draft/discard")
    assert discarded.status_code == 200 and discarded.json()["draft"] is None
    assert _drafts(db, key) == []
    assert admin.post(f"{P}/{key}/draft/discard").status_code == 409
    assert admin.get(f"{P}/{key}/compare").json() == {"has_draft": False, "changes": []}
    assert _audit(db, "APP_UI_DRAFT_DISCARDED", target_id=key)


def test_unknown_page_key_is_404(admin):
    admin.step_up()
    for resp in (
        admin.get(f"{P}/billing"),
        admin.get(f"{P}/billing/compare"),
        admin.get(f"{P}/billing/versions"),
        admin.get(f"{P}/billing/versions/1"),
        admin.post(f"{P}/billing/draft", {"content": {"schema_version": 1}, "revision": 0}),
        admin.post(f"{P}/billing/draft/discard"),
        admin.post(f"{P}/billing/publish", {"revision": 1}),
        admin.post(f"{P}/billing/versions/1/rollback", {}),
        admin.post(f"{P}/billing/versions/1/restore", {"revision": 0}),
    ):
        assert resp.status_code == 404, resp.text


# --- publish ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", KEYS["pages"])
def test_publish_versions_and_audit(admin, db, tenant, tenant_api, key):
    edit, other = EDITS[key]
    assert _save(admin, key, edit).status_code == 200
    needs = _publish(admin, key)
    assert needs.status_code == 403 and needs.json()["error"]["code"] == "STEP_UP_REQUIRED"
    admin.step_up()
    assert admin.post(f"{P}/{key}/publish", {"revision": 2}).status_code == 409  # not the previewed revision

    first = _publish(admin, key, note="First look")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["draft"] is None and body["published"]["version"] == 1
    assert body["published"]["content"] == app_ui_service.validate_content(key, edit)
    assert _tenant_ui(tenant_api, tenant).json()["pages"][key] == body["published"]["content"]

    row = _audit(db, "APP_UI_PUBLISHED", target_id=key)[-1]
    assert row.platform_staff_id == admin.id and row.target_type == "app_ui_page"
    assert row.reason == "First look" and row.details["role"] == "platform_administrator"
    assert row.details["version"] == 1 and row.details["previous_version"] is None
    assert row.details["changes"] and all({"path", "old", "new"} <= set(c) for c in row.details["changes"])

    _save_and_publish(admin, key, other)
    third = _save_and_publish(admin, key, edit)
    assert third["published"]["version"] == 3
    assert [i["version"] for i in admin.get(f"{P}/{key}/versions").json()["items"]] == [3, 2, 1]
    assert _audit(db, "APP_UI_PUBLISHED", target_id=key)[-1].details["previous_version"] == 2
    listing = {i["key"]: i for i in admin.get(P).json()["items"]}
    assert listing[key]["published_version"] == 3 and listing[key]["has_draft"] is False


def test_publish_audit_records_old_and_new_values(admin, db):
    admin.step_up()
    _save_and_publish(admin, "overview", {"schema_version": 1, "header": {"title": "Old title"}})
    _save_and_publish(admin, "overview", {"schema_version": 1, "header": {"title": "New title"}}, note="Retitle")
    row = _audit(db, "APP_UI_PUBLISHED", target_id="overview")[-1]
    assert {"path": "header.title", "old": "Old title", "new": "New title"} in row.details["changes"]
    assert row.reason == "Retitle" and row.staff_role_snapshot


def test_identical_to_live_is_not_published(admin):
    admin.step_up()
    # never published: a draft equal to the defaults has nothing to publish
    assert _save(admin, "theme", {"schema_version": 1}).status_code == 200
    resp = _publish(admin, "theme")
    assert resp.status_code == 409
    assert _state(admin, "theme")["draft"] is not None  # the draft is kept
    assert admin.post(f"{P}/theme/draft/discard").status_code == 200
    # published: a draft equal to the live version has nothing to publish
    _save_and_publish(admin, "theme", EDITS["theme"][0])
    assert _save(admin, "theme", copy.deepcopy(EDITS["theme"][0])).status_code == 200
    assert _publish(admin, "theme").status_code == 409
    assert _state(admin, "theme")["published"]["version"] == 1


def test_publish_without_a_draft_is_409(admin):
    admin.step_up()
    assert admin.post(f"{P}/overview/publish", {"revision": 1}).status_code == 409


# --- rollback / restore -------------------------------------------------------------------------------------------


def test_rollback_creates_a_new_version_and_keeps_history(admin, db, tenant, tenant_api):
    admin.step_up()
    v1, v2 = EDITS["overview"]
    _save_and_publish(admin, "overview", v1)
    _save_and_publish(admin, "overview", v2)
    assert admin.post(f"{P}/overview/versions/2/rollback", {}).status_code == 409  # already live

    rolled = admin.post(f"{P}/overview/versions/1/rollback", {"note": "Back to v1"})
    assert rolled.status_code == 200, rolled.text
    published = rolled.json()["published"]
    assert published["version"] == 3 and published["based_on_version"] == 1
    assert published["content"] == app_ui_service.validate_content("overview", v1)
    assert _tenant_ui(tenant_api, tenant).json()["pages"]["overview"] == published["content"]
    assert admin.post(f"{P}/overview/versions/1/rollback", {}).status_code == 409  # its content is live now
    items = admin.get(f"{P}/overview/versions").json()["items"]
    assert [(i["version"], i["live"]) for i in items] == [(3, True), (2, False), (1, False)]
    assert admin.get(f"{P}/overview/versions/2").json()["content"] == app_ui_service.validate_content("overview", v2)
    row = _audit(db, "APP_UI_ROLLED_BACK", target_id="overview")[-1]
    assert row.details["restored_version"] == 1 and row.details["new_version"] == 3
    assert row.details["previous_version"] == 2 and row.reason == "Back to v1"

    # version 0 = built-in defaults
    defaults = admin.post(f"{P}/overview/versions/0/rollback", {})
    assert defaults.status_code == 200, defaults.text
    assert defaults.json()["published"]["version"] == 4
    assert defaults.json()["published"]["content"] == app_ui_service.default_content("overview")
    assert admin.post(f"{P}/overview/versions/0/rollback", {}).status_code == 409  # defaults already live
    assert _tenant_ui(tenant_api, tenant).json()["pages"]["overview"] == app_ui_service.default_content("overview")

    assert admin.post(f"{P}/overview/versions/99/rollback", {}).status_code == 404
    assert admin.post(f"{P}/overview/versions/-3/rollback", {}).status_code == 404
    assert admin.get(f"{P}/overview/versions/99").status_code == 404


def test_rollback_leaves_an_open_draft_untouched(admin):
    admin.step_up()
    v1, v2 = EDITS["invoices"]
    _save_and_publish(admin, "invoices", v1)
    _save_and_publish(admin, "invoices", v2)
    assert _save(admin, "invoices", {"schema_version": 1, "header": {"title": "Work in progress"}}).status_code == 200
    assert admin.post(f"{P}/invoices/versions/1/rollback", {}).status_code == 200
    assert _state(admin, "invoices")["draft"]["content"]["header"]["title"] == "Work in progress"


def test_rollback_of_a_never_published_page_is_409(admin):
    admin.step_up()
    assert admin.post(f"{P}/customers/versions/0/rollback", {}).status_code == 409
    assert admin.post(f"{P}/customers/versions/1/rollback", {}).status_code == 409
    assert _save(admin, "customers", EDITS["customers"][0]).status_code == 200  # draft only
    assert admin.post(f"{P}/customers/versions/0/rollback", {}).status_code == 409


def test_rollback_needs_step_up(admin, db):
    admin.step_up()
    _save_and_publish(admin, "overview", EDITS["overview"][0])
    fresh = Staff(db, ADMIN)  # a new session without step-up
    resp = fresh.post(f"{P}/overview/versions/0/rollback", {})
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "STEP_UP_REQUIRED"
    assert _state(admin, "overview")["published"]["version"] == 1


def test_restore_loads_an_old_version_into_the_draft_only(admin, db, tenant, tenant_api):
    admin.step_up()
    v1, v2 = EDITS["navigation"]
    _save_and_publish(admin, "navigation", v1)
    _save_and_publish(admin, "navigation", v2)
    live_before = _tenant_ui(tenant_api, tenant).json()

    restored = admin.post(f"{P}/navigation/versions/1/restore", {"revision": 0})
    assert restored.status_code == 200, restored.text
    draft = restored.json()["draft"]
    assert draft["content"] == app_ui_service.validate_content("navigation", v1) and draft["revision"] == 1
    assert restored.json()["published"]["version"] == 2
    assert _tenant_ui(tenant_api, tenant).json() == live_before
    assert _audit(db, "APP_UI_DRAFT_RESTORED", target_id="navigation")[-1].details["from_version"] == 1

    assert admin.post(f"{P}/navigation/versions/2/restore", {"revision": 0}).status_code == 409  # stale
    assert admin.post(f"{P}/navigation/versions/2/restore", {"revision": 1}).json()["draft"]["revision"] == 2
    assert admin.post(f"{P}/navigation/versions/42/restore", {"revision": 2}).status_code == 404


# --- validation / malicious content ----------------------------------------------------------------------------

BIG = "a" * (app_ui_service.MAX_CONTENT_BYTES + 10)

INVALID = [
    ("overview", {"header": {"title": "<script>alert(1)</script>"}}),
    ("overview", {"header": {"subtitle": "<img src=x onerror=alert(1)>"}}),
    ("overview", {"kpis": [{"key": "mrr", "label": "MRR<b>"}]}),
    ("navigation", {"sections": [{"key": "workspace", "label": "<svg onload=alert(1)>"}]}),
    ("navigation", {"sections": [{"key": "workspace", "items": [{"key": "overview", "label": "Home>"}]}]}),
    ("customers", {"empty": {"title": "<script>"}}),
    ("invoices", {"columns": [{"key": "total", "label": "</td><script>"}]}),
    ("overview", {"header": {"title": "Over\x00view"}}),
    ("invoices", {"kpis": [{"key": "paid", "label": "Paid\x1b[31m"}]}),
    ("overview", {"header": {"title": "Hi", "html": "x"}}),  # unknown keys anywhere
    ("overview", {"footer": {"title": "x"}}),
    ("overview", {"kpis": [{"key": "mrr", "onClick": "alert(1)"}]}),
    ("theme", {"brand_600": "#1d4ed8", "font_family": "Comic Sans"}),
    ("navigation", {"sections": [{"key": "workspace", "items": [{"key": "overview", "href": "javascript:1"}]}]}),
    ("navigation", {"sections": [{"key": "workspace", "items": [{"key": "not_a_page"}]}]}),  # unknown keys
    ("navigation", {"sections": [{"key": "secret_section"}]}),
    ("navigation", {"sections": [{"key": "workspace", "items": [{"key": "overview", "icon": "Skull"}]}]}),
    ("overview", {"kpis": [{"key": "net_worth"}]}),
    ("overview", {"main_widgets": [{"key": "iframe"}]}),
    ("overview", {"side_widgets": [{"key": "revenue_overview"}]}),  # main widget in the side list
    ("customers", {"columns": [{"key": "password_hash"}]}),
    ("invoices", {"columns": [{"key": "customer_number"}]}),  # a customers column on invoices
    ("overview", {"kpis": [{"key": "mrr"}, {"key": "mrr"}]}),  # duplicates
    ("customers", {"columns": [{"key": "company"}, {"key": "company", "hidden": True}]}),
    ("navigation", {"sections": [{"key": "workspace"}, {"key": "workspace"}]}),
    ("navigation", {"sections": [{"key": "workspace", "items": [{"key": "overview"}, {"key": "overview"}]}]}),
    ("navigation", {"sections": [{"key": "workspace", "items": [{"key": "invoices"}]}]}),  # wrong section
    ("navigation", {"sections": [{"key": "system", "items": [{"key": "settings", "hidden": True}]}]}),
    ("navigation", {"sections": [{"key": "system", "hidden": True}]}),
    ("customers", {"columns": [{"key": "customer", "hidden": True}]}),  # required columns
    ("invoices", {"columns": [{"key": "invoice_number", "hidden": True}]}),
    ("theme", {"brand_600": "red"}),
    ("theme", {"brand_600": "#fff"}),
    ("theme", {"brand_500": "url(javascript:alert(1))"}),
    ("theme", {"sidebar_background": "#1d4ed8; background: url(x)"}),
    ("theme", {"brand_600": "#ffffff"}),  # too light for white text
    ("theme", {"sidebar_active": "#fde047"}),
    ("theme", {"brand_700": 1193046}),
    ("overview", {"schema_version": 2}),
    ("theme", {"schema_version": "1; drop"}),
    ("overview", {"header": {"title": BIG}}),  # oversized
    ("overview", {"kpis": [{"key": "mrr"}] * 3000}),
    ("customers", {"junk": ["x" * 100] * 400}),
    ("overview", {"header": {"eyebrow": "e" * 61}}),  # over max length
    ("overview", {"header": {"title": "t" * 121}}),
    ("overview", {"header": {"subtitle": "s" * 301}}),
    ("invoices", {"kpis": [{"key": "paid", "label": "l" * 61}]}),
    ("overview", {"header": {"title": ""}}),
    ("overview", {"kpis": [{"key": "mrr", "hidden": "yes please"}]}),
    ("overview", {"kpis": {"key": "mrr"}}),
]


@pytest.mark.parametrize("key,content", INVALID)
def test_invalid_or_malicious_content_is_refused(admin, db, key, content):
    resp = _save(admin, key, content, revision=0)
    assert resp.status_code == 422, resp.text
    assert _state(admin, key)["draft"] is None
    assert _drafts(db) == []


def test_oversized_payload_names_the_limit(admin):
    resp = _save(admin, "overview", {"schema_version": 1, "x": BIG}, revision=0)
    assert resp.status_code == 422
    assert "too large" in resp.text


@pytest.mark.parametrize("content", [[], "theme", 42, None, [{"schema_version": 1}]])
def test_non_object_content_is_refused(admin, db, content):
    resp = admin.post(f"{P}/theme/draft", {"content": content, "revision": 0})
    assert resp.status_code == 422, resp.text
    assert _drafts(db) == []


def test_invalid_content_does_not_overwrite_an_existing_draft(admin):
    assert _save(admin, "overview", EDITS["overview"][0]).status_code == 200
    assert _save(admin, "overview", {"header": {"title": "<script>"}}, revision=1).status_code == 422
    draft = _state(admin, "overview")["draft"]
    assert draft["revision"] == 1 and draft["content"]["header"]["title"] == "Welcome back"


def test_mass_assignment_is_refused(admin, db):
    for body in (
        {"content": EDITS["theme"][0], "revision": 0, "state": "published"},
        {"content": EDITS["theme"][0], "revision": 0, "version": 99},
        {"content": EDITS["theme"][0], "revision": 0, "created_by_staff_id": admin.id},
        {"content": EDITS["theme"][0], "revision": -1},
        {"content": EDITS["theme"][0]},
    ):
        assert admin.post(f"{P}/theme/draft", body).status_code == 422, body
    assert _drafts(db) == []
    admin.step_up()
    assert _save(admin, "theme", EDITS["theme"][0]).status_code == 200
    assert admin.post(f"{P}/theme/publish", {"revision": 1, "version": 7}).status_code == 422
    assert admin.post(f"{P}/theme/versions/0/rollback", {"content": EDITS["theme"][1]}).status_code == 422
    assert admin.post(f"{P}/theme/versions/1/restore", {"revision": 1, "content": {}}).status_code == 422
    assert admin.post(f"{P}/theme/publish", {"revision": 1, "note": "<script>"}).status_code == 422


def test_saved_content_is_normalised_by_the_schema(admin):
    resp = _save(admin, "theme", {"brand_600": "#1d4ed8", "brand_500": None}, revision=0)
    assert resp.status_code == 200
    assert resp.json()["draft"]["content"] == {"schema_version": 1, "brand_600": "#1d4ed8"}


# --- concurrency ---------------------------------------------------------------------------------------------------


def test_two_saves_on_the_same_revision(admin, db):
    other = Staff(db, ADMIN)
    assert _save(admin, "overview", EDITS["overview"][0], revision=0).status_code == 200
    assert _save(other, "overview", EDITS["overview"][1], revision=0).status_code == 409
    assert _save(admin, "overview", EDITS["overview"][1], revision=1).status_code == 200
    assert _save(other, "overview", EDITS["overview"][0], revision=1).status_code == 409
    assert len(_drafts(db, "overview")) == 1


def test_publishing_twice_with_the_same_revision(admin, db):
    admin.step_up()
    assert _save(admin, "overview", EDITS["overview"][0]).status_code == 200
    assert admin.post(f"{P}/overview/publish", {"revision": 1}).status_code == 200
    assert admin.post(f"{P}/overview/publish", {"revision": 1}).status_code == 409  # draft gone
    db.expire_all()
    assert len(db.scalars(select(AppUiVersion).where(AppUiVersion.page_key == "overview")).all()) == 1


def test_published_versions_are_immutable_rows(admin, db):
    admin.step_up()
    _save_and_publish(admin, "theme", EDITS["theme"][0])
    _save_and_publish(admin, "theme", EDITS["theme"][1])
    db.expire_all()
    rows = db.scalars(select(AppUiVersion).where(AppUiVersion.page_key == "theme")).all()
    assert sorted(r.version for r in rows) == [1, 2] and all(r.state == "published" for r in rows)
    for r in rows:
        assert app_ui_service.sha256(r.content) == r.content_sha256


# --- keys.json parity ------------------------------------------------------------------------------------------------


def test_keys_json_matches_the_frontend():
    frontend = REPO / "frontend/src/appUi/keys.json"
    if not frontend.exists():
        pytest.skip("frontend/src/appUi/keys.json does not exist yet")
    backend = json.loads((REPO / "backend/app/app_ui/keys.json").read_text(encoding="utf-8"))
    assert json.loads(frontend.read_text(encoding="utf-8")) == backend


def test_keys_json_is_self_consistent():
    layout = KEYS["nav_layout"]
    assert list(layout) == KEYS["nav_sections"]
    placed = [item for items in layout.values() for item in items]
    assert sorted(placed) == sorted(KEYS["nav_items"]) and len(placed) == len(set(placed))
    assert "settings" in layout["system"]
    assert "customer" in KEYS["customers_columns"] and "invoice_number" in KEYS["invoices_columns"]
    for name, values in KEYS.items():
        if isinstance(values, list):
            assert len(values) == len(set(values)), name

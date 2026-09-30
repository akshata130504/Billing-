"""Landing-page CMS: draft -> preview -> publish, history, rollback, security.

Public users only ever get the published version; editing is Platform Administrator only and
server-side enforced; content is strictly validated (no markup, safe links, allow-listed media).
"""
import copy
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.models.platform import PlatformAuditLog
from backend.app.models.website import WebsiteContentVersion
from backend.app.services import website_service
from backend.tests.test_platform_console import ADMIN, OPS, SUPPORT, Staff

W = "/website/pages/landing"
REPO = Path(__file__).resolve().parents[2]
SEED = json.loads((REPO / "backend/app/website/landing_default.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _no_open_draft(db):
    """Website content is platform-wide (not per test tenant): start every test without a draft."""
    from backend.app.models.website import WebsitePage

    website_service.public_content(db)  # seed if needed
    page = db.get(WebsitePage, "landing")
    if page.draft_version_id:
        draft = db.get(WebsiteContentVersion, page.draft_version_id)
        page.draft_version_id = None
        db.flush()
        db.delete(draft)
        db.commit()
    yield


@pytest.fixture
def admin(db):
    return Staff(db, ADMIN)


@pytest.fixture
def public():
    from backend.app.main import app

    return TestClient(app)  # the tenant/public host


def _draft(admin):
    state = admin.get(W).json()
    return state, (state["draft"]["revision"] if state["draft"] else 0)


def _save(admin, content, revision=None):
    if revision is None:
        revision = _draft(admin)[1]
    return admin.post(f"{W}/draft", {"content": content, "revision": revision})


def _edited(**changes):
    content = copy.deepcopy(SEED)
    for path, value in changes.items():
        node = content
        keys = path.split("__")
        for key in keys[:-1]:
            node = node[int(key)] if key.isdigit() else node[key]
        last = keys[-1]
        if last.isdigit():
            node[int(last)] = value
        else:
            node[last] = value
    return content


def _audit(db, action):
    db.expire_all()
    return db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.action == action)
                      .order_by(PlatformAuditLog.occurred_at)).all()


def _publish(admin, note="Test publish"):
    state, revision = _draft(admin)
    return admin.post(f"{W}/publish", {"revision": revision, "note": note})


# --- seed + public ---------------------------------------------------------------------------------------


def test_seed_matches_the_frontend_default_exactly():
    frontend = json.loads((REPO / "frontend/src/pages/public/landing/defaultContent.json").read_text(encoding="utf-8"))
    assert frontend == SEED
    assert website_service.seed_content() == SEED  # the seed validates against the strict schema


def test_public_serves_the_published_content_only(public, admin, db):
    first = public.get("/api/v1/public/website/landing")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "public, max-age=60"
    live_before = first.json()
    assert live_before["content"]["hero"]["headline"] == admin.get(W).json()["published"]["content"]["hero"]["headline"]
    assert _save(admin, _edited(hero__headline="Draft headline - not public yet")).status_code == 200
    after = public.get("/api/v1/public/website/landing").json()
    assert after == live_before
    assert "Draft headline" not in public.get("/api/v1/public/website/landing").text
    # there is no public route that exposes drafts or versions
    for path in ("/api/v1/public/website/landing/draft", "/api/v1/public/website/landing?state=draft",
                 "/api/v1/public/website/drafts", "/api/v1/public/website/landing/versions/1"):
        resp = public.get(path)
        assert resp.status_code == 404 or "Draft headline" not in resp.text


def test_public_website_not_served_on_platform_host(admin):
    assert admin.client.get("/api/v1/public/website/landing").status_code == 404


# --- authorization -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", [OPS, SUPPORT])
def test_only_administrators_can_use_the_cms(db, role):
    staff = Staff(db, role)
    staff.step_up()
    assert staff.get(W).status_code == 403
    assert staff.post(f"{W}/draft", {"content": SEED, "revision": 0}).status_code == 403
    assert staff.post(f"{W}/publish", {"revision": 1}).status_code == 403
    assert staff.post(f"{W}/versions/1/rollback", {}).status_code == 403
    assert staff.post(f"{W}/draft/discard").status_code == 403
    assert staff.get(f"{W}/versions").status_code == 403


def test_tenant_users_and_anonymous_cannot_touch_the_cms(tenant):
    from backend.app.main import app

    anon = TestClient(app, base_url="http://platform.test")
    assert anon.get(f"/api/v1/platform{W}").status_code == 401
    assert anon.get(f"/api/v1/platform{W}", headers=tenant.headers()).status_code == 401
    assert TestClient(app).post(f"/api/v1/platform{W}/draft", headers=tenant.headers(),
                                json={"content": SEED, "revision": 0}).status_code == 404


# --- validation / security ---------------------------------------------------------------------------------


@pytest.mark.parametrize("changes", [
    {"hero__headline": "<script>alert(1)</script>"},
    {"hero__subheading": "Click <a href=javascript:alert(1)>here</a>"},
    {"faq__items__0__a": "<img src=x onerror=alert(1)>"},
    {"seo__title": "Rooman\x00Billing"},
    {"footer__columns__0__links__0__link": "javascript:alert(1)"},
    {"footer__columns__0__links__0__link": "data:text/html;base64,PHNjcmlwdD4="},
    {"footer__columns__0__links__0__link": "//evil.example/path"},
    {"footer__columns__0__links__0__link": "http://evil.example/"},
    {"footer__columns__0__links__0__link": "https://user:pass@evil.example/"},
    {"footer__columns__0__links__0__link": "/../../etc/passwd"},
    {"pricing__primary_cta_link": "vbscript:msgbox"},
    {"hero__video_src": "https://evil.example/video.mp4"},
    {"hero__video_src": "/uploads/website/../../../backend/.env"},
    {"hero__video_src": "/uploads/logos/org_x.png"},
    {"capabilities__cards__0__icon": "Skull"},
    {"capabilities__cards__0__accent": "red; background:url(javascript:1)"},
    {"why__cards__0__tone": "neon"},
    {"header__nav__0__target": "evil"},
    {"pricing__models__2__tiers": [{"up_to": 200, "rate": 14}, {"up_to": 50, "rate": 20}, {"up_to": None, "rate": 10}]},
    {"pricing__models__0__price": -5},
    {"schema_version": 2},
])
def test_unsafe_or_invalid_content_is_refused(admin, db, changes):
    resp = _save(admin, _edited(**changes))
    assert resp.status_code == 422, resp.text
    assert admin.get(W).json()["draft"] is None


def test_unknown_fields_and_mass_assignment_are_refused(admin):
    content = copy.deepcopy(SEED)
    content["hero"]["dangerouslySetInnerHTML"] = "x"
    assert _save(admin, content).status_code == 422
    assert admin.post(f"{W}/draft", {"content": SEED, "revision": 0, "state": "published", "version": 99}).status_code == 422


# --- draft / publish / history ------------------------------------------------------------------------------


def test_draft_publish_rollback_restore_full_cycle(admin, public, db):
    live = admin.get(W).json()["published"]
    live_v, live_headline = live["version"], live["content"]["hero"]["headline"]
    # save + optimistic concurrency
    resp = _save(admin, _edited(hero__headline="Billing that grows with you."))
    assert resp.status_code == 200, resp.text
    draft = resp.json()["draft"]
    assert draft["revision"] == 1 and draft["changed_sections"] == ["hero"]
    assert _save(admin, _edited(hero__headline="Stale edit"), revision=0).status_code == 409
    assert _save(admin, _edited(hero__headline="Billing that grows with you!"), revision=1).status_code == 200
    compare = admin.get(f"{W}/compare").json()
    assert compare["has_draft"] and compare["changes"] == [
        {"path": "hero.headline", "published": live_headline, "draft": "Billing that grows with you!"}
    ]

    # publish needs step-up and the previewed revision
    assert _publish(admin).json()["error"]["code"] == "STEP_UP_REQUIRED"
    admin.step_up()
    assert admin.post(f"{W}/publish", {"revision": 1}).status_code == 409  # stale preview
    published = _publish(admin, note="New hero headline")
    assert published.status_code == 200, published.text
    body = published.json()
    assert body["draft"] is None and body["published"]["version"] == live_v + 1
    assert public.get("/api/v1/public/website/landing").json()["content"]["hero"]["headline"] == "Billing that grows with you!"
    row = _audit(db, "WEBSITE_PUBLISHED")[-1]
    assert row.platform_staff_id == admin.id and row.target_type == "website_page" and row.target_id == "landing"
    assert row.details["changed_sections"] == ["hero"] and row.reason == "New hero headline"

    # nothing to publish
    assert _save(admin, copy.deepcopy(public.get("/api/v1/public/website/landing").json()["content"])).status_code == 200
    assert _publish(admin).status_code == 409
    assert admin.post(f"{W}/draft/discard").status_code == 200
    assert admin.post(f"{W}/draft/discard").status_code == 409

    # history + rollback (as a new version, never rewriting history)
    versions = admin.get(f"{W}/versions").json()
    assert versions["items"][0]["version"] == live_v + 1 and versions["items"][0]["live"] is True
    rolled = admin.post(f"{W}/versions/{live_v}/rollback", {"note": "Revert hero"})
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["published"]["version"] == live_v + 2
    assert public.get("/api/v1/public/website/landing").json()["content"]["hero"]["headline"] == live_headline
    assert admin.post(f"{W}/versions/{live_v}/rollback", {}).status_code == 409  # already live
    assert _audit(db, "WEBSITE_ROLLED_BACK")[-1].details["restored_version"] == live_v
    old = admin.get(f"{W}/versions/{live_v + 1}").json()
    assert old["content"]["hero"]["headline"] == "Billing that grows with you!"  # history intact

    # restore an old version into the draft (not live)
    restored = admin.post(f"{W}/versions/{live_v + 1}/restore", {"revision": 0})
    assert restored.status_code == 200
    assert restored.json()["draft"]["content"]["hero"]["headline"] == "Billing that grows with you!"
    assert public.get("/api/v1/public/website/landing").json()["content"]["hero"]["headline"] != "Billing that grows with you!"
    assert _audit(db, "WEBSITE_DRAFT_RESTORED")
    assert admin.post(f"{W}/draft/discard").status_code == 200


def test_rollback_needs_step_up_and_existing_version(admin):
    assert admin.post(f"{W}/versions/1/rollback", {}).json()["error"]["code"] == "STEP_UP_REQUIRED"
    admin.step_up()
    assert admin.post(f"{W}/versions/9999/rollback", {}).status_code == 404
    assert admin.get(f"{W}/versions/9999").status_code == 404
    assert admin.get("/website/pages/other").status_code == 404


def test_published_versions_are_immutable_rows(admin, db):
    admin.step_up()
    assert _save(admin, _edited(final_cta__heading="Start billing today?")).status_code == 200
    assert _publish(admin).status_code == 200
    db.expire_all()
    rows = db.scalars(select(WebsiteContentVersion).where(WebsiteContentVersion.state == "published")).all()
    shas = {r.version: r.content_sha256 for r in rows}
    assert len(shas) == len(rows) >= 2
    for r in rows:
        assert website_service.sha256(r.content) == r.content_sha256


# --- assets --------------------------------------------------------------------------------------------------


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


@pytest.mark.parametrize("name,data,ctype,ok", [
    ("hero.png", PNG, "image/png", True),
    ("clip.mp4", MP4, "video/mp4", True),
    ("../../evil.png", PNG, "image/png", True),  # the client name is never used
    ("fake.png", b"<svg onload=alert(1)>", "image/png", False),
    ("icon.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml", False),
    ("page.html", b"<html></html>", "text/html", False),
    ("clip.mp4", PNG, "video/mp4", False),
    ("hero.png", PNG, "image/jpeg", False),
    ("empty.png", b"", "image/png", False),
])
def test_asset_upload_validation(admin, db, name, data, ctype, ok):
    resp = admin.client.post("/api/v1/platform/website/assets", headers=admin.csrf(),
                             files={"file": (name, io.BytesIO(data), ctype)})
    if not ok:
        assert resp.status_code == 422, resp.text
        return
    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    assert url.startswith("/uploads/website/") and ".." not in url and "evil" not in url
    if url.endswith(".mp4"):  # an uploaded video can be used as hero media
        assert _save(admin, _edited(hero__video_src=url)).status_code == 200
    assert _audit(db, "WEBSITE_ASSET_UPLOADED")[-1].details["url"] == url


def test_asset_upload_size_limit(admin, monkeypatch):
    monkeypatch.setattr(website_service, "MAX_IMAGE_BYTES", 100)
    resp = admin.client.post("/api/v1/platform/website/assets", headers=admin.csrf(),
                             files={"file": ("big.png", io.BytesIO(PNG + b"\x00" * 200), "image/png")})
    assert resp.status_code == 422


def test_asset_upload_is_administrator_only(db):
    ops = Staff(db, OPS)
    resp = ops.client.post("/api/v1/platform/website/assets", headers=ops.csrf(),
                           files={"file": ("hero.png", io.BytesIO(PNG), "image/png")})
    assert resp.status_code == 403

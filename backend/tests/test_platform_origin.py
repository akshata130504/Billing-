"""The platform console and the tenant app share ONE application origin (single-origin deployment).

The tenant app is served at /admin and the platform (Rooman staff) console at /superadmin, both on
the origin of FRONTEND_URL (conftest: http://localhost:5173). Sharing the origin shares no
authorization: platform API paths accept only the platform session (cookies, CSRF double submit,
TOTP), refuse every other browser origin and every cross-site fetch, and tenant routes never accept
platform credentials (and vice versa).

The tenant app authenticates with bearer tokens only (no cookies, no CSRF token), so "tenant
cookies / tenant CSRF" on the platform side are covered by the bearer and forged-cookie checks.
"""
import time
import uuid
from http.cookies import SimpleCookie

import pytest
from fastapi.testclient import TestClient

from backend.app.api.platform_deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    REFRESH_COOKIE,
    cookie_specs,
)
from backend.app.core.config import Settings, settings
from backend.app.core.totp import totp
from backend.app.models.platform import PlatformRole, PlatformStaff
from backend.app.services import platform_auth_service as svc

APP = "http://localhost:5173"  # the one application origin (/admin and /superadmin)
OTHER_TENANT_ORIGIN = "http://127.0.0.1:5173"  # a tenant ALLOWED_ORIGINS entry, not the app origin
AUTH = "/api/v1/platform/auth"
TENANT_ME = "/api/v1/auth/me"
PASSWORD = "Platform-Passw0rd-2026!"


@pytest.fixture
def platform_client():
    from backend.app.main import app

    with TestClient(app, base_url=APP) as c:
        yield c


def _tenant_client():
    from backend.app.main import app

    return TestClient(app, base_url=APP)


def _staff(db):
    return svc.create_staff(db, email=f"origin-{uuid.uuid4().hex[:8]}@rooman.test", full_name="Origin Tester",
                            role=PlatformRole.PLATFORM_ADMINISTRATOR, password=PASSWORD, actor="test")


def _sign_in(client, db, enrolment):
    db.expire_all()
    staff = db.get(PlatformStaff, enrolment.staff.id)
    staff.totp_last_used_step = None
    db.commit()
    first = client.post(f"{AUTH}/login", json={"email": enrolment.staff.email, "password": PASSWORD})
    assert first.status_code == 200, first.text
    resp = client.post(f"{AUTH}/2fa", json={"challenge_token": first.json()["challenge_token"],
                                            "code": totp(enrolment.totp_secret, at=time.time())})
    assert resp.status_code == 200, resp.text
    return resp


def _set_cookies(resp):
    parsed = {}
    for line in resp.headers.get_list("set-cookie"):
        jar = SimpleCookie()
        jar.load(line)
        for name, morsel in jar.items():
            parsed[name] = (morsel, line)
    return parsed


# --- configuration -------------------------------------------------------------------------------------------


STRONG_TENANT_KEY = "b7c1e9a4f02d58e36a9c47d1b0e2f8a51c3d6e9f04a7b2c5"
STRONG_PLATFORM_KEY = STRONG_TENANT_KEY[::-1] + "Z9"


def test_conftest_serves_the_platform_on_the_application_origin():
    assert settings.platform_origin == APP
    assert settings.platform_auth_enabled


def test_platform_sign_in_needs_the_platform_key():
    disabled = Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET="", FRONTEND_URL=APP)
    assert not disabled.platform_auth_enabled
    enabled = Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY, FRONTEND_URL=APP)
    assert enabled.platform_auth_enabled


def test_platform_origin_is_the_normalised_application_origin():
    s = Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY,
                 FRONTEND_URL="HTTP://Billing.Localhost:5173/")
    assert s.platform_origin == "http://billing.localhost:5173"
    assert s.platform_auth_enabled


def test_there_is_no_separate_platform_origin_setting():
    assert "PLATFORM_APP_ORIGIN" not in Settings.model_fields
    # a stale value left in an old .env.production is ignored: it cannot move the console elsewhere
    s = Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY, FRONTEND_URL=APP,
                 PLATFORM_APP_ORIGIN="https://platform.example.test")
    assert s.platform_origin == APP


@pytest.mark.parametrize("frontend_url", [
    "http://billing.test/app",  # a path, not an origin
    "billing.test",             # no scheme
    "ftp://billing.test",
    "*",
])
def test_platform_needs_a_bare_application_origin(frontend_url):
    with pytest.raises(ValueError, match="FRONTEND_URL"):
        Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY, FRONTEND_URL=frontend_url)


def test_https_application_origin_refuses_insecure_platform_cookies():
    with pytest.raises(ValueError, match="PLATFORM_COOKIE_SECURE"):
        Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY,
                 FRONTEND_URL="https://billing.example.test", PLATFORM_COOKIE_SECURE=False)


def test_production_serves_the_platform_on_the_https_application_origin():
    base = dict(ENVIRONMENT="production", SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY,
                ALLOWED_ORIGINS="https://app.example.test",
                DATABASE_URL="postgresql://u:p@db/x", SECURE_COOKIES=True, DEBUG=False)
    with pytest.raises(ValueError, match="FRONTEND_URL"):
        Settings(**base, FRONTEND_URL="http://app.example.test")
    try:
        prod = Settings(**base, FRONTEND_URL="https://app.example.test")
    except ValueError as exc:  # other unrelated production checks must not be about the platform
        assert "PLATFORM" not in str(exc), exc
        pytest.skip(f"production settings need more unrelated configuration: {exc}")
    assert prod.platform_origin == "https://app.example.test"
    # one public host: nothing beyond the application host (and internal probes) is admitted
    assert [h for h in prod.effective_allowed_hosts if h not in ("localhost", "127.0.0.1")] == ["app.example.test"]
    assert prod.platform_cookie_secure


# --- one origin, two separately authorised applications -----------------------------------------------------


def test_tenant_and_platform_apis_answer_on_the_same_origin(platform_client, tenant):
    # the platform API is reachable on the application origin - and requires a platform session
    assert platform_client.get(f"{AUTH}/me").status_code == 401
    # the tenant API is reachable on the very same origin, with tenant credentials
    assert platform_client.get(TENANT_ME, headers=tenant.headers()).status_code == 200
    assert platform_client.get("/api/v1/health").status_code == 200


def test_same_origin_does_not_share_authorization(platform_client, db, tenant):
    # a tenant Owner's token on the same origin is no platform credential
    assert platform_client.get(f"{AUTH}/me", headers=tenant.headers()).status_code == 401
    assert platform_client.get("/api/v1/platform/dashboard", headers=tenant.headers()).status_code == 401
    # a signed-in platform browser holds no tenant session on the same origin
    _sign_in(platform_client, db, _staff(db))
    assert platform_client.get(f"{AUTH}/me").status_code == 200
    assert platform_client.get(TENANT_ME).status_code == 401
    assert platform_client.get("/api/v1/customers").status_code == 401


def test_boundary_rejections_carry_strict_headers(platform_client):
    resp = platform_client.get(f"{AUTH}/me", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403
    assert resp.headers["content-security-policy"].startswith("default-src 'none'")
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["cache-control"] == "no-store"


def test_tenant_responses_unchanged(tenant):
    tenant_client = _tenant_client()
    resp = tenant_client.get(TENANT_ME, headers=tenant.headers())
    assert resp.status_code == 200
    # the tenant CSP (with the payment provider) is unchanged on tenant responses
    assert "checkout.razorpay.com" in resp.headers["content-security-policy"]
    assert tenant_client.get("/api/v1/health").status_code == 200


# --- Origin / Sec-Fetch-Site ---------------------------------------------------------------------------------


@pytest.mark.parametrize("origin", [
    OTHER_TENANT_ORIGIN,                   # another tenant CORS origin is still not the application origin
    "https://evil.example",                # arbitrary
    "null",                                # sandboxed iframe / file: / data:
    "http://localhost:5173.evil.example",  # suffix trick
    "http://evil.example/localhost:5173",
    "http://platform.localhost:5173",      # a sibling host (same-site, different origin)
    "http://localhost:5174",               # same host, other port = other origin
    "https://localhost:5173",              # other scheme = other origin
    "",
])
def test_foreign_origins_are_refused_on_platform_paths(platform_client, db, origin):
    enrolment = _staff(db)
    login = platform_client.post(f"{AUTH}/login", headers={"Origin": origin},
                                 json={"email": enrolment.staff.email, "password": PASSWORD})
    assert login.status_code == 403
    assert "access-control-allow-origin" not in login.headers
    assert platform_client.get(f"{AUTH}/me", headers={"Origin": origin}).status_code == 403


def test_application_origin_and_no_origin_are_accepted(platform_client, db):
    enrolment = _staff(db)
    body = {"email": enrolment.staff.email, "password": PASSWORD}
    assert platform_client.post(f"{AUTH}/login", headers={"Origin": APP}, json=body).status_code == 200
    assert platform_client.post(f"{AUTH}/login", headers={"Origin": "HTTP://LOCALHOST:5173"}, json=body).status_code == 200
    assert platform_client.post(f"{AUTH}/login", json=body).status_code == 200  # non-browser client


@pytest.mark.parametrize("site,allowed", [("same-origin", True), ("none", True), ("same-site", False), ("cross-site", False)])
def test_sec_fetch_site(platform_client, db, site, allowed):
    enrolment = _staff(db)
    resp = platform_client.post(f"{AUTH}/login", headers={"Sec-Fetch-Site": site},
                                json={"email": enrolment.staff.email, "password": PASSWORD})
    assert (resp.status_code == 200) is allowed, (site, resp.status_code)


@pytest.mark.parametrize("attacker", [
    {"Origin": "http://platform.localhost:5173", "Sec-Fetch-Site": "same-site"},  # sibling subdomain
    {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
])
def test_other_sites_cannot_use_the_platform_session(platform_client, db, attacker):
    """A page on another site - or a sibling subdomain, which is same-site - talking to the platform
    API with the staff member's cookies attached: every request is refused, including no-cors
    "simple" writes that skip preflight, and nothing is readable because CORS never allows it."""
    _sign_in(platform_client, db, _staff(db))
    csrf = platform_client.cookies.get(CSRF_COOKIE, path="/")
    me = platform_client.get(f"{AUTH}/me", headers=attacker)
    assert me.status_code == 403 and "access-control-allow-origin" not in me.headers
    # simple form-encoded POST (no preflight), even with a guessed/stolen CSRF value
    for path in (f"{AUTH}/logout-all", f"{AUTH}/logout", f"{AUTH}/refresh"):
        resp = platform_client.post(path, headers={**attacker, CSRF_HEADER: csrf, "Content-Type": "text/plain"}, content="x")
        assert resp.status_code == 403, path
    # a navigation-style request from that page (no Origin on GET)
    assert platform_client.get(f"{AUTH}/sessions", headers={"Sec-Fetch-Site": attacker["Sec-Fetch-Site"]}).status_code == 403
    # the session is still alive and intact: none of the above did anything
    assert platform_client.get(f"{AUTH}/me").status_code == 200
    assert platform_client.get(f"{AUTH}/sessions").json()["sessions"]


def test_same_origin_writes_still_need_the_platform_csrf_token(platform_client, db):
    """Same origin is not a free pass: a same-origin state change without the CSRF header is refused."""
    _sign_in(platform_client, db, _staff(db))
    same = {"Origin": APP, "Sec-Fetch-Site": "same-origin"}
    assert platform_client.post(f"{AUTH}/logout-all", headers=same).status_code == 403
    assert platform_client.post(f"{AUTH}/logout-all", headers={**same, CSRF_HEADER: "guessed"}).status_code == 403
    assert platform_client.get(f"{AUTH}/me").status_code == 200


# --- CORS -------------------------------------------------------------------------------------------------------


def _preflight(client, path, origin, headers="content-type, x-platform-csrf"):
    return client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                         "Access-Control-Request-Headers": headers})


def test_cors_preflight_from_the_application_origin(platform_client):
    resp = _preflight(platform_client, f"{AUTH}/logout", APP)
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == APP
    assert resp.headers["access-control-allow-credentials"] == "true"
    assert "x-platform-csrf" in resp.headers["access-control-allow-headers"].lower()
    assert "*" not in resp.headers["access-control-allow-origin"]


@pytest.mark.parametrize("origin", [OTHER_TENANT_ORIGIN, "https://evil.example", "null", "http://localhost:5173.evil.example"])
def test_cors_preflight_from_other_origins_is_refused(platform_client, origin):
    resp = _preflight(platform_client, f"{AUTH}/logout", origin)
    assert resp.status_code in (400, 403)
    assert "access-control-allow-origin" not in resp.headers
    assert "access-control-allow-credentials" not in resp.headers


def test_cors_actual_response_only_names_the_application_origin(platform_client, db):
    enrolment = _staff(db)
    resp = platform_client.post(f"{AUTH}/login", headers={"Origin": APP},
                                json={"email": enrolment.staff.email, "password": PASSWORD})
    assert resp.headers["access-control-allow-origin"] == APP
    assert resp.headers["access-control-allow-credentials"] == "true"
    assert "origin" in resp.headers.get("vary", "").lower()


def test_platform_policy_never_reflects_or_wildcards(monkeypatch):
    """Even with a wildcard tenant CORS setting, the platform policy lists only the application origin."""
    from backend.app.core.platform_boundary import PathSplitCORSMiddleware

    mw = PathSplitCORSMiddleware(lambda *a: None, tenant_options=dict(allow_origins=["*"]))
    assert mw.platform.allow_origins == [APP]
    assert not mw.platform.allow_all_origins
    assert mw.platform.allow_origin_regex is None


def test_tenant_cors_unchanged():
    tenant = _tenant_client()
    resp = _preflight(tenant, "/api/v1/auth/login", APP, headers="content-type, authorization")
    assert resp.status_code == 200 and resp.headers["access-control-allow-origin"] == APP
    resp = _preflight(tenant, "/api/v1/auth/login", "https://evil.example", headers="content-type")
    assert "access-control-allow-origin" not in resp.headers


# --- cookies ------------------------------------------------------------------------------------------------------


def test_cookies_are_host_only_httponly_strict_and_narrow(platform_client, db):
    cookies = _set_cookies(_sign_in(platform_client, db, _staff(db)))
    assert set(cookies) == {ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE}
    for name, (morsel, line) in cookies.items():
        assert "domain" not in line.lower(), line  # host-only: never a parent-domain cookie
        assert morsel["samesite"].lower() == "strict"
    assert cookies[ACCESS_COOKIE][0]["httponly"] and cookies[ACCESS_COOKIE][0]["path"] == "/api/v1/platform"
    assert cookies[REFRESH_COOKIE][0]["httponly"] and cookies[REFRESH_COOKIE][0]["path"] == AUTH
    assert not cookies[CSRF_COOKIE][0]["httponly"]


def test_secure_mode_uses_host_and_secure_prefixes(db, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_COOKIE_SECURE", True)
    from backend.app.main import app

    client = TestClient(app, base_url="https://billing.test")  # Secure cookies only travel over https
    resp = _sign_in(client, db, _staff(db))
    cookies = _set_cookies(resp)
    access, refresh, csrf = cookie_specs()
    assert (access.name, refresh.name, csrf.name) == (
        "__Host-rb_platform_access", "__Secure-rb_platform_refresh", "__Host-rb_platform_csrf")
    assert set(cookies) == {access.name, refresh.name, csrf.name}
    for name, (morsel, line) in cookies.items():
        assert morsel["secure"] and "domain" not in line.lower(), line
    # __Host- requires Path=/ ; the refresh cookie stays on the auth path
    assert cookies[access.name][0]["path"] == "/" and cookies[csrf.name][0]["path"] == "/"
    assert cookies[refresh.name][0]["path"] == AUTH
    # the full cookie flow works with the prefixed names
    assert client.get(f"{AUTH}/me").status_code == 200
    token = client.cookies.get(csrf.name)
    assert client.post(f"{AUTH}/refresh", headers={CSRF_HEADER: token}).status_code == 200
    assert client.post(f"{AUTH}/logout", headers={CSRF_HEADER: token}).status_code == 204
    assert client.get(f"{AUTH}/me").status_code == 401
    # an unprefixed cookie (e.g. one a sibling subdomain tossed in) is ignored in secure mode
    stray = TestClient(app, base_url="https://billing.test")
    stray.cookies.set(ACCESS_COOKIE, "x", domain="billing.test", path="/")
    assert stray.get(f"{AUTH}/me").status_code == 401


def test_secure_mode_platform_cookie_on_tenant_paths_grants_nothing(db, monkeypatch, tenant):
    """In secure mode the __Host- access cookie has Path=/ and so also travels to tenant paths on the
    shared origin: tenant routes must ignore it (they read bearer tokens only)."""
    monkeypatch.setattr(settings, "PLATFORM_COOKIE_SECURE", True)
    from backend.app.main import app

    client = TestClient(app, base_url="https://billing.test")
    _sign_in(client, db, _staff(db))
    assert client.get(f"{AUTH}/me").status_code == 200
    for path in (TENANT_ME, "/api/v1/customers", "/api/v1/invoices"):
        assert client.get(path).status_code == 401, path
    # with the tenant's own token the same browser gets exactly the tenant's view, nothing more
    assert client.get(TENANT_ME, headers=tenant.headers()).status_code == 200


def test_platform_session_cookies_are_scoped_to_the_platform_api(platform_client, db):
    _sign_in(platform_client, db, _staff(db))
    assert platform_client.get(f"{AUTH}/me").status_code == 200
    # Same origin, tenant API path: the path-scoped platform session cookies are not attached.
    sent = platform_client.get(TENANT_ME)
    assert sent.status_code == 401
    attached = sent.request.headers.get("cookie", "")
    assert ACCESS_COOKIE not in attached and REFRESH_COOKIE not in attached


def test_platform_cookies_replayed_to_tenant_routes_grant_nothing(platform_client, db):
    _sign_in(platform_client, db, _staff(db))
    raw = "; ".join(f"{c.name}={c.value}" for c in platform_client.cookies.jar)
    csrf = platform_client.cookies.get(CSRF_COOKIE, path="/")
    tenant = _tenant_client()
    headers = {"Cookie": raw, CSRF_HEADER: csrf}
    assert tenant.get(TENANT_ME, headers=headers).status_code == 401
    assert tenant.get("/api/v1/customers", headers=headers).status_code == 401
    assert tenant.post("/api/v1/customers", headers=headers, json={"name": "x"}).status_code == 401


def test_tenant_credentials_grant_nothing_on_platform_routes(platform_client, tenant):
    tenant_token = tenant.headers()["Authorization"].split(" ", 1)[1]
    # as a bearer token
    assert platform_client.get(f"{AUTH}/me", headers=tenant.headers()).status_code == 401
    # smuggled into the platform access cookie slot
    assert platform_client.get(f"{AUTH}/me", headers={"Cookie": f"{ACCESS_COOKIE}={tenant_token}"}).status_code == 401


def test_platform_csrf_value_is_bound_to_the_platform_session(platform_client, db):
    """CSRF needs the header to equal this browser's platform CSRF cookie; any other value (a tenant
    request id, another session's value, a forged cookie+header pair without a session) fails."""
    _sign_in(platform_client, db, _staff(db))
    assert platform_client.post(f"{AUTH}/logout", headers={CSRF_HEADER: "tenant-or-guessed"}).status_code == 403
    assert platform_client.post(f"{AUTH}/logout").status_code == 403
    # a matching cookie+header pair with no platform session authenticates nothing
    anon = TestClient(platform_client.app, base_url=APP)
    assert anon.post(f"{AUTH}/logout", headers={"Cookie": f"{CSRF_COOKIE}=abc", CSRF_HEADER: "abc"}).status_code == 401
    assert platform_client.get(f"{AUTH}/me").status_code == 200


def test_websockets_are_refused_on_platform_paths(platform_client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with platform_client.websocket_connect(f"{AUTH}/me"):
            pass
    assert exc_info.value.code == 1008


def test_website_media_is_served_read_only_on_the_application_origin(platform_client):
    """Uploaded CMS media (public files) load from the one origin for both the public landing page
    and the console preview; nothing can be written through that path."""
    import os

    folder = os.path.join(settings.UPLOAD_DIR, "website")
    os.makedirs(folder, exist_ok=True)
    name = "0123456789abcdef0123456789abcdef.png"
    with open(os.path.join(folder, name), "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
    try:
        assert platform_client.get(f"/uploads/website/{name}").status_code == 200
        assert platform_client.post(f"/uploads/website/{name}").status_code in (404, 405)
    finally:
        os.remove(os.path.join(folder, name))

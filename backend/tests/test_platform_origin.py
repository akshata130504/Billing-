"""Phase 2.5: the platform console lives on its own origin, isolated from the tenant app.

conftest configures the tenant app on the default TestClient host ("testserver", FRONTEND_URL
http://localhost:5173) and the platform console on PLATFORM_APP_ORIGIN=http://platform.test.

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

PLATFORM = "http://platform.test"
TENANT_ORIGIN = "http://localhost:5173"
AUTH = "/api/v1/platform/auth"
TENANT_ME = "/api/v1/auth/me"
PASSWORD = "Platform-Passw0rd-2026!"


@pytest.fixture
def platform_client():
    from backend.app.main import app

    with TestClient(app, base_url=PLATFORM) as c:
        yield c


def _tenant_client():
    from backend.app.main import app

    return TestClient(app)


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


def test_platform_needs_both_key_and_origin():
    with pytest.raises(ValueError):
        Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY, PLATFORM_APP_ORIGIN="")
    with pytest.raises(ValueError):
        Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET="", PLATFORM_APP_ORIGIN="http://platform.localhost:5174")
    disabled = Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET="", PLATFORM_APP_ORIGIN="")
    assert not disabled.platform_auth_enabled and disabled.platform_origin is None


@pytest.mark.parametrize("origin", [
    "http://localhost:5174",        # same hostname as the tenant app, different port: cookies are shared
    "http://localhost:5173",        # the tenant origin itself
    "http://127.0.0.1:9999",        # a tenant ALLOWED_ORIGINS hostname
    "http://platform.test/console",  # a path, not an origin
    "platform.test",                # no scheme
    "ftp://platform.test",
    "*",
])
def test_platform_origin_must_be_a_distinct_bare_origin(origin):
    with pytest.raises(ValueError):
        Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY, PLATFORM_APP_ORIGIN=origin)


def test_platform_origin_normalised():
    s = Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY,
                 PLATFORM_APP_ORIGIN="HTTP://Platform.Localhost:5174/")
    assert s.platform_origin == "http://platform.localhost:5174"
    assert s.platform_netloc == "platform.localhost:5174"
    assert s.platform_auth_enabled


def test_https_platform_origin_refuses_insecure_cookies():
    with pytest.raises(ValueError, match="PLATFORM_COOKIE_SECURE"):
        Settings(SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY,
                 PLATFORM_APP_ORIGIN="https://platform.example.test", PLATFORM_COOKIE_SECURE=False)


def test_production_requires_https_platform_origin_and_admits_its_host():
    base = dict(ENVIRONMENT="production", SECRET_KEY=STRONG_TENANT_KEY, PLATFORM_JWT_SECRET=STRONG_PLATFORM_KEY,
                FRONTEND_URL="https://app.example.test", ALLOWED_ORIGINS="https://app.example.test",
                DATABASE_URL="postgresql://u:p@db/x", SECURE_COOKIES=True, DEBUG=False)
    with pytest.raises(ValueError, match="PLATFORM_APP_ORIGIN"):
        Settings(**base, PLATFORM_APP_ORIGIN="http://platform.example.test")
    try:
        prod = Settings(**base, PLATFORM_APP_ORIGIN="https://platform.example.test")
    except ValueError as exc:  # other unrelated production checks must not be about the platform
        assert "PLATFORM" not in str(exc), exc
        pytest.skip(f"production settings need more unrelated configuration: {exc}")
    assert "platform.example.test" in prod.effective_allowed_hosts
    assert prod.platform_cookie_secure


# --- host binding ---------------------------------------------------------------------------------------------


def test_platform_api_is_not_served_on_the_tenant_host():
    tenant = _tenant_client()
    for path in (f"{AUTH}/login", f"{AUTH}/me", f"{AUTH}/refresh", f"{AUTH}/logout"):
        assert tenant.post(path, json={}).status_code == 404, path
    assert tenant.get(f"{AUTH}/me").status_code == 404


def test_platform_host_serves_nothing_but_the_platform_api(platform_client):
    for path in (TENANT_ME, "/api/v1/customers", "/api/v1/auth/login", "/api/v1/health", "/api/v1/uploads/x.png", "/"):
        assert platform_client.get(path).status_code == 404, path
    assert platform_client.get(f"{AUTH}/me").status_code == 401  # reachable, just unauthenticated


def test_boundary_rejections_carry_strict_headers(platform_client):
    resp = platform_client.get(TENANT_ME)
    assert resp.status_code == 404
    assert resp.headers["content-security-policy"].startswith("default-src 'none'")
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["cache-control"] == "no-store"


def test_tenant_host_unchanged(tenant):
    tenant_client = _tenant_client()
    resp = tenant_client.get(TENANT_ME, headers=tenant.headers())
    assert resp.status_code == 200
    # the tenant CSP (with the payment provider) is unchanged on tenant responses
    assert "checkout.razorpay.com" in resp.headers["content-security-policy"]
    assert tenant_client.get("/api/v1/health").status_code == 200


# --- Origin / Sec-Fetch-Site ---------------------------------------------------------------------------------


@pytest.mark.parametrize("origin", [
    TENANT_ORIGIN,                       # the tenant app (e.g. XSS on the tenant origin)
    "http://127.0.0.1:5173",
    "https://evil.example",              # arbitrary
    "null",                              # sandboxed iframe / file: / data:
    "http://platform.test.evil.example",  # suffix trick
    "http://evil.example/platform.test",
    "http://platform.test:8080",         # same host, other port = other origin
    "https://platform.test",             # other scheme = other origin
    "",
])
def test_foreign_origins_are_refused_on_platform_paths(platform_client, db, origin):
    enrolment = _staff(db)
    login = platform_client.post(f"{AUTH}/login", headers={"Origin": origin},
                                 json={"email": enrolment.staff.email, "password": PASSWORD})
    assert login.status_code == 403
    assert "access-control-allow-origin" not in login.headers
    assert platform_client.get(f"{AUTH}/me", headers={"Origin": origin}).status_code == 403


def test_own_origin_and_no_origin_are_accepted(platform_client, db):
    enrolment = _staff(db)
    body = {"email": enrolment.staff.email, "password": PASSWORD}
    assert platform_client.post(f"{AUTH}/login", headers={"Origin": PLATFORM}, json=body).status_code == 200
    assert platform_client.post(f"{AUTH}/login", headers={"Origin": "HTTP://PLATFORM.TEST"}, json=body).status_code == 200
    assert platform_client.post(f"{AUTH}/login", json=body).status_code == 200  # non-browser client


@pytest.mark.parametrize("site,allowed", [("same-origin", True), ("none", True), ("same-site", False), ("cross-site", False)])
def test_sec_fetch_site(platform_client, db, site, allowed):
    enrolment = _staff(db)
    resp = platform_client.post(f"{AUTH}/login", headers={"Sec-Fetch-Site": site},
                                json={"email": enrolment.staff.email, "password": PASSWORD})
    assert (resp.status_code == 200) is allowed, (site, resp.status_code)


def test_tenant_origin_xss_cannot_use_the_platform_session(platform_client, db):
    """A script on the tenant origin (XSS) talking to the platform console: the browser would attach
    the platform cookies only if it chose to - but even when it does (sibling subdomains are
    same-site), every request is refused, including no-cors "simple" writes that skip preflight,
    and nothing is readable because CORS never allows the tenant origin."""
    _sign_in(platform_client, db, _staff(db))
    csrf = platform_client.cookies.get(CSRF_COOKIE, path="/")
    xss = {"Origin": TENANT_ORIGIN, "Sec-Fetch-Site": "same-site"}
    me = platform_client.get(f"{AUTH}/me", headers=xss)
    assert me.status_code == 403 and "access-control-allow-origin" not in me.headers
    # simple form-encoded POST (no preflight), even with a guessed/stolen CSRF value
    for path in (f"{AUTH}/logout-all", f"{AUTH}/logout", f"{AUTH}/refresh"):
        resp = platform_client.post(path, headers={**xss, CSRF_HEADER: csrf, "Content-Type": "text/plain"}, content="x")
        assert resp.status_code == 403, path
    # a navigation-style request from the tenant page (no Origin on GET, Sec-Fetch-Site same-site)
    assert platform_client.get(f"{AUTH}/sessions", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    # the session is still alive and intact: none of the above did anything
    assert platform_client.get(f"{AUTH}/me").status_code == 200
    # the platform cookies are HttpOnly (except the CSRF value, which grants nothing on its own)
    assert platform_client.get(f"{AUTH}/sessions").json()["sessions"]


# --- CORS -------------------------------------------------------------------------------------------------------


def _preflight(client, path, origin, headers="content-type, x-platform-csrf"):
    return client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                         "Access-Control-Request-Headers": headers})


def test_cors_preflight_from_platform_origin(platform_client):
    resp = _preflight(platform_client, f"{AUTH}/logout", PLATFORM)
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == PLATFORM
    assert resp.headers["access-control-allow-credentials"] == "true"
    assert "x-platform-csrf" in resp.headers["access-control-allow-headers"].lower()
    assert "*" not in resp.headers["access-control-allow-origin"]


@pytest.mark.parametrize("origin", [TENANT_ORIGIN, "https://evil.example", "null", "http://platform.test.evil.example"])
def test_cors_preflight_from_other_origins_is_refused(platform_client, origin):
    resp = _preflight(platform_client, f"{AUTH}/logout", origin)
    assert resp.status_code in (400, 403)
    assert "access-control-allow-origin" not in resp.headers
    assert "access-control-allow-credentials" not in resp.headers


def test_cors_actual_response_only_names_the_platform_origin(platform_client, db):
    enrolment = _staff(db)
    resp = platform_client.post(f"{AUTH}/login", headers={"Origin": PLATFORM},
                                json={"email": enrolment.staff.email, "password": PASSWORD})
    assert resp.headers["access-control-allow-origin"] == PLATFORM
    assert resp.headers["access-control-allow-credentials"] == "true"
    assert "origin" in resp.headers.get("vary", "").lower()


def test_platform_policy_never_reflects_or_wildcards(monkeypatch):
    """Even with a wildcard tenant CORS setting, the platform policy lists only the platform origin."""
    from backend.app.core.platform_boundary import PathSplitCORSMiddleware

    mw = PathSplitCORSMiddleware(lambda *a: None, tenant_options=dict(allow_origins=["*"]))
    assert mw.platform.allow_origins == [PLATFORM]
    assert not mw.platform.allow_all_origins
    assert mw.platform.allow_origin_regex is None


def test_tenant_cors_unchanged():
    tenant = _tenant_client()
    resp = _preflight(tenant, "/api/v1/auth/login", TENANT_ORIGIN, headers="content-type, authorization")
    assert resp.status_code == 200 and resp.headers["access-control-allow-origin"] == TENANT_ORIGIN
    # the platform origin is not a tenant CORS origin
    resp = _preflight(tenant, "/api/v1/auth/login", PLATFORM, headers="content-type")
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

    client = TestClient(app, base_url="https://platform.test")  # Secure cookies only travel over https
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
    stray = TestClient(app, base_url="https://platform.test")
    stray.cookies.set(ACCESS_COOKIE, "x", domain="platform.test", path="/")
    assert stray.get(f"{AUTH}/me").status_code == 401


def test_platform_cookies_are_not_sent_to_the_tenant_host(platform_client, db, tenant):
    _sign_in(platform_client, db, _staff(db))
    assert platform_client.get(f"{AUTH}/me").status_code == 200
    # Same cookie jar, tenant host: the host-only platform cookies are not attached.
    sent = platform_client.get(f"http://testserver{TENANT_ME}")
    assert sent.status_code == 401
    assert "cookie" not in {k.lower() for k in sent.request.headers}


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
    anon = TestClient(platform_client.app, base_url=PLATFORM)
    assert anon.post(f"{AUTH}/logout", headers={"Cookie": f"{CSRF_COOKIE}=abc", CSRF_HEADER: "abc"}).status_code == 401
    assert platform_client.get(f"{AUTH}/me").status_code == 200


def test_websockets_are_refused_on_the_platform_host(platform_client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with platform_client.websocket_connect(f"{AUTH}/me"):
            pass
    assert exc_info.value.code == 1008

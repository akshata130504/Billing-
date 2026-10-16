"""The browser's refresh token lives in an HttpOnly cookie, never in the JSON body.

The SPA sends X-Rooman-Session: cookie (frontend/src/services/apiClient.ts). Without that header the
documented body-token contract is unchanged (API / native clients, the rest of this suite).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.api import session_cookies
from backend.app.core.config import settings
from backend.app.main import app

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd!"
COOKIE = {session_cookies.SESSION_MODE_HEADER: "cookie"}


@pytest.fixture()
def browser():
    """A fresh cookie jar per test (the session-wide `client` fixture must stay cookie-free)."""
    return TestClient(app)


def _login(browser: TestClient, email: str):
    return browser.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}, headers=COOKIE)


def _set_cookie_header(resp) -> str:
    return "; ".join(v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie")


def test_cookie_mode_login_keeps_refresh_token_out_of_the_body(browser, tenant):
    r = _login(browser, tenant.owner.email)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body.get("refresh_token") in (None, "")
    raw = _set_cookie_header(r)
    assert f"{session_cookies.cookie_name()}=" in raw
    assert "HttpOnly" in raw
    assert "SameSite=strict" in raw or "samesite=strict" in raw.lower()
    assert f"Path={API}/auth" in raw
    # the access token (kept in memory by the SPA) works
    me = browser.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200


def test_body_mode_is_unchanged_for_api_clients(browser, tenant):
    r = browser.post(f"{API}/auth/login", json={"email": tenant.owner.email, "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["refresh_token"]
    assert session_cookies.cookie_name() not in _set_cookie_header(r)


def test_refresh_from_cookie_rotates_and_needs_the_header(browser, tenant):
    _login(browser, tenant.owner.email)
    # the cookie alone (e.g. a cross-site form post) is not enough
    assert browser.post(f"{API}/auth/refresh").status_code == 401
    r = browser.post(f"{API}/auth/refresh", headers=COOKIE)
    assert r.status_code == 200, r.text
    assert r.json()["access_token"] and r.json().get("refresh_token") is None
    assert session_cookies.cookie_name() in _set_cookie_header(r)  # rotated
    assert browser.post(f"{API}/auth/refresh", headers=COOKIE).status_code == 200


def test_logout_clears_the_cookie_and_revokes_the_session(browser, tenant):
    access = _login(browser, tenant.owner.email).json()["access_token"]
    old_cookie = browser.cookies.get(session_cookies.cookie_name())
    r = browser.post(f"{API}/auth/logout", headers={**COOKIE, "Authorization": f"Bearer {access}"})
    assert r.status_code == 204
    assert 'Max-Age=0' in _set_cookie_header(r) or "expires=" in _set_cookie_header(r).lower()
    # the revoked refresh token is refused even if the old cookie value is replayed
    replay = TestClient(app)
    replay.cookies.set(session_cookies.cookie_name(), old_cookie, path=f"{API}/auth")
    assert replay.post(f"{API}/auth/refresh", headers=COOKIE).status_code == 401


def test_two_tabs_refreshing_with_the_same_cookie_stay_signed_in(browser, tenant, monkeypatch):
    _login(browser, tenant.owner.email)
    stale = browser.cookies.get(session_cookies.cookie_name())
    assert browser.post(f"{API}/auth/refresh", headers=COOKIE).status_code == 200  # tab 1 rotates
    tab2 = TestClient(app)
    tab2.cookies.set(session_cookies.cookie_name(), stale, path=f"{API}/auth")
    assert tab2.post(f"{API}/auth/refresh", headers=COOKIE).status_code == 200  # tab 2 within the grace
    assert browser.post(f"{API}/auth/refresh", headers=COOKIE).status_code == 200  # tab 1 unaffected


def test_replay_of_a_rotated_cookie_after_the_grace_is_reuse(browser, tenant, monkeypatch):
    monkeypatch.setattr(settings, "SESSION_REFRESH_REUSE_GRACE_SECONDS", 0)
    _login(browser, tenant.owner.email)
    stale = browser.cookies.get(session_cookies.cookie_name())
    assert browser.post(f"{API}/auth/refresh", headers=COOKIE).status_code == 200
    thief = TestClient(app)
    thief.cookies.set(session_cookies.cookie_name(), stale, path=f"{API}/auth")
    r = thief.post(f"{API}/auth/refresh", headers=COOKIE)
    assert r.status_code == 401
    # reuse detection revoked the whole chain, the legitimate tab included
    assert browser.post(f"{API}/auth/refresh", headers=COOKIE).status_code == 401


def test_change_password_keeps_the_cookie_session(browser, tenant):
    access = _login(browser, tenant.owner.email).json()["access_token"]
    r = browser.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "An0therStr0ngPass!"},
        headers={**COOKIE, "Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 204, r.text
    assert browser.post(f"{API}/auth/refresh", headers=COOKIE).status_code == 200


def test_https_deployments_use_a_secure_prefixed_cookie(monkeypatch):
    monkeypatch.setattr(settings, "SECURE_COOKIES", True)
    assert session_cookies.cookie_name() == "__Secure-rb_session"
    from fastapi import Response

    resp = Response()
    session_cookies.set_refresh_cookie(resp, "x")
    raw = resp.headers["set-cookie"]
    assert raw.startswith("__Secure-rb_session=x")
    assert "Secure" in raw and "HttpOnly" in raw

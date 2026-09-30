"""Platform (Rooman staff) identity and authentication - phase 2.

Covers the separate PlatformStaff principal, mandatory TOTP, platform sessions and cookies, the
separate platform token (key, audience, issuer, type), token confusion in both directions, role
dependencies, isolation from tenant auth, and the platform audit trail.
"""
import base64
import json
import time
import uuid
from datetime import timedelta

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.api.platform_deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    REFRESH_COOKIE,
    PlatformContext,
    require_platform_administrator,
    require_platform_operations,
    require_platform_staff,
    require_platform_support,
)
from backend.app.core import platform_security
from backend.app.core.config import settings
from backend.app.core.exceptions import AppException, app_exception_handler
from backend.app.core.platform_security import (
    PLATFORM_ACCESS_TOKEN_TYPE,
    PLATFORM_TOKEN_AUDIENCE,
    PLATFORM_TOKEN_ISSUER,
    create_platform_access_token,
    decode_platform_access_token,
)
from backend.app.core.security import (
    TENANT_TOKEN_AUDIENCE,
    TOKEN_ISSUER,
    create_access_token,
    decode_access_token,
    verify_password,
)
from backend.app.core.totp import totp
from backend.app.models import MemberRole
from backend.app.models.base import utcnow
from backend.app.models.platform import (
    PlatformAuditLog,
    PlatformLoginChallenge,
    PlatformRole,
    PlatformSession,
    PlatformStaff,
)
from backend.app.services import platform_auth_service as svc

AUTH = "/api/v1/platform/auth"
# The platform API answers only on the platform console host (conftest: PLATFORM_APP_ORIGIN);
# tenant endpoints answer on every other host (TestClient's default "testserver").
PLATFORM_BASE = "http://platform.test"
TENANT_ME = "/api/v1/auth/me"
PASSWORD = "Platform-Passw0rd-2026!"

ADMIN = PlatformRole.PLATFORM_ADMINISTRATOR
OPS = PlatformRole.PLATFORM_OPERATIONS
SUPPORT = PlatformRole.PLATFORM_SUPPORT


# --- helpers --------------------------------------------------------------------------------------------


@pytest.fixture
def client():
    """A fresh TestClient per test: platform cookies must never leak between tests."""
    from backend.app.main import app

    with TestClient(app, base_url=PLATFORM_BASE) as c:
        yield c


def _staff(db, role=ADMIN, email=None):
    return svc.create_staff(
        db, email=email or f"staff-{uuid.uuid4().hex[:8]}@rooman.test", full_name="Platform Person",
        role=role, password=PASSWORD, actor="test",
    )


def _code(secret, steps=0):
    return totp(secret, at=time.time() + steps * 30)


def _fresh_client():
    from backend.app.main import app

    return TestClient(app, base_url=PLATFORM_BASE)


def _tenant_client():
    from backend.app.main import app

    return TestClient(app)


def _challenge(client, enrolment, password=PASSWORD):
    return client.post(f"{AUTH}/login", json={"email": enrolment.staff.email, "password": password})


def _sign_in(client, db, enrolment, steps=0):
    """Full sign-in; returns the 2FA response. Allows repeated sign-ins in one test."""
    db.expire_all()
    staff = db.get(PlatformStaff, enrolment.staff.id)
    staff.totp_last_used_step = None
    db.commit()
    first = _challenge(client, enrolment)
    assert first.status_code == 200, first.text
    resp = client.post(f"{AUTH}/2fa", json={"challenge_token": first.json()["challenge_token"],
                                            "code": _code(enrolment.totp_secret, steps)})
    assert resp.status_code == 200, resp.text
    return resp


def _access(client):
    return client.cookies.get(ACCESS_COOKIE, path="/api/v1/platform")


def _csrf(client):
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE, path="/")}


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _platform_claims(staff_id, session_id, **overrides):
    now = time.time()
    claims = {
        "sub": staff_id, "sid": session_id, "role": "platform_administrator",
        "aud": PLATFORM_TOKEN_AUDIENCE, "iss": PLATFORM_TOKEN_ISSUER, "typ": PLATFORM_ACCESS_TOKEN_TYPE,
        "iat": now, "exp": int(now + 600), "jti": uuid.uuid4().hex, "amr": ["pwd", "otp"], "auth_time": int(now),
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not ...}


def _sign(claims, key):
    return jwt.encode(claims, key, algorithm="HS256")


def _audit(db, staff_id=None, action=None):
    db.expire_all()
    stmt = select(PlatformAuditLog)
    if staff_id is not None:
        stmt = stmt.where(PlatformAuditLog.platform_staff_id == staff_id)
    if action is not None:
        stmt = stmt.where(PlatformAuditLog.action == action)
    return list(db.scalars(stmt.order_by(PlatformAuditLog.occurred_at)).all())


# --- platform identity ------------------------------------------------------------------------------------


def test_create_staff_hashes_password_and_encrypts_totp(db):
    enrolment = _staff(db)
    db.expire_all()
    staff = db.get(PlatformStaff, enrolment.staff.id)
    assert staff.hashed_password != PASSWORD and verify_password(PASSWORD, staff.hashed_password)
    assert staff.totp_enabled_at is not None
    assert staff.totp_secret and enrolment.totp_secret not in staff.totp_secret  # stored encrypted
    assert enrolment.otpauth_uri.startswith("otpauth://totp/")
    assert staff.role == ADMIN and staff.is_active


def test_platform_staff_is_not_a_tenant_user(db):
    from backend.app.models import Membership, User

    enrolment = _staff(db)
    assert db.scalars(select(User).where(User.email == enrolment.staff.email)).first() is None
    assert db.scalars(select(Membership).where(Membership.user_id == enrolment.staff.id)).first() is None
    assert {m.value for m in MemberRole} == {"owner", "admin", "finance", "viewer"}  # tenant roles unchanged


@pytest.mark.parametrize(
    "password", ["short1A", "alllowercase123456", "ALLUPPERCASE123456", "NoDigitsAtAllHere!", "Sh0rtButMixed"]
)
def test_weak_platform_passwords_refused(db, password):
    with pytest.raises(AppException):
        svc.create_staff(db, email=f"w-{uuid.uuid4().hex[:6]}@rooman.test", full_name="W", role=SUPPORT,
                         password=password, actor="test")


def test_duplicate_staff_email_refused(db):
    enrolment = _staff(db)
    with pytest.raises(AppException):
        _staff(db, email=enrolment.staff.email.upper())


def test_password_alone_never_establishes_a_session(client, db):
    enrolment = _staff(db)
    resp = _challenge(client, enrolment)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"two_factor_required": True, "challenge_token": body["challenge_token"], "expires_in": 300}
    assert _access(client) is None and client.cookies.get(REFRESH_COOKIE, path=f"{AUTH}") is None
    db.expire_all()
    assert db.scalars(select(PlatformSession).where(PlatformSession.staff_id == enrolment.staff.id)).first() is None
    # The challenge itself is not a credential for anything.
    assert client.get(f"{AUTH}/me", headers=_bearer(body["challenge_token"])).status_code == 401


@pytest.mark.parametrize("case", ["unknown", "wrong_password", "inactive"])
def test_login_failures_look_identical(client, db, case):
    enrolment = _staff(db)
    if case == "unknown":
        body = {"email": f"nobody-{uuid.uuid4().hex[:6]}@rooman.test", "password": PASSWORD}
    elif case == "wrong_password":
        body = {"email": enrolment.staff.email, "password": PASSWORD + "x"}
    else:
        svc.deactivate_staff(db, email=enrolment.staff.email, reason="test", actor="test")
        body = {"email": enrolment.staff.email, "password": PASSWORD}
    resp = client.post(f"{AUTH}/login", json=body)
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == svc.INVALID_CREDENTIALS


def test_staff_without_two_factor_cannot_sign_in(client, db):
    enrolment = _staff(db)
    staff = db.get(PlatformStaff, enrolment.staff.id)
    staff.totp_enabled_at = None
    db.commit()
    resp = _challenge(client, enrolment)
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == svc.INVALID_CREDENTIALS


def test_tenant_user_credentials_do_not_work_on_platform_login(client, tenant):
    resp = client.post(f"{AUTH}/login", json={"email": tenant.owner.email, "password": "Str0ngPassw0rd!"})
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == svc.INVALID_CREDENTIALS


def test_password_brute_force_is_throttled(client, db):
    enrolment = _staff(db)
    codes = [_challenge(client, enrolment, password="Wrong-Passw0rd-xx").status_code for _ in range(svc.MAX_FAILED_LOGINS)]
    assert codes == [401] * svc.MAX_FAILED_LOGINS
    locked = _challenge(client, enrolment)  # even the right password is refused while locked
    assert locked.status_code == 401
    assert locked.json()["error"]["message"] == svc.TOO_MANY_ATTEMPTS
    assert _audit(db, enrolment.staff.id, "PLATFORM_ACCOUNT_LOCKED")


# --- mandatory 2FA ------------------------------------------------------------------------------------------


def test_valid_totp_establishes_session_with_secure_cookies(client, db):
    enrolment = _staff(db)
    resp = _sign_in(client, db, enrolment)
    body = resp.json()
    assert body["staff"]["email"] == enrolment.staff.email and body["staff"]["role"] == "platform_administrator"
    assert "access_token" not in resp.text and "refresh" not in json.dumps(body)
    set_cookies = "\n".join(resp.headers.get_list("set-cookie")).lower()
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        line = next(l for l in resp.headers.get_list("set-cookie") if l.startswith(name))
        assert "httponly" in line.lower() and "samesite=strict" in line.lower()
    assert "path=/api/v1/platform;" in set_cookies or "path=/api/v1/platform\n" in set_cookies or "path=/api/v1/platform" in set_cookies
    assert f"path={AUTH.lower()}" in set_cookies
    csrf_line = next(l for l in resp.headers.get_list("set-cookie") if l.startswith(CSRF_COOKIE))
    assert "httponly" not in csrf_line.lower()
    assert resp.headers.get("cache-control") == "no-store"
    assert client.get(f"{AUTH}/me").status_code == 200


def test_cookies_are_secure_in_production_like_settings(client, db, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_COOKIE_SECURE", True)
    resp = _sign_in(client, db, _staff(db))
    for line in resp.headers.get_list("set-cookie"):
        assert "secure" in line.lower()


@pytest.mark.parametrize("code", ["000000", "12345", "abcdef", ""])
def test_invalid_or_missing_totp_rejected(client, db, code):
    enrolment = _staff(db)
    challenge = _challenge(client, enrolment).json()["challenge_token"]
    resp = client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": code})
    assert resp.status_code in (401, 422)
    assert _access(client) is None


def test_totp_code_cannot_be_replayed(client, db):
    enrolment = _staff(db)
    code = _code(enrolment.totp_secret)
    first = client.post(f"{AUTH}/2fa", json={"challenge_token": _challenge(client, enrolment).json()["challenge_token"], "code": code})
    assert first.status_code == 200
    again = client.post(f"{AUTH}/2fa", json={"challenge_token": _challenge(client, enrolment).json()["challenge_token"], "code": code})
    assert again.status_code == 401
    assert again.json()["error"]["message"] == svc.INVALID_CODE


def test_challenge_is_single_use(client, db):
    enrolment = _staff(db)
    challenge = _challenge(client, enrolment).json()["challenge_token"]
    assert client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": _code(enrolment.totp_secret)}).status_code == 200
    reuse = client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": _code(enrolment.totp_secret, 1)})
    assert reuse.status_code == 401
    assert reuse.json()["error"]["message"] == svc.CHALLENGE_INVALID


def test_expired_challenge_rejected(client, db):
    enrolment = _staff(db)
    challenge = _challenge(client, enrolment).json()["challenge_token"]
    row = db.scalars(select(PlatformLoginChallenge).where(PlatformLoginChallenge.staff_id == enrolment.staff.id)).first()
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    resp = client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": _code(enrolment.totp_secret)})
    assert resp.status_code == 401 and resp.json()["error"]["message"] == svc.CHALLENGE_INVALID


def test_unknown_challenge_rejected(client, db):
    resp = client.post(f"{AUTH}/2fa", json={"challenge_token": "not-a-challenge", "code": "123456"})
    assert resp.status_code == 401 and resp.json()["error"]["message"] == svc.CHALLENGE_INVALID


def test_new_login_voids_older_challenges(client, db):
    enrolment = _staff(db)
    old = _challenge(client, enrolment).json()["challenge_token"]
    _challenge(client, enrolment)
    resp = client.post(f"{AUTH}/2fa", json={"challenge_token": old, "code": _code(enrolment.totp_secret)})
    assert resp.status_code == 401 and resp.json()["error"]["message"] == svc.CHALLENGE_INVALID


def test_challenge_dies_after_too_many_wrong_codes(client, db):
    enrolment = _staff(db)
    challenge = _challenge(client, enrolment).json()["challenge_token"]
    for _ in range(svc.MAX_CHALLENGE_ATTEMPTS):
        assert client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": "000000"}).status_code == 401
    resp = client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": _code(enrolment.totp_secret)})
    assert resp.status_code == 401 and resp.json()["error"]["message"] == svc.CHALLENGE_INVALID


def test_code_brute_force_locks_the_account_step(client, db):
    enrolment = _staff(db)
    for _ in range(svc.MAX_FAILED_LOGINS):
        challenge = _challenge(client, enrolment).json()["challenge_token"]
        client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": "000000"})
    challenge = _challenge(client, enrolment).json()["challenge_token"]
    resp = client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": _code(enrolment.totp_secret)})
    assert resp.status_code == 401 and resp.json()["error"]["message"] == svc.TOO_MANY_ATTEMPTS
    assert _audit(db, enrolment.staff.id, "PLATFORM_ACCOUNT_LOCKED")


def test_deactivated_between_steps_cannot_finish(client, db):
    enrolment = _staff(db)
    challenge = _challenge(client, enrolment).json()["challenge_token"]
    svc.deactivate_staff(db, email=enrolment.staff.email, reason="test", actor="test")
    resp = client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": _code(enrolment.totp_secret)})
    assert resp.status_code == 401


def test_tenant_two_factor_endpoints_unaffected(client, tenant):
    """Platform 2FA is isolated: the tenant /auth/login/mfa flow still refuses a platform challenge."""
    resp = _tenant_client().post("/api/v1/auth/login/mfa", json={"mfa_token": "not-a-tenant-token", "code": "000000"})
    assert resp.status_code == 401


# --- sessions ---------------------------------------------------------------------------------------------------


def test_session_created_and_listed(client, db):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment).json()
    sessions = client.get(f"{AUTH}/sessions").json()["sessions"]
    assert [s["id"] for s in sessions] == [me["session_id"]] and sessions[0]["current"] is True
    row = db.get(PlatformSession, me["session_id"])
    assert row.refresh_token_hash and len(row.refresh_token_hash) == 64  # only a hash is stored
    assert client.cookies.get(REFRESH_COOKIE, path=AUTH) not in row.refresh_token_hash


def test_multiple_sessions_and_revoke_one(db):
    enrolment = _staff(db)
    a, b = _fresh_client(), _fresh_client()
    sid_a = _sign_in(a, db, enrolment).json()["session_id"]
    sid_b = _sign_in(b, db, enrolment, steps=1).json()["session_id"]
    assert {s["id"] for s in a.get(f"{AUTH}/sessions").json()["sessions"]} == {sid_a, sid_b}
    assert a.delete(f"{AUTH}/sessions/{sid_b}", headers=_csrf(a)).status_code == 204
    assert b.get(f"{AUTH}/me").status_code == 401
    assert a.get(f"{AUTH}/me").status_code == 200
    assert _audit(db, enrolment.staff.id, "PLATFORM_SESSION_REVOKED")


def test_cannot_revoke_another_staff_members_session(db):
    one, other = _staff(db), _staff(db, role=SUPPORT)
    a, b = _fresh_client(), _fresh_client()
    _sign_in(a, db, one)
    sid_other = _sign_in(b, db, other).json()["session_id"]
    assert a.delete(f"{AUTH}/sessions/{sid_other}", headers=_csrf(a)).status_code == 404
    assert b.get(f"{AUTH}/me").status_code == 200


def test_logout_revokes_session_and_clears_cookies(client, db):
    enrolment = _staff(db)
    _sign_in(client, db, enrolment)
    token = _access(client)
    resp = client.post(f"{AUTH}/logout", headers=_csrf(client))
    assert resp.status_code == 204
    assert client.get(f"{AUTH}/me", headers=_bearer(token)).status_code == 401  # the old token is dead
    assert _audit(db, enrolment.staff.id, "PLATFORM_LOGOUT")


def test_logout_all_revokes_every_session(db):
    enrolment = _staff(db)
    a, b = _fresh_client(), _fresh_client()
    _sign_in(a, db, enrolment)
    _sign_in(b, db, enrolment, steps=1)
    resp = a.post(f"{AUTH}/logout-all", headers=_csrf(a))
    assert resp.status_code == 200 and resp.json()["sessions_revoked"] == 2
    assert a.get(f"{AUTH}/me").status_code == 401
    assert b.get(f"{AUTH}/me").status_code == 401
    assert _audit(db, enrolment.staff.id, "PLATFORM_ALL_SESSIONS_REVOKED")


def test_refresh_rotates_and_detects_reuse(client, db):
    enrolment = _staff(db)
    _sign_in(client, db, enrolment)
    old_secret = client.cookies.get(REFRESH_COOKIE, path=AUTH)
    first = client.post(f"{AUTH}/refresh", headers=_csrf(client))
    assert first.status_code == 200, first.text
    new_secret = client.cookies.get(REFRESH_COOKIE, path=AUTH)
    assert new_secret and new_secret != old_secret
    # Presenting the rotated-away secret again = theft signal: the session is revoked.
    thief = _fresh_client()
    thief.cookies.set(REFRESH_COOKIE, old_secret, path=AUTH)
    thief.cookies.set(CSRF_COOKIE, "x", path="/")
    assert thief.post(f"{AUTH}/refresh", headers={CSRF_HEADER: "x"}).status_code == 401
    assert client.get(f"{AUTH}/me").status_code == 401
    assert _audit(db, enrolment.staff.id, "PLATFORM_REFRESH_REUSE_DETECTED")


def test_refresh_requires_csrf(client, db):
    _sign_in(client, db, _staff(db))
    assert client.post(f"{AUTH}/refresh").status_code == 403
    assert client.post(f"{AUTH}/refresh", headers={CSRF_HEADER: "wrong"}).status_code == 403


def test_cookie_authenticated_writes_require_csrf(client, db):
    _sign_in(client, db, _staff(db))
    assert client.post(f"{AUTH}/logout").status_code == 403
    assert client.post(f"{AUTH}/logout-all", headers={CSRF_HEADER: "forged"}).status_code == 403
    assert client.get(f"{AUTH}/me").status_code == 200  # reads need no CSRF


@pytest.mark.parametrize("field", ["expires_at", "idle_expires_at"])
def test_expired_session_rejected(client, db, field):
    me = _sign_in(client, db, _staff(db)).json()
    row = db.get(PlatformSession, me["session_id"])
    setattr(row, field, utcnow() - timedelta(seconds=1))
    db.commit()
    assert client.get(f"{AUTH}/me").status_code == 401
    assert client.post(f"{AUTH}/refresh", headers=_csrf(client)).status_code == 401


def test_deactivation_kills_live_sessions(client, db):
    enrolment = _staff(db)
    _sign_in(client, db, enrolment)
    svc.deactivate_staff(db, email=enrolment.staff.email, reason="left", actor="test")
    assert client.get(f"{AUTH}/me").status_code == 401
    assert _audit(db, enrolment.staff.id, "PLATFORM_STAFF_DEACTIVATED")


def test_password_and_two_factor_reset_revoke_sessions(db):
    enrolment = _staff(db)
    a = _fresh_client()
    _sign_in(a, db, enrolment)
    svc.set_password(db, email=enrolment.staff.email, password="Another-Passw0rd-2026", actor="test")
    assert a.get(f"{AUTH}/me").status_code == 401
    new = svc.reset_two_factor(db, email=enrolment.staff.email, reason="lost phone", actor="test")
    assert new.totp_secret != enrolment.totp_secret
    assert _audit(db, enrolment.staff.id, "PLATFORM_PASSWORD_RESET") and _audit(db, enrolment.staff.id, "PLATFORM_2FA_RESET")


# --- tokens and confusion (A-M) -----------------------------------------------------------------------------


def test_A_tenant_token_on_tenant_endpoint_succeeds(client, tenant):
    assert _tenant_client().get(TENANT_ME, headers=tenant.headers()).status_code == 200


def test_B_tenant_token_on_platform_endpoint_rejected(client, tenant):
    assert client.get(f"{AUTH}/me", headers=tenant.headers()).status_code == 401
    assert client.get(f"{AUTH}/sessions", headers=tenant.headers()).status_code == 401


def test_C_platform_token_on_platform_endpoint_succeeds(client, db):
    _sign_in(client, db, _staff(db))
    token = _access(client)
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(token)).status_code == 200
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["aud"] == "platform" and claims["iss"] == "rooman-billing-platform" and claims["typ"] == "platform_access"
    assert {"sub", "sid", "exp", "iat", "jti"} <= set(claims) and "org" not in claims and "type" not in claims


def test_D_platform_token_on_tenant_endpoint_rejected(client, db, tenant):
    _sign_in(client, db, _staff(db))
    token = _access(client)
    assert _tenant_client().get(TENANT_ME, headers=_bearer(token)).status_code == 401
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)


@pytest.mark.parametrize("aud", ["tenant", "platform-support", "", ["platform", "tenant"]])
def test_E_wrong_audience_rejected(client, db, aud):
    me = _sign_in(client, db, _staff(db)).json()
    token = _sign(_platform_claims(me["staff"]["id"], me["session_id"], aud=aud), settings.PLATFORM_JWT_SECRET)
    with pytest.raises(jwt.PyJWTError):
        decode_platform_access_token(token)
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(token)).status_code == 401


@pytest.mark.parametrize("iss", ["rooman-billing", "rooman-billing-platform-x", ""])
def test_F_wrong_issuer_rejected(client, db, iss):
    me = _sign_in(client, db, _staff(db)).json()
    token = _sign(_platform_claims(me["staff"]["id"], me["session_id"], iss=iss), settings.PLATFORM_JWT_SECRET)
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(token)).status_code == 401


@pytest.mark.parametrize("extra", [{"typ": "access"}, {"typ": "platform_refresh"}, {"type": "access"}, {"org": "x"}])
def test_G_wrong_token_type_rejected(client, db, extra):
    me = _sign_in(client, db, _staff(db)).json()
    token = _sign(_platform_claims(me["staff"]["id"], me["session_id"], **extra), settings.PLATFORM_JWT_SECRET)
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(token)).status_code == 401


def test_H_expired_platform_token_rejected(client, db):
    me = _sign_in(client, db, _staff(db)).json()
    past = time.time() - 3600
    token = _sign(_platform_claims(me["staff"]["id"], me["session_id"], iat=past, exp=int(past + 600)), settings.PLATFORM_JWT_SECRET)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_platform_access_token(token)
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(token)).status_code == 401


def test_I_revoked_session_token_rejected(client, db):
    me = _sign_in(client, db, _staff(db)).json()
    token = _access(client)
    row = db.get(PlatformSession, me["session_id"])
    row.revoked_at = utcnow()
    db.commit()
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(token)).status_code == 401


def test_J_tenant_key_cannot_mint_platform_token(client, db):
    me = _sign_in(client, db, _staff(db)).json()
    forged = _sign(_platform_claims(me["staff"]["id"], me["session_id"]), settings.SECRET_KEY)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_platform_access_token(forged)
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(forged)).status_code == 401


def test_K_platform_key_cannot_mint_tenant_token(client, tenant):
    now = time.time()
    forged = _sign({"sub": tenant.owner.id, "org": tenant.organization.id, "role": "owner", "type": "access",
                    "aud": TENANT_TOKEN_AUDIENCE, "iss": TOKEN_ISSUER, "iat": now, "exp": int(now + 600),
                    "jti": uuid.uuid4().hex}, settings.PLATFORM_JWT_SECRET)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)
    assert _tenant_client().get(TENANT_ME, headers=_bearer(forged)).status_code == 401


@pytest.mark.parametrize("missing", ["sub", "sid", "aud", "iss", "typ", "exp", "iat", "jti"])
def test_L_missing_required_claims_rejected(client, db, missing):
    me = _sign_in(client, db, _staff(db)).json()
    token = _sign(_platform_claims(me["staff"]["id"], me["session_id"], **{missing: ...}), settings.PLATFORM_JWT_SECRET)
    with pytest.raises(jwt.PyJWTError):
        decode_platform_access_token(token)
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(token)).status_code == 401


def test_M_malformed_tokens_rejected(client, db):
    _sign_in(client, db, _staff(db))
    good = _access(client)
    enc = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()  # noqa: E731
    head, body, sig = good.split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    for token in ("garbage", "a.b.c", good[:-4], f"{head}.{enc(dict(claims, role='x'))}.{sig}",
                  f"{enc({'alg': 'none', 'typ': 'JWT'})}.{enc(claims)}.",
                  f"{enc({'alg': 'HS512', 'typ': 'JWT'})}.{body}.{sig}"):
        assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(token)).status_code == 401, token


def test_token_for_deleted_or_foreign_session_rejected(client, db):
    one, two = _staff(db), _staff(db)
    me_one = _sign_in(client, db, one).json()
    # A validly signed token pairing staff two with staff one's session.
    token = create_platform_access_token(staff_id=two.staff.id, session_id=me_one["session_id"], role="platform_administrator", auth_time=utcnow())
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(token)).status_code == 401
    token = create_platform_access_token(staff_id=one.staff.id, session_id=str(uuid.uuid4()), role="platform_administrator", auth_time=utcnow())
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(token)).status_code == 401


def test_platform_disabled_without_key(client, db, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_JWT_SECRET", "")
    enrolment = _staff(db)
    assert _challenge(client, enrolment).status_code == 503
    assert client.get(f"{AUTH}/me").status_code == 503
    with pytest.raises(platform_security.PlatformAuthNotConfigured):
        create_platform_access_token(staff_id="x", session_id="y", role="z", auth_time=utcnow())
    # tenant auth keeps working
    assert _tenant_client().post("/api/v1/auth/login", json={"email": "nobody@example.test", "password": "x"}).status_code == 401


def test_platform_key_must_differ_from_tenant_key():
    from backend.app.core.config import Settings

    strong = "b7c1e9a4f02d58e36a9c47d1b0e2f8a51c3d6e9f04a7b2c5"
    with pytest.raises(ValueError):
        Settings(SECRET_KEY=strong, PLATFORM_JWT_SECRET=strong)
    with pytest.raises(ValueError):
        Settings(PLATFORM_JWT_SECRET="too-short")
    assert Settings(SECRET_KEY=strong, PLATFORM_JWT_SECRET=strong[::-1] + "Z9").platform_auth_enabled


def test_platform_secret_is_masked():
    assert settings.PLATFORM_JWT_SECRET not in repr(settings)


# --- authorization dependencies ----------------------------------------------------------------------------


def _role_app():
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)

    @app.get("/any")
    def any_staff(ctx: PlatformContext = Depends(require_platform_staff)):
        return {"role": ctx.role.value}

    @app.get("/admin")
    def admin_only(ctx: PlatformContext = Depends(require_platform_administrator)):
        return {"ok": True}

    @app.get("/ops")
    def ops(ctx: PlatformContext = Depends(require_platform_operations)):
        return {"ok": True}

    @app.get("/support")
    def support(ctx: PlatformContext = Depends(require_platform_support)):
        return {"ok": True}

    return TestClient(app)


@pytest.mark.parametrize(
    "role,expected",
    [
        (ADMIN, {"/any": 200, "/admin": 200, "/ops": 200, "/support": 200}),
        (OPS, {"/any": 200, "/admin": 403, "/ops": 200, "/support": 403}),
        (SUPPORT, {"/any": 200, "/admin": 403, "/ops": 403, "/support": 200}),
    ],
    ids=["administrator", "operations", "support"],
)
def test_role_dependencies(client, db, role, expected):
    _sign_in(client, db, _staff(db, role=role))
    token = _access(client)
    roles = _role_app()
    for path, status in expected.items():
        assert roles.get(path, headers=_bearer(token)).status_code == status, (role, path)


def test_role_comes_from_database_not_token(client, db):
    enrolment = _staff(db, role=SUPPORT)
    _sign_in(client, db, enrolment)
    # A token claiming administrator for a support staff member does not grant it.
    me = client.get(f"{AUTH}/me").json()
    token = create_platform_access_token(staff_id=enrolment.staff.id, session_id=me["session_id"],
                                         role="platform_administrator", auth_time=utcnow())
    assert _role_app().get("/admin", headers=_bearer(token)).status_code == 403


def test_tenant_users_and_anonymous_rejected_by_role_dependencies(tenant):
    roles = _role_app()
    for path in ("/any", "/admin", "/ops", "/support"):
        assert roles.get(path).status_code == 401
        assert roles.get(path, headers=tenant.headers()).status_code == 401  # tenant Owner token
        assert roles.get(path, headers=tenant.headers_for_role(MemberRole.ADMIN)).status_code == 401


def test_no_wildcard_role_exists():
    import backend.app.api.platform_deps as deps

    assert {r.value for r in PlatformRole} == {"platform_administrator", "platform_operations", "platform_support"}
    assert not [name for name in dir(deps) if "super" in name.lower() or "everything" in name.lower()]


# --- isolation --------------------------------------------------------------------------------------------------


def test_platform_session_is_not_tenant_session(client, db, tenant):
    """Signing in as platform staff yields nothing that tenant endpoints accept, and a tenant sign-in
    yields nothing platform endpoints accept - with cookies or bearer tokens."""
    _sign_in(client, db, _staff(db))
    # Tenant endpoints do not exist on the platform host...
    assert client.get(TENANT_ME).status_code == 404
    assert client.get("/api/v1/customers").status_code == 404
    # ...and the platform cookies, even replayed by hand to the tenant host, are not tenant credentials.
    stolen = {"Cookie": "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)}
    assert client.cookies.jar
    tenant_client = _tenant_client()
    assert tenant_client.get(TENANT_ME, headers=stolen).status_code == 401
    assert tenant_client.get("/api/v1/customers", headers=stolen).status_code == 401
    resp = tenant_client.post("/api/v1/auth/login", json={"email": tenant.owner.email, "password": "Str0ngPassw0rd!"})
    assert resp.status_code == 200, resp.text
    tenant_token = resp.json()["access_token"]
    # The platform API does not exist on the tenant host; on the platform host a tenant token fails.
    assert tenant_client.get(f"{AUTH}/me", headers=_bearer(tenant_token)).status_code == 404
    assert _fresh_client().get(f"{AUTH}/me", headers=_bearer(tenant_token)).status_code == 401
    assert _fresh_client().get(f"{AUTH}/me").status_code == 401


def test_platform_routes_expose_no_tenant_data(client, db):
    me = _sign_in(client, db, _staff(db)).json()
    assert set(me) == {"staff", "session_id", "session_expires_at", "access_expires_in"}
    assert set(me["staff"]) == {"id", "email", "full_name", "role", "last_login_at"}
    from backend.app.main import app

    platform_paths = {r.path for r in app.routes if "/platform" in getattr(r, "path", "")}
    auth_paths = {f"{AUTH}/{p}" for p in ("login", "2fa", "refresh", "me", "sessions", "sessions/{session_id}", "logout", "logout-all", "step-up")}
    # Phase 3 console (metadata only; see test_platform_console.py for what each returns).
    console = "/api/v1/platform"
    org = f"{console}/organizations/{{organization_id}}"
    console_paths = {f"{console}/dashboard", f"{console}/health", f"{console}/audit", f"{console}/organizations",
                     org, f"{org}/activity", f"{org}/suspend", f"{org}/reactivate", f"{org}/schedule-deletion",
                     f"{org}/cancel-deletion", f"{org}/jobs/pause", f"{org}/jobs/resume", f"{console}/staff",
                     f"{console}/staff/{{staff_id}}", f"{console}/staff/{{staff_id}}/deactivate",
                     f"{console}/staff/{{staff_id}}/activate", f"{console}/staff/{{staff_id}}/revoke-sessions",
                     f"{org}/revoke-sessions", f"{console}/jobs"}
    assert platform_paths == auth_paths | console_paths


# --- audit ---------------------------------------------------------------------------------------------------------


def test_successful_sign_in_is_audited(client, db):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment, steps=0).json()
    actions = [row.action for row in _audit(db, enrolment.staff.id)]
    for expected in ("PLATFORM_STAFF_CREATED", "PLATFORM_LOGIN_PASSWORD_VERIFIED", "PLATFORM_2FA_SUCCEEDED", "PLATFORM_LOGIN_SUCCEEDED"):
        assert expected in actions, actions
    ok = _audit(db, enrolment.staff.id, "PLATFORM_LOGIN_SUCCEEDED")[-1]
    assert ok.session_id == me["session_id"] and ok.result == "success"
    assert ok.ip_address and ok.user_agent and ok.staff_email_snapshot == enrolment.staff.email


def test_failures_are_audited_including_unknown_emails(client, db):
    enrolment = _staff(db)
    _challenge(client, enrolment, password="Wrong-Passw0rd-xx")
    stranger = f"stranger-{uuid.uuid4().hex[:6]}@rooman.test"
    client.post(f"{AUTH}/login", json={"email": stranger, "password": "Whatever-Passw0rd-1"})
    challenge = _challenge(client, enrolment).json()["challenge_token"]
    client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": "000000"})
    failed = _audit(db, enrolment.staff.id, "PLATFORM_LOGIN_FAILED")[-1]
    assert failed.result == "failure" and failed.details["reason"] == "bad_password"
    unknown = _audit(db, action="PLATFORM_LOGIN_FAILED")
    assert any(r.platform_staff_id is None and r.staff_email_snapshot == stranger for r in unknown)
    assert _audit(db, enrolment.staff.id, "PLATFORM_2FA_FAILED")[-1].result == "failure"


def test_audit_never_contains_credentials(client, db):
    enrolment = _staff(db)
    code = _code(enrolment.totp_secret)
    _challenge(client, enrolment, password="Wrong-Passw0rd-xx")
    challenge = _challenge(client, enrolment).json()["challenge_token"]
    client.post(f"{AUTH}/2fa", json={"challenge_token": challenge, "code": code})
    refresh_secret = client.cookies.get(REFRESH_COOKIE, path=AUTH)
    access = _access(client)
    client.post(f"{AUTH}/logout", headers=_csrf(client))
    dump = json.dumps([
        {c.name: str(getattr(row, c.name)) for c in PlatformAuditLog.__table__.columns}
        for row in _audit(db, enrolment.staff.id)
    ])
    for secret in (PASSWORD, "Wrong-Passw0rd-xx", code, enrolment.totp_secret, challenge, refresh_secret, access):
        assert secret and secret not in dump
    staff = db.get(PlatformStaff, enrolment.staff.id)
    assert staff.hashed_password not in dump and staff.totp_secret not in dump


def test_audit_details_scrub_credential_keys(db):
    from backend.app.services import platform_audit

    row = platform_audit.record(db, action="TEST", result="success", details={
        "password": "p", "code": "123456", "refresh_token": "t", "totp_secret": "s", "reason": "kept",
    })
    db.commit()
    assert row.details == {"reason": "kept"}

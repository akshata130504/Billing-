"""Sign in with Rooman One (OpenID Connect): /auth/rooman-one/*.

Rooman One is replaced by an in-test RSA key, discovery document and token endpoint; the
id_token checks themselves (signature, aud, iss, nonce, state) are the real ones.
"""
import time
import uuid
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.models import AuditLog, MemberRole, Membership, Organization, User
from backend.app.models.base import utcnow
from backend.app.models.platform import PlatformAuditLog
from backend.app.services import rooman_one_service as rooman_one

ISSUER = "https://roomanone.example.test"
CLIENT_ID = "billing-web-test"
BASE = "/api/v1/auth/rooman-one"
COOKIE = "rb_rooman_one_flow"

ROOMAN_ONE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _SigningKey:
    key = ROOMAN_ONE_KEY.public_key()


class _JwkClient:
    def get_signing_key_from_jwt(self, token):
        return _SigningKey()


@pytest.fixture()
def rooman_one_on(monkeypatch, client):
    monkeypatch.setattr(settings, "OIDC_ISSUER", ISSUER)
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(settings, "OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(settings, "OIDC_REDIRECT_URI", "http://testserver/api/v1/auth/rooman-one/callback")
    monkeypatch.setattr(settings, "REDIS_URL", None)
    monkeypatch.setattr(
        rooman_one,
        "discovery",
        lambda: {
            "authorization_endpoint": ISSUER + "/oauth/authorize",
            "token_endpoint": ISSUER + "/oauth/token",
            "jwks_uri": ISSUER + "/oauth/jwks",
        },
    )
    monkeypatch.setattr(rooman_one, "_jwk_client", lambda uri: _JwkClient())
    client.cookies.clear()
    yield
    client.cookies.clear()


def _person(**overrides):
    claims = {
        "sub": str(uuid.uuid4()),
        "org_id": str(uuid.uuid4()),
        "org_name": "Rooman One Org",
        "role": "admin",
        "email": f"r1-{uuid.uuid4().hex[:8]}@example.test",
        "name": "Rooman One Person",
    }
    claims.update(overrides)
    return claims


def _id_token(claims, nonce, *, key=ROOMAN_ONE_KEY, aud=CLIENT_ID, iss=ISSUER):
    now = int(time.time())
    body = {"iss": iss, "aud": aud, "iat": now, "exp": now + 300, "nonce": nonce, **claims}
    return jwt.encode(body, key, algorithm="RS256")


def _start(client, next_path="/invoices"):
    r = client.get(f"{BASE}/start", params={"next": next_path}, follow_redirects=False)
    assert r.status_code == 303, r.text
    query = parse_qs(urlparse(r.headers["location"]).query)
    return query, r.cookies.get(COOKIE)


def _sign_in(client, monkeypatch, claims, *, token_kwargs=None, nonce=None, next_path="/invoices"):
    """Full browser round trip; returns the callback's redirect URL."""
    query, cookie = _start(client, next_path)
    token = _id_token(claims, nonce or query["nonce"][0], **(token_kwargs or {}))
    monkeypatch.setattr(rooman_one, "exchange_code", lambda code, verifier: token)
    client.cookies.set(COOKIE, cookie, path=BASE)
    r = client.get(f"{BASE}/callback", params={"code": "c0de", "state": query["state"][0]}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"]


def _handoff(location):
    assert "/auth/rooman-one#handoff=" in location, location
    return parse_qs(urlparse(location).fragment)["handoff"][0]


def _sso_error(location):
    assert "/login?sso_error=" in location, location
    return parse_qs(urlparse(location).query)["sso_error"][0]


def _exchange(client, handoff):
    return client.post(f"{BASE}/exchange", json={"handoff": handoff})


# --- off until configured -----------------------------------------------------------


def test_off_until_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "OIDC_ISSUER", None)
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", None)
    assert client.get(BASE).json() == {"enabled": False}
    assert client.get(f"{BASE}/start", follow_redirects=False).status_code == 404
    assert client.get(f"{BASE}/callback", follow_redirects=False).status_code == 404
    assert client.post(f"{BASE}/exchange", json={"handoff": "x"}).status_code == 404


def test_start_redirects_with_pkce_and_sets_flow_cookie(client, rooman_one_on):
    assert client.get(BASE).json() == {"enabled": True}
    r = client.get(f"{BASE}/start", params={"next": "/invoices"}, follow_redirects=False)
    assert r.status_code == 303
    url = urlparse(r.headers["location"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == ISSUER + "/oauth/authorize"
    q = parse_qs(url.query)
    assert q["client_id"] == [CLIENT_ID] and q["response_type"] == ["code"]
    assert q["scope"] == ["openid profile email"]
    assert q["code_challenge_method"] == ["S256"] and len(q["code_challenge"][0]) == 43
    assert q["state"][0] and q["nonce"][0]
    set_cookie = r.headers["set-cookie"].lower()
    assert COOKIE in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie
    assert "path=/api/v1/auth/rooman-one" in set_cookie
    flow = rooman_one.unseal(r.cookies.get(COOKIE))
    assert flow["state"] == q["state"][0] and flow["next"] == "/invoices"


@pytest.mark.parametrize("bad", ["//evil.example", "/\\evil.example", "https://evil.example", "evil"])
def test_next_cannot_leave_billing(client, rooman_one_on, bad):
    _, cookie = _start(client, bad)
    assert rooman_one.unseal(cookie)["next"] == "/dashboard"


# --- first sign-in and later sign-ins -------------------------------------------------


def test_first_sign_in_creates_organization_and_owner_then_signs_in(client, db, rooman_one_on, monkeypatch):
    claims = _person()
    location = _sign_in(client, monkeypatch, claims)
    r = _exchange(client, _handoff(location))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] and body["refresh_token"] and body["next"] == "/invoices"

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200, me.text
    assert me.json()["user"]["id"] == claims["sub"]
    assert me.json()["organization"]["id"] == claims["org_id"]

    db.expire_all()
    org = db.get(Organization, claims["org_id"])
    assert org.name == "Rooman One Org" and org.trial_started_at is not None and org.trial_ends_at is not None
    user = db.get(User, claims["sub"])
    assert user.email == claims["email"] and user.hashed_password is None and user.email_verified_at is not None
    membership = db.scalars(select(Membership).where(Membership.user_id == user.id)).one()
    assert membership.role == MemberRole.OWNER and membership.organization_id == org.id
    actions = set(db.scalars(select(PlatformAuditLog.action).where(PlatformAuditLog.organization_id == org.id)))
    assert {"ORGANIZATION_CREATED", "ORGANIZATION_TRIAL_STARTED"} <= actions
    login_audit = db.scalars(
        select(AuditLog).where(AuditLog.action == "USER_LOGGED_IN", AuditLog.entity_id == user.id)
    ).first()
    assert login_audit is not None and login_audit.after_state.get("via") == "rooman_one"


def test_existing_user_signs_in_again_without_duplicates(client, db, rooman_one_on, monkeypatch):
    claims = _person()
    assert _exchange(client, _handoff(_sign_in(client, monkeypatch, claims))).status_code == 200
    assert _exchange(client, _handoff(_sign_in(client, monkeypatch, claims))).status_code == 200
    db.expire_all()
    assert len(db.scalars(select(Membership).where(Membership.user_id == claims["sub"])).all()) == 1


def test_colleague_joins_with_mapped_role(client, db, rooman_one_on, monkeypatch):
    founder = _person()
    assert _exchange(client, _handoff(_sign_in(client, monkeypatch, founder))).status_code == 200
    for role, expected in (("admin", MemberRole.ADMIN), ("staff", MemberRole.FINANCE), ("viewer", MemberRole.VIEWER), ("auditor", MemberRole.VIEWER)):
        colleague = _person(org_id=founder["org_id"], role=role)
        assert _exchange(client, _handoff(_sign_in(client, monkeypatch, colleague))).status_code == 200
        db.expire_all()
        m = db.scalars(select(Membership).where(Membership.user_id == colleague["sub"])).one()
        assert m.organization_id == founder["org_id"] and m.role == expected, role


def test_existing_billing_email_is_refused_not_duplicated(client, db, tenant, rooman_one_on, monkeypatch):
    claims = _person(email=tenant.owner.email)
    message = _sso_error(_sign_in(client, monkeypatch, claims))
    assert "already has its own Rooman Billing account" in message
    db.expire_all()
    assert db.get(User, claims["sub"]) is None and db.get(Organization, claims["org_id"]) is None


def test_two_factor_user_gets_the_mfa_challenge(client, db, rooman_one_on, monkeypatch):
    claims = _person()
    assert _exchange(client, _handoff(_sign_in(client, monkeypatch, claims))).status_code == 200
    user = db.get(User, claims["sub"])
    user.totp_enabled_at = utcnow()
    db.commit()
    body = _exchange(client, _handoff(_sign_in(client, monkeypatch, claims))).json()
    assert body["mfa_required"] is True and body["mfa_token"] and "access_token" not in body


# --- refused ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "token_kwargs",
    [{"key": OTHER_KEY}, {"aud": "some-other-app"}, {"iss": "https://evil.example"}],
    ids=["other-signing-key", "wrong-aud", "wrong-iss"],
)
def test_untrusted_id_token_is_refused(client, db, rooman_one_on, monkeypatch, token_kwargs):
    claims = _person()
    message = _sso_error(_sign_in(client, monkeypatch, claims, token_kwargs=token_kwargs))
    assert "couldn't verify" in message
    assert db.get(User, claims["sub"]) is None


def test_nonce_from_another_flow_is_refused(client, db, rooman_one_on, monkeypatch):
    claims = _person()
    message = _sso_error(_sign_in(client, monkeypatch, claims, nonce="nonce-of-an-earlier-sign-in"))
    assert "couldn't verify" in message
    assert db.get(User, claims["sub"]) is None


def test_missing_forged_or_replayed_state_is_refused(client, rooman_one_on, monkeypatch):
    query, cookie = _start(client)
    token = _id_token(_person(), query["nonce"][0])
    monkeypatch.setattr(rooman_one, "exchange_code", lambda code, verifier: token)

    client.cookies.clear()  # no flow cookie
    r = client.get(f"{BASE}/callback", params={"code": "c", "state": query["state"][0]}, follow_redirects=False)
    assert "try again" in _sso_error(r.headers["location"])

    client.cookies.set(COOKIE, cookie, path=BASE)  # forged state
    r = client.get(f"{BASE}/callback", params={"code": "c", "state": "forged"}, follow_redirects=False)
    assert "try again" in _sso_error(r.headers["location"])

    client.cookies.set(COOKIE, cookie[:-2] + "xx", path=BASE)  # tampered cookie
    r = client.get(f"{BASE}/callback", params={"code": "c", "state": query["state"][0]}, follow_redirects=False)
    assert "try again" in _sso_error(r.headers["location"])

    client.cookies.set(COOKIE, cookie, path=BASE)  # first use works, a replay does not
    r = client.get(f"{BASE}/callback", params={"code": "c", "state": query["state"][0]}, follow_redirects=False)
    _handoff(r.headers["location"])
    client.cookies.set(COOKIE, cookie, path=BASE)
    r = client.get(f"{BASE}/callback", params={"code": "c", "state": query["state"][0]}, follow_redirects=False)
    assert "try again" in _sso_error(r.headers["location"])


def test_handoff_is_single_use_and_expires(client, rooman_one_on, monkeypatch):
    handoff = _handoff(_sign_in(client, monkeypatch, _person()))
    assert _exchange(client, handoff).status_code == 200
    assert _exchange(client, handoff).status_code == 401  # reused

    monkeypatch.setattr(rooman_one, "HANDOFF_TTL_SECONDS", -1)  # issued already expired
    stale = _handoff(_sign_in(client, monkeypatch, _person()))
    assert _exchange(client, stale).status_code == 401  # expired


def test_garbage_handoff_is_refused(client, rooman_one_on):
    assert _exchange(client, "not-a-real-handoff").status_code == 401

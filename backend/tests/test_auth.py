"""Authentication flows: signup, login, lockout, refresh rotation, passwords, resets, rate limiting."""
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.security import decode_access_token, hash_password
from backend.app.models import AuditLog, Membership, MemberRole, MembershipStatus, Organization, RefreshToken, User

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd!"  # matches conftest.Tenant members
NEW_PASSWORD = "An0therStr0ngPass"


def unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


_SENT_OTPS: dict = {}
_SENT_MAIL: list = []


@pytest.fixture(autouse=True)
def _capture_auth_email(monkeypatch):
    """Signup codes and reset links are only ever emailed; capture them for the tests."""
    from backend.app.services import auth_service

    _SENT_OTPS.clear()
    _SENT_MAIL.clear()

    def fake_otp(email, full_name, otp):
        _SENT_OTPS[email] = otp
        return True

    def fake_send(to, subject, text_body, html_body=None, **kwargs):
        _SENT_MAIL.append({"to": to, "subject": subject, "text": text_body, "html": html_body})
        return True

    monkeypatch.setattr(auth_service, "_send_signup_verification_email", fake_otp)
    monkeypatch.setattr(auth_service, "send_email", fake_send)


def emailed_reset_token(email: str) -> str:
    body = [m for m in _SENT_MAIL if m["to"] == email.lower()][-1]["text"]
    return token_of(next(word for word in body.split() if "reset-password?token=" in word))


def signup(client, **overrides):
    """Email-verified signup: request-verification, then verify-otp with the emailed code."""
    body = {
        "organization_name": overrides.pop("organization_name", f"Org {unique('signup')}"),
        "full_name": overrides.pop("full_name", "Sign Up"),
        "email": overrides.pop("email", f"{unique('user')}@example.test"),
        "password": overrides.pop("password", PASSWORD),
    }
    body.update(overrides)
    requested = client.post(f"{API}/auth/signup/request-verification", json=body)
    if requested.status_code != 200:
        return requested
    email = requested.json()["email"]
    return client.post(
        f"{API}/auth/signup/verify-otp", json={"email": email, "otp": _SENT_OTPS[email], "password": body["password"]}
    )


def test_legacy_unverified_signup_endpoint_is_gone(client):
    r = client.post(
        f"{API}/auth/signup",
        json={"organization_name": "X", "full_name": "Y", "email": f"{unique('legacy')}@example.test", "password": PASSWORD},
    )
    assert r.status_code == 410 and r.json()["error"]["code"] == "GONE"


def login(client, email, password=PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def audit_rows(db, action: str, entity_id: str | None = None):
    db.expire_all()
    stmt = select(AuditLog).where(AuditLog.action == action)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    return list(db.scalars(stmt.order_by(AuditLog.created_at)).all())


def token_of(reset_or_invite_url: str) -> str:
    return parse_qs(urlparse(reset_or_invite_url).query)["token"][0]


# --- signup ---------------------------------------------------------------------------


def test_signup_creates_org_owner_tokens_and_me(client, db):
    email = f"{unique('owner')}@Example.TEST"
    r = signup(client, organization_name="Acme Corp!  Pvt. Ltd", full_name="Ann Owner", email=email)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["token_type"] == "bearer" and data["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert data["access_token"] and data["refresh_token"]
    me = data["me"]
    assert me["user"]["email"] == email.lower()
    assert me["user"]["full_name"] == "Ann Owner"
    assert me["organization"]["slug"] == "acme-corp-pvt-ltd"
    assert me["organization"]["name"] == "Acme Corp!  Pvt. Ltd"
    assert me["organization"]["default_tax_rate_pct"] == "18.00"
    assert me["organization"]["created_at"].endswith("Z")
    assert me["membership"]["role"] == "owner" and me["membership"]["status"] == "active"
    assert me["membership"]["joined_at"] is not None
    assert [o["slug"] for o in me["organizations"]] == ["acme-corp-pvt-ltd"]
    assert "hashed_password" not in r.text and "token_hash" not in r.text

    claims = decode_access_token(data["access_token"])
    assert claims["org"] == me["organization"]["id"] and claims["role"] == "owner"

    # /me works with the issued access token and matches the signup payload
    r2 = client.get(f"{API}/auth/me", headers=bearer(data["access_token"]))
    assert r2.status_code == 200
    assert r2.json()["organization"]["id"] == me["organization"]["id"]

    rows = audit_rows(db, "USER_SIGNED_UP", me["user"]["id"])
    assert len(rows) == 1
    assert rows[0].organization_id == me["organization"]["id"]
    assert rows[0].actor_user_id == me["user"]["id"]
    assert rows[0].after_state["slug"] == "acme-corp-pvt-ltd"

    # refresh token is persisted hashed, never raw
    db.expire_all()
    stored = db.scalars(select(RefreshToken).where(RefreshToken.user_id == me["user"]["id"])).all()
    assert len(stored) == 1 and stored[0].token_hash != data["refresh_token"]
    assert stored[0].organization_id == me["organization"]["id"]


def test_signup_slug_is_made_unique(client):
    name = f"Slug Test {uuid.uuid4().hex[:6]}"
    first = signup(client, organization_name=name).json()["me"]["organization"]["slug"]
    second = signup(client, organization_name=name).json()["me"]["organization"]["slug"]
    third = signup(client, organization_name=name.upper()).json()["me"]["organization"]["slug"]
    assert second == f"{first}-2"
    assert third == f"{first}-3"


def test_signup_duplicate_email_is_conflict(client):
    email = f"{unique('dup')}@example.test"
    assert signup(client, email=email).status_code == 201
    r = signup(client, email=email.upper())
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_signup_enforces_password_policy(client):
    for weak in ("short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere"):
        r = signup(client, password=weak)
        assert r.status_code == 422, weak
        err = r.json()["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert "password" in err["details"]["fields"]


def test_signup_rejects_invalid_email_with_envelope(client):
    r = signup(client, email="not-an-email")
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "email" in err["details"]["fields"]


# --- login ----------------------------------------------------------------------------


def test_login_success_sets_last_login_and_audits(client, db, tenant):
    r = login(client, tenant.owner.email)
    assert r.status_code == 200, r.text
    tokens = r.json()
    assert tokens["token_type"] == "bearer"
    claims = decode_access_token(tokens["access_token"])
    assert claims["sub"] == tenant.owner.id and claims["org"] == tenant.organization.id

    me = client.get(f"{API}/auth/me", headers=bearer(tokens["access_token"])).json()
    assert me["user"]["last_login_at"] is not None
    assert me["organization"]["id"] == tenant.organization.id
    rows = audit_rows(db, "USER_LOGGED_IN", tenant.owner.id)
    assert rows and rows[0].actor_label == tenant.owner.email and rows[0].organization_id == tenant.organization.id


def test_login_wrong_password_and_unknown_email_look_the_same(client, db, tenant):
    bad = login(client, tenant.owner.email, "WrongPassw0rd!")
    unknown = login(client, f"{unique('ghost')}@example.test", "WrongPassw0rd!")
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["error"]["code"] == "UNAUTHORIZED"
    assert bad.json()["error"]["message"] == unknown.json()["error"]["message"]

    rows = audit_rows(db, "LOGIN_FAILED", tenant.owner.id)
    assert rows and rows[0].status.value == "denied" and rows[0].actor_label == tenant.owner.email

    # a correct login resets the (email, IP) failure counter
    from backend.app.models.identity import LoginThrottle

    db.expire_all()
    assert db.scalars(select(LoginThrottle).where(LoginThrottle.subject == tenant.owner.email)).first() is not None
    assert login(client, tenant.owner.email).status_code == 200
    db.expire_all()
    assert db.scalars(select(LoginThrottle).where(LoginThrottle.subject == tenant.owner.email)).first() is None


def _client_from(ip: str):
    """A TestClient whose TCP peer is a private proxy address forwarding X-Real-IP=ip."""
    from fastapi.testclient import TestClient

    from backend.app.main import app

    c = TestClient(app, client=("172.18.0.5", 50000))
    c.headers.update({"X-Real-IP": ip})
    return c


def test_failed_logins_throttle_per_account_and_ip(client, db, tenant):
    from backend.app.models.identity import LoginThrottle

    user = tenant.add_member("locky", MemberRole.FINANCE)
    db.commit()
    attacker = _client_from("203.0.113.66")
    victim = _client_from("198.51.100.7")
    for attempt in range(1, 5):
        r = login(attacker, user.email, "WrongPassw0rd!")
        assert r.status_code == 401
        assert r.json()["error"]["message"] == "Invalid email or password.", attempt
    fifth = login(attacker, user.email, "WrongPassw0rd!")
    assert fifth.status_code == 401
    assert "too many" in fifth.json()["error"]["message"].lower()

    # even the right password is refused from the throttled address...
    blocked = login(attacker, user.email)
    assert blocked.status_code == 401 and "too many" in blocked.json()["error"]["message"].lower()
    # ...but the real user on another address is not locked out
    assert login(victim, user.email).status_code == 200
    db.refresh(user)
    assert user.locked_until is None

    # unknown emails are throttled identically, so the message never reveals account existence
    ghost = f"{unique('ghost')}@example.test"
    for _ in range(4):
        login(attacker, ghost, "WrongPassw0rd!")
    assert fifth.json()["error"]["message"] == login(attacker, ghost, "WrongPassw0rd!").json()["error"]["message"]

    # once the block expires the address works again
    db.expire_all()
    row = db.scalars(select(LoginThrottle).where(LoginThrottle.subject == user.email, LoginThrottle.ip_address == "203.0.113.66")).one()
    row.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert login(attacker, user.email).status_code == 200


def test_login_requires_an_active_membership(client, db):
    user = User(email=f"{unique('orphan')}@example.test", full_name="No Org", hashed_password=hash_password(PASSWORD))
    db.add(user)
    db.commit()
    r = login(client, user.email)
    assert r.status_code == 401
    assert "active member" in r.json()["error"]["message"]


def test_login_picks_most_recent_membership(client, db, tenant):
    other = Organization(name="Newer Org", slug=unique("newer-org"))
    db.add(other)
    db.flush()
    db.add(
        Membership(
            organization_id=other.id,
            user_id=tenant.owner.id,
            role=MemberRole.VIEWER,
            status=MembershipStatus.ACTIVE,
            created_at=datetime.now(timezone.utc) + timedelta(seconds=5),
        )
    )
    db.commit()
    claims = decode_access_token(login(client, tenant.owner.email).json()["access_token"])
    assert claims["org"] == other.id and claims["role"] == "viewer"


def test_login_invalid_body_uses_validation_envelope(client):
    r = client.post(f"{API}/auth/login", json={"email": "nope"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert set(err["details"]["fields"]) >= {"email", "password"}


# --- refresh / logout -----------------------------------------------------------------


def test_refresh_rotates_and_detects_reuse(client, db, tenant):
    first = login(client, tenant.owner.email).json()
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert decode_access_token(second["access_token"])["org"] == tenant.organization.id

    # the rotated token records its successor
    from backend.app.core.security import hash_token

    db.expire_all()
    old_row = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == hash_token(first["refresh_token"]))).one()
    new_row = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == hash_token(second["refresh_token"]))).one()
    assert old_row.revoked_at is not None and old_row.replaced_by_id == new_row.id

    # replaying the old token kills the whole chain
    reuse = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401 and reuse.json()["error"]["code"] == "UNAUTHORIZED"
    chained = client.post(f"{API}/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert chained.status_code == 401

    db.expire_all()
    live = db.scalars(select(RefreshToken).where(RefreshToken.user_id == tenant.owner.id, RefreshToken.revoked_at.is_(None))).all()
    assert live == []


def test_refresh_rejects_unknown_and_expired_tokens(client, db, tenant):
    from backend.app.core.security import generate_opaque_token, hash_token

    assert client.post(f"{API}/auth/refresh", json={"refresh_token": "does-not-exist"}).status_code == 401
    raw = generate_opaque_token()
    db.add(
        RefreshToken(
            user_id=tenant.owner.id,
            organization_id=tenant.organization.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    db.commit()
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": raw})
    assert r.status_code == 401 and "expired" in r.json()["error"]["message"].lower()


def test_logout_revokes_token_and_is_idempotent(client, db, tenant):
    tokens = login(client, tenant.owner.email).json()
    headers = bearer(tokens["access_token"])
    r = client.post(f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]}, headers=headers)
    assert r.status_code == 204
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    # Access token is immediately revoked upon logout:
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401
    assert client.post(f"{API}/auth/logout", json={"refresh_token": "nope"}, headers=headers).status_code == 401
    # Anonymous logout is 401:
    assert client.post(f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    # Unknown refresh token with a new valid session is still 204 (idempotent):
    new_tokens = login(client, tenant.owner.email).json()
    new_headers = bearer(new_tokens["access_token"])
    assert client.post(f"{API}/auth/logout", json={"refresh_token": "nope"}, headers=new_headers).status_code == 204
    assert audit_rows(db, "USER_LOGGED_OUT", tenant.owner.id)


def test_me_requires_a_valid_bearer_token(client):
    r = client.get(f"{API}/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
    r = client.get(f"{API}/auth/me", headers=bearer("garbage"))
    assert r.status_code == 401


def test_me_lists_every_active_organization(client, db, tenant):
    other = Organization(name="Second Org", slug=unique("second-org"))
    db.add(other)
    db.flush()
    db.add(Membership(organization_id=other.id, user_id=tenant.owner.id, role=MemberRole.ADMIN, status=MembershipStatus.ACTIVE))
    third = Organization(name="Deactivated Org", slug=unique("deact-org"))
    db.add(third)
    db.flush()
    db.add(Membership(organization_id=third.id, user_id=tenant.owner.id, role=MemberRole.ADMIN, status=MembershipStatus.DEACTIVATED))
    db.commit()

    me = client.get(f"{API}/auth/me", headers=tenant.headers()).json()
    assert me["organization"]["id"] == tenant.organization.id
    assert {o["id"]: o["role"] for o in me["organizations"]} == {tenant.organization.id: "owner", other.id: "admin"}


# --- switch organization ------------------------------------------------------------------


def test_switch_organization_issues_tokens_for_that_org(client, db, tenant):
    other = Organization(name="Other Org", slug=unique("other-org"))
    db.add(other)
    db.flush()
    db.add(Membership(organization_id=other.id, user_id=tenant.owner.id, role=MemberRole.FINANCE, status=MembershipStatus.ACTIVE))
    stranger = Organization(name="Stranger Org", slug=unique("stranger-org"))
    db.add(stranger)
    db.commit()

    tokens = login(client, tenant.owner.email).json()
    r = client.post(f"{API}/auth/switch-organization", json={"organization_id": other.id}, headers=bearer(tokens["access_token"]))
    assert r.status_code == 200, r.text
    switched = r.json()
    claims = decode_access_token(switched["access_token"])
    assert claims["org"] == other.id and claims["role"] == "finance"
    me = client.get(f"{API}/auth/me", headers=bearer(switched["access_token"])).json()
    assert me["organization"]["id"] == other.id and me["membership"]["role"] == "finance"

    # the previous session is untouched
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200

    denied = client.post(f"{API}/auth/switch-organization", json={"organization_id": stranger.id}, headers=bearer(switched["access_token"]))
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "FORBIDDEN"


# --- change password ----------------------------------------------------------------------


def test_change_password_revokes_other_sessions(client, db, tenant):
    user = tenant.add_member("changer", MemberRole.ADMIN)
    db.commit()
    session_a = login(client, user.email).json()
    session_b = login(client, user.email).json()
    headers = bearer(session_a["access_token"])

    wrong = client.post(
        f"{API}/auth/change-password",
        json={"current_password": "Wr0ngCurrent!!", "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert wrong.status_code == 422 and "current_password" in wrong.json()["error"]["details"]["fields"]

    weak = client.post(f"{API}/auth/change-password", json={"current_password": PASSWORD, "new_password": "weak"}, headers=headers)
    assert weak.status_code == 422 and "new_password" in weak.json()["error"]["details"]["fields"]

    ok = client.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD, "refresh_token": session_a["refresh_token"]},
        headers=headers,
    )
    assert ok.status_code == 204, ok.text

    # the caller's own refresh token survives, the other session is gone
    # (check the live one first: replaying a revoked token deliberately revokes the whole chain)
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": session_a["refresh_token"]}).status_code == 200
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": session_b["refresh_token"]}).status_code == 401

    assert login(client, user.email, PASSWORD).status_code == 401
    assert login(client, user.email, NEW_PASSWORD).status_code == 200
    assert audit_rows(db, "PASSWORD_CHANGED", user.id)


def test_change_password_without_refresh_token_revokes_everything(client, db, tenant):
    user = tenant.add_member("changer2", MemberRole.VIEWER)
    db.commit()
    session = login(client, user.email).json()
    r = client.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=bearer(session["access_token"]),
    )
    assert r.status_code == 204
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": session["refresh_token"]}).status_code == 401


# --- forgot / reset password ----------------------------------------------------------------


def test_forgot_and_reset_password_flow(client, db, tenant):
    user = tenant.add_member("forgetful", MemberRole.FINANCE)
    db.commit()
    session = login(client, user.email).json()

    unknown = client.post(f"{API}/auth/forgot-password", json={"email": f"{unique('nobody')}@example.test"})
    assert unknown.status_code == 202
    assert "reset_url" not in unknown.json() and unknown.json()["message"]

    r = client.post(f"{API}/auth/forgot-password", json={"email": user.email.upper()})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["message"] == unknown.json()["message"]
    assert "reset_url" not in body  # the link is only ever emailed
    token = emailed_reset_token(user.email)
    assert audit_rows(db, "PASSWORD_RESET_REQUESTED", user.id)

    weak = client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "weak"})
    assert weak.status_code == 422 and "new_password" in weak.json()["error"]["details"]["fields"]

    ok = client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert ok.status_code == 204, ok.text

    # single use, revokes existing sessions, new password works
    again = client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert again.status_code == 422 and again.json()["error"]["details"]["fields"]["token"]
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": session["refresh_token"]}).status_code == 401
    assert login(client, user.email, PASSWORD).status_code == 401
    assert login(client, user.email, NEW_PASSWORD).status_code == 200
    rows = audit_rows(db, "PASSWORD_RESET", user.id)
    assert rows and rows[0].organization_id == tenant.organization.id


def test_reset_password_clears_login_throttle(client, db, tenant):
    user = tenant.add_member("lockedout", MemberRole.VIEWER)
    db.commit()
    for _ in range(5):
        login(client, user.email, "WrongPassw0rd!")
    assert login(client, user.email).status_code == 401
    assert client.post(f"{API}/auth/forgot-password", json={"email": user.email}).status_code == 202
    token = emailed_reset_token(user.email)
    assert client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}).status_code == 204
    assert login(client, user.email, NEW_PASSWORD).status_code == 200


def test_new_reset_link_voids_older_ones(client, db, tenant):
    user = tenant.add_member("tworesets", MemberRole.VIEWER)
    db.commit()
    client.post(f"{API}/auth/forgot-password", json={"email": user.email})
    first = emailed_reset_token(user.email)
    client.post(f"{API}/auth/forgot-password", json={"email": user.email})
    second = emailed_reset_token(user.email)
    assert first != second
    assert client.post(f"{API}/auth/reset-password", json={"token": first, "new_password": NEW_PASSWORD}).status_code == 422
    assert client.post(f"{API}/auth/reset-password", json={"token": second, "new_password": NEW_PASSWORD}).status_code == 204


def test_reset_email_escapes_user_supplied_name(client, db, tenant):
    user = tenant.add_member("xssname", MemberRole.VIEWER)
    user.full_name = "<img src=x onerror=alert(1)>"
    db.commit()
    client.post(f"{API}/auth/forgot-password", json={"email": user.email})
    html_body = [m for m in _SENT_MAIL if m["to"] == user.email][-1]["html"]
    assert "<img" not in html_body and "&lt;img" in html_body


def test_reset_password_rejects_bad_or_expired_tokens(client, db, tenant):
    from backend.app.core.security import generate_opaque_token, hash_token
    from backend.app.models import PasswordResetToken

    bad = client.post(f"{API}/auth/reset-password", json={"token": "nonsense", "new_password": NEW_PASSWORD})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "VALIDATION_ERROR"
    # The reset page shows this field in its banner; it must be a sentence, not a code.
    assert "Request a new link" in bad.json()["error"]["details"]["fields"]["token"]

    raw = generate_opaque_token()
    db.add(PasswordResetToken(user_id=tenant.owner.id, token_hash=hash_token(raw), expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    db.commit()
    expired = client.post(f"{API}/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD})
    assert expired.status_code == 422
    assert login(client, tenant.owner.email).status_code == 200  # password untouched


# --- platform behaviour -----------------------------------------------------------------------


def test_rate_limit_returns_standard_envelope(client, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT", "2/minute")
    ip = f"10.9.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    proxied = _client_from(ip)
    body = {"email": f"{unique('rl')}@example.test"}
    assert proxied.post(f"{API}/auth/forgot-password", json=body).status_code == 202
    assert proxied.post(f"{API}/auth/forgot-password", json=body).status_code == 202
    # a spoofed X-Forwarded-For does not buy a fresh bucket
    limited = proxied.post(f"{API}/auth/forgot-password", json=body, headers={"X-Forwarded-For": "1.2.3.4"})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert limited.headers.get("Retry-After")
    # a different client IP (as reported by our proxy) is not affected
    other = _client_from("10.8.7.6").post(f"{API}/auth/forgot-password", json=body)
    assert other.status_code == 202


def test_public_token_rate_limit_is_per_endpoint_not_per_token(client, monkeypatch):
    """Walking the token space (a different /public/invoices/<token> per request) must share
    one bucket per client IP - not get a fresh bucket for every token."""
    monkeypatch.setattr(settings, "PUBLIC_RATE_LIMIT", "3/minute")
    proxied = _client_from(f"10.7.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}")
    statuses = [proxied.get(f"{API}/public/invoices/enum-{uuid.uuid4().hex}").status_code for _ in range(5)]
    assert statuses[:3] == [404, 404, 404]
    assert statuses[3:] == [429, 429]
    # the same scan from another client IP is unaffected
    assert _client_from("10.6.5.4").get(f"{API}/public/invoices/enum-{uuid.uuid4().hex}").status_code == 404


def test_client_ip_ignores_forwarded_headers_from_untrusted_peers():
    from starlette.requests import Request

    from backend.app.api.deps import client_ip

    def req(peer, headers):
        return Request({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()], "client": (peer, 1)})

    # direct internet peer: both headers are ignored
    assert client_ip(req("8.8.8.8", {"X-Forwarded-For": "1.1.1.1", "X-Real-IP": "2.2.2.2"})) == "8.8.8.8"
    # our proxy on the private network: X-Real-IP wins, X-Forwarded-For is never used
    assert client_ip(req("172.18.0.3", {"X-Forwarded-For": "1.1.1.1", "X-Real-IP": "2.2.2.2"})) == "2.2.2.2"
    assert client_ip(req("172.18.0.3", {"X-Forwarded-For": "1.1.1.1"})) == "172.18.0.3"
    assert client_ip(req("172.18.0.3", {"X-Real-IP": "not-an-ip"})) == "172.18.0.3"


def test_security_headers_are_set(client):
    r = client.get(f"{API}/meta/integrations")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert r.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert "Strict-Transport-Security" not in r.headers  # SECURE_COOKIES is off in tests


def test_meta_integrations_is_public(client):
    r = client.get(f"{API}/meta/integrations")
    assert r.status_code == 200
    assert r.json() == {"razorpay": {"enabled": False, "key_id": None}, "email": {"enabled": False}}


def test_openapi_documents_auth_routes(client):
    spec = client.get(f"{API}/openapi.json").json()
    for path in ("/auth/signup/request-verification", "/auth/signup/verify-otp", "/auth/login", "/auth/login/mfa", "/auth/sessions", "/auth/refresh", "/auth/me", "/auth/forgot-password", "/auth/accept-invitation", "/organization", "/team", "/team/invitations"):
        assert f"{API}{path}" in spec["paths"], path
    login_ok = spec["paths"][f"{API}/auth/login"]["post"]["responses"]["200"]
    assert "LoginResponse" in login_ok["content"]["application/json"]["schema"]["$ref"]

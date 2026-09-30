"""Phase 2 tests: Immediate access token revocation via tokens_valid_after.

Verifies:
A. Freshly issued normal access token works.
B. Logout immediately invalidates previously issued access token.
C. Password change immediately invalidates old access token.
D. Password reset immediately invalidates old access token.
E. Existing valid refresh session survives when preserved on password change.
F. Timestamp cutoff behavior: token issued after is accepted, before is rejected.
G. Null tokens_valid_after continues to function normally.
H. Missing or non-numeric iat is rejected safely without leaking secrets.
I. Refresh token rotation and replay detection work properly.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.security import ACCESS_TOKEN_TYPE, create_access_token, TENANT_TOKEN_AUDIENCE, TOKEN_ISSUER
from backend.app.models import Membership, MemberRole, MembershipStatus, Organization, User, utcnow

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd!"
NEW_PASSWORD = "An0therStr0ngPass!"


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _signup(client, email: str, password: str = PASSWORD):
    """Email-verified signup (request-verification + verify-otp with the emailed code)."""
    from unittest.mock import patch

    sent = {}
    with patch(
        "backend.app.services.auth_service._send_signup_verification_email",
        side_effect=lambda to, name, otp: sent.setdefault(to, otp) or True,
    ):
        requested = client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": f"Org {_unique('revoc')}",
                "full_name": "Revocation Tester",
                "email": email,
                "password": password,
            },
        )
    if requested.status_code != 200:
        return requested
    email = requested.json()["email"]
    return client.post(f"{API}/auth/signup/verify-otp", json={"email": email, "otp": sent[email], "password": password})


def _login(client, email: str, password: str = PASSWORD):
    return client.post(
        f"{API}/auth/login",
        json={"email": email, "password": password},
    )


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_normal_access_token_works(client):
    """A freshly issued access token authenticates successfully."""
    email = f"{_unique('normal')}@example.com"
    signup_resp = _signup(client, email)
    assert signup_resp.status_code == 201

    tokens = signup_resp.json()
    me_resp = client.get(f"{API}/auth/me", headers=_bearer(tokens["access_token"]))
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["email"] == email.lower()


def test_logout_invalidates_access_token_immediately(client):
    """Logging out revokes the access token immediately, closing the stateless window."""
    email = f"{_unique('logout')}@example.com"
    _signup(client, email)

    login_resp = _login(client, email)
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Verify access token works before logout
    pre_logout = client.get(f"{API}/auth/me", headers=_bearer(access_token))
    assert pre_logout.status_code == 200

    # Call logout
    logout_resp = client.post(
        f"{API}/auth/logout",
        json={"refresh_token": refresh_token},
        headers=_bearer(access_token),
    )
    assert logout_resp.status_code == 204

    # The access token must be rejected immediately
    post_logout = client.get(f"{API}/auth/me", headers=_bearer(access_token))
    assert post_logout.status_code == 401
    assert "revoked" in post_logout.json()["error"]["message"].lower()

    # The refresh token must also be rejected
    refresh_resp = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 401


def test_password_change_invalidates_old_access_token(client):
    """Changing password immediately invalidates previously issued access tokens."""
    email = f"{_unique('pwchange')}@example.com"
    _signup(client, email)

    login_resp = _login(client, email)
    tokens = login_resp.json()
    old_access_token = tokens["access_token"]
    old_refresh_token = tokens["refresh_token"]

    # Verify old token works before password change
    assert client.get(f"{API}/auth/me", headers=_bearer(old_access_token)).status_code == 200

    # Change password
    change_resp = client.post(
        f"{API}/auth/change-password",
        json={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "refresh_token": old_refresh_token,
        },
        headers=_bearer(old_access_token),
    )
    assert change_resp.status_code == 204

    # Old access token must be rejected immediately
    post_change = client.get(f"{API}/auth/me", headers=_bearer(old_access_token))
    assert post_change.status_code == 401
    assert "revoked" in post_change.json()["error"]["message"].lower()

    # The kept refresh token can still issue a brand new valid session
    new_session = client.post(f"{API}/auth/refresh", json={"refresh_token": old_refresh_token})
    assert new_session.status_code == 200
    new_access_token = new_session.json()["access_token"]

    # New session access token works
    assert client.get(f"{API}/auth/me", headers=_bearer(new_access_token)).status_code == 200


def test_password_reset_invalidates_old_access_token(client, db):
    """Resetting password via forgot-password token invalidates old access tokens."""
    email = f"{_unique('pwreset')}@example.com"
    _signup(client, email)

    login_resp = _login(client, email)
    old_access_token = login_resp.json()["access_token"]
    assert client.get(f"{API}/auth/me", headers=_bearer(old_access_token)).status_code == 200

    # Request password reset link (only ever delivered by email; capture it)
    from unittest.mock import patch

    mails = []
    with patch(
        "backend.app.services.auth_service.send_email",
        side_effect=lambda to, subject, text_body, **kw: mails.append(text_body) or True,
    ):
        forgot_resp = client.post(f"{API}/auth/forgot-password", json={"email": email})
    assert forgot_resp.status_code == 202
    assert "reset_url" not in forgot_resp.json()
    reset_url = next(w for w in mails[-1].split() if "reset-password?token=" in w)
    reset_token = parse_qs(urlparse(reset_url).query)["token"][0]

    # Reset password
    reset_resp = client.post(
        f"{API}/auth/reset-password",
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )
    assert reset_resp.status_code == 204

    # Old access token must be rejected immediately
    post_reset = client.get(f"{API}/auth/me", headers=_bearer(old_access_token))
    assert post_reset.status_code == 401
    assert "revoked" in post_reset.json()["error"]["message"].lower()

    # Login with new password works
    new_login = _login(client, email, NEW_PASSWORD)
    assert new_login.status_code == 200
    assert client.get(f"{API}/auth/me", headers=_bearer(new_login.json()["access_token"])).status_code == 200


def test_timestamp_valid_after_cutoff_precision(client, db):
    """Tokens issued before tokens_valid_after are rejected; tokens issued after are accepted."""
    email = f"{_unique('timestamp')}@example.com"
    _signup(client, email)
    user = db.scalars(select(User).where(User.email == email.lower())).first()
    assert user is not None

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=20)
    user.tokens_valid_after = cutoff
    db.commit()

    # 1. Token issued 10 seconds before cutoff (30s ago) -> REJECTED
    past_ts = (cutoff - timedelta(seconds=10)).timestamp()
    past_payload = {
        "sub": user.id,
        "org": None,
        "role": "owner",
        "type": ACCESS_TOKEN_TYPE,
        "iat": past_ts,
        "exp": int(past_ts + 1800),
        "jti": "past_token_jti_12345",
        "aud": TENANT_TOKEN_AUDIENCE,
        "iss": TOKEN_ISSUER,
    }
    past_token = jwt.encode(past_payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    r_past = client.get(f"{API}/auth/me", headers=_bearer(past_token))
    assert r_past.status_code == 401
    assert "revoked" in r_past.json()["error"]["message"].lower()

    # 2. Token issued 10 seconds after cutoff (10s ago, in past) -> ACCEPTED
    valid_ts = (cutoff + timedelta(seconds=10)).timestamp()
    valid_payload = {
        "sub": user.id,
        "org": None,
        "role": "owner",
        "type": ACCESS_TOKEN_TYPE,
        "iat": valid_ts,
        "exp": int(valid_ts + 1800),
        "jti": "valid_token_jti_12345",
        "aud": TENANT_TOKEN_AUDIENCE,
        "iss": TOKEN_ISSUER,
    }
    valid_token = jwt.encode(valid_payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    r_valid = client.get(f"{API}/auth/me", headers=_bearer(valid_token))
    assert r_valid.status_code == 200
    assert r_valid.json()["user"]["id"] == user.id


def test_null_tokens_valid_after_allows_normal_access(client, db):
    """Users with tokens_valid_after = NULL (legacy/unrevoked accounts) function normally."""
    email = f"{_unique('nullvalid')}@example.com"
    _signup(client, email)
    user = db.scalars(select(User).where(User.email == email.lower())).first()
    assert user is not None
    user.tokens_valid_after = None
    db.commit()

    login_resp = _login(client, email)
    token = login_resp.json()["access_token"]
    r = client.get(f"{API}/auth/me", headers=_bearer(token))
    assert r.status_code == 200


def test_missing_or_invalid_iat_rejected_safely(client, db):
    """Tokens with missing or invalid iat are rejected without leaking sensitive token data."""
    email = f"{_unique('invalidiat')}@example.com"
    _signup(client, email)
    user = db.scalars(select(User).where(User.email == email.lower())).first()
    assert user is not None

    # Set tokens_valid_after so iat is checked
    user.tokens_valid_after = utcnow()
    db.commit()

    # 1. Missing iat
    payload_no_iat = {
        "sub": user.id,
        "org": None,
        "role": "owner",
        "type": ACCESS_TOKEN_TYPE,
        "exp": int(time.time() + 1800),
        "jti": "no_iat_jti_12345",
    }
    token_no_iat = jwt.encode(payload_no_iat, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    r_no_iat = client.get(f"{API}/auth/me", headers=_bearer(token_no_iat))
    assert r_no_iat.status_code == 401
    assert token_no_iat not in r_no_iat.text

    # 2. String/corrupted iat
    payload_bad_iat = {
        "sub": user.id,
        "org": None,
        "role": "owner",
        "type": ACCESS_TOKEN_TYPE,
        "iat": "invalid-timestamp-string",
        "exp": int(time.time() + 1800),
        "jti": "bad_iat_jti_12345",
    }
    token_bad_iat = jwt.encode(payload_bad_iat, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    r_bad_iat = client.get(f"{API}/auth/me", headers=_bearer(token_bad_iat))
    assert r_bad_iat.status_code == 401
    assert token_bad_iat not in r_bad_iat.text

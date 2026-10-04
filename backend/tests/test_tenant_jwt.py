"""Tenant access tokens carry aud="tenant" / iss="rooman-billing" (platform phase 1).

Covers acceptance of new tokens, rejection of wrong/partial audience and issuer, expiry,
malformed and cross-kind tokens, and the tightly bounded transition for tokens minted before
aud/iss existed.
"""
import base64
import json
import time
import uuid

import jwt
import pytest

from backend.app.core import security
from backend.app.core.config import settings
from backend.app.core.security import (
    ACCESS_TOKEN_TYPE,
    TENANT_TOKEN_AUDIENCE,
    TOKEN_ISSUER,
    create_access_token,
    create_mfa_token,
    decode_access_token,
    decode_mfa_token,
)

ME = "/api/v1/auth/me"
LIFETIME = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def _claims(tenant, **overrides):
    now = time.time()
    claims = {
        "sub": tenant.owner.id,
        "org": tenant.organization.id,
        "role": "owner",
        "type": ACCESS_TOKEN_TYPE,
        "aud": TENANT_TOKEN_AUDIENCE,
        "iss": TOKEN_ISSUER,
        "iat": now,
        "exp": int(now + LIFETIME),
        "jti": uuid.uuid4().hex[:16],
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not ...}


def _sign(claims, key=None):
    return jwt.encode(claims, key or settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _me(client, token):
    return client.get(ME, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def legacy_window(monkeypatch):
    """Pretend this process started just now, so tokens issued a moment ago are 'pre-deploy'."""
    started = time.time() + 1
    monkeypatch.setattr(security, "LEGACY_TOKENS_ISSUED_BEFORE", started)
    return started


def _legacy(tenant, issued_ago=60, lifetime=LIFETIME, **overrides):
    iat = time.time() - issued_ago
    claims = _claims(tenant, aud=..., iss=..., iat=iat, exp=int(iat + lifetime))
    claims.update(overrides)
    return _sign({k: v for k, v in claims.items() if v is not ...})


# --- new tokens ---------------------------------------------------------------------------------


def test_new_tenant_token_carries_audience_and_issuer_and_is_accepted(client, tenant):
    token = create_access_token(tenant.owner.id, tenant.organization.id, "owner")
    unverified = jwt.decode(token, options={"verify_signature": False})
    assert unverified["aud"] == "tenant"
    assert unverified["iss"] == "rooman-billing"
    assert decode_access_token(token)["sub"] == tenant.owner.id
    assert _me(client, token).status_code == 200


def test_login_issues_tokens_with_audience(client, tenant):
    """The real login flow (not just the helper) mints aud/iss tokens."""
    # conftest.Tenant creates members with this password.
    resp = client.post("/api/v1/auth/login", json={"email": tenant.owner.email, "password": "Str0ngPassw0rd!"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    assert jwt.decode(token, options={"verify_signature": False})["aud"] == "tenant"
    assert _me(client, token).status_code == 200


# --- rejected tokens --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "platform"},
        {"aud": "tenant-support"},
        {"aud": ""},
        {"aud": ["tenant", "platform"]},  # merely listing "tenant" is not enough
        {"aud": ["platform"]},
    ],
    ids=["platform", "other", "empty", "list-with-tenant", "list-without-tenant"],
)
def test_wrong_audience_rejected(client, tenant, overrides):
    token = _sign(_claims(tenant, **overrides))
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)
    assert _me(client, token).status_code == 401


@pytest.mark.parametrize("iss", ["rooman-billing-platform", "someone-else", ""])
def test_wrong_issuer_rejected(client, tenant, iss):
    token = _sign(_claims(tenant, iss=iss))
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)
    assert _me(client, token).status_code == 401


def test_expired_token_rejected(client, tenant):
    past = time.time() - 2 * LIFETIME
    token = _sign(_claims(tenant, iat=past, exp=int(past + LIFETIME)))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)
    assert _me(client, token).status_code == 401


@pytest.mark.parametrize("missing", ["exp", "iat", "sub"])
def test_token_missing_core_claims_rejected(client, tenant, missing):
    token = _sign(_claims(tenant, **{missing: ...}))
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)
    assert _me(client, token).status_code == 401


def _tamper_payload(token: str, **changes) -> str:
    head, body, sig = token.split(".")
    padded = body + "=" * (-len(body) % 4)
    data = json.loads(base64.urlsafe_b64decode(padded))
    data.update(changes)
    new_body = base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    return f"{head}.{new_body}.{sig}"


def _alg_none(claims) -> str:
    enc = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{enc({'alg': 'none', 'typ': 'JWT'})}.{enc(claims)}."


def test_malformed_tokens_rejected(client, tenant):
    good = create_access_token(tenant.owner.id, tenant.organization.id, "owner")
    candidates = [
        "not-a-jwt",
        "a.b.c",
        good[:-5],  # truncated signature
        good + "x",
        _tamper_payload(good, org=str(uuid.uuid4())),  # payload edited, signature kept
        _tamper_payload(good, aud="platform"),
        _alg_none(_claims(tenant)),  # unsigned
    ]
    for token in candidates:
        with pytest.raises(jwt.PyJWTError):
            decode_access_token(token)
        assert _me(client, token).status_code == 401, token


def test_token_signed_with_another_key_rejected(client, tenant):
    """Token confusion: correct claims, wrong key (e.g. a future platform signing key)."""
    other_key = "a-completely-different-signing-key-for-another-audience-0123456789"
    for aud in (TENANT_TOKEN_AUDIENCE, "platform"):
        token = _sign(_claims(tenant, aud=aud), key=other_key)
        with pytest.raises(jwt.InvalidSignatureError):
            decode_access_token(token)
        assert _me(client, token).status_code == 401


def test_token_confusion_between_kinds(client, tenant):
    # An MFA challenge token is not an access token ...
    mfa = create_mfa_token(tenant.owner.id)
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(mfa)
    assert _me(client, mfa).status_code == 401
    # ... an access token is not an MFA challenge ...
    access = create_access_token(tenant.owner.id, tenant.organization.id, "owner")
    with pytest.raises(jwt.PyJWTError):
        decode_mfa_token(access)
    resp = client.post("/api/v1/auth/login/mfa", json={"mfa_token": access, "code": "000000"})
    assert resp.status_code in (400, 401), resp.text
    # ... and a tenant-audience token with another type is not an access token.
    other_type = _sign(_claims(tenant, type="refresh"))
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(other_type)
    assert _me(client, other_type).status_code == 401


def test_valid_token_for_an_org_without_membership_is_refused(client, tenant, db):
    """Tenant isolation is unchanged: a correctly signed tenant token naming another
    organization still needs an active membership there."""
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    token = _sign(_claims(tenant, org=other.organization.id))
    assert _me(client, token).status_code == 401


# --- legacy transition ------------------------------------------------------------------------------


def test_legacy_token_accepted_during_transition(client, tenant, legacy_window):
    token = _legacy(tenant)
    payload = decode_access_token(token)
    assert payload["sub"] == tenant.owner.id and "aud" not in payload
    assert _me(client, token).status_code == 200


def test_legacy_token_issued_after_process_start_rejected(client, tenant, monkeypatch):
    monkeypatch.setattr(security, "LEGACY_TOKENS_ISSUED_BEFORE", time.time() - 3600 + 60)
    token = _legacy(tenant, issued_ago=10)  # minted after "start": no legitimate issuer exists
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)
    assert _me(client, token).status_code == 401


def test_legacy_transition_ends_after_one_token_lifetime(client, tenant, monkeypatch):
    monkeypatch.setattr(security, "LEGACY_TOKENS_ISSUED_BEFORE", time.time() - LIFETIME - 5)
    token = _legacy(tenant, issued_ago=LIFETIME + 30, lifetime=LIFETIME * 10)
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)
    assert _me(client, token).status_code == 401


def test_legacy_token_must_not_outlive_configured_lifetime(client, tenant, legacy_window):
    token = _legacy(tenant, issued_ago=60, lifetime=LIFETIME * 4)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)
    assert _me(client, token).status_code == 401


@pytest.mark.parametrize(
    "partial",
    [{"aud": TENANT_TOKEN_AUDIENCE}, {"iss": TOKEN_ISSUER}, {"aud": "platform"}, {"iss": "rooman-billing-platform"}],
    ids=["aud-only", "iss-only", "platform-aud-only", "platform-iss-only"],
)
def test_partial_audience_or_issuer_is_never_legacy(client, tenant, legacy_window, partial):
    token = _legacy(tenant, **partial)
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)
    assert _me(client, token).status_code == 401


def test_expired_legacy_token_rejected(client, tenant, legacy_window):
    token = _legacy(tenant, issued_ago=LIFETIME + 120)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)
    assert _me(client, token).status_code == 401


def test_legacy_token_of_another_type_rejected(client, tenant, legacy_window):
    token = _legacy(tenant, type="mfa")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)
    assert _me(client, token).status_code == 401


def test_legacy_token_would_never_satisfy_a_platform_audience(tenant, legacy_window):
    """A future platform decoder requires aud="platform"; a legacy token has no aud at all."""
    token = _legacy(tenant)
    with pytest.raises(jwt.MissingRequiredClaimError):
        jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience="platform",
            options={"require": ["aud"]},
        )

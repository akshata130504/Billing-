"""Sign in with Rooman One (OpenID Connect authorization code + PKCE).

Rooman One (OIDC_ISSUER) is the identity provider for the Rooman apps. A person signed in
there opens Billing without a second password, and Billing keeps Rooman One's ids: the
id_token's `sub` is the Billing user id and its `org_id` the Billing organization id. The first
sign-in of an organization Billing has not seen creates it exactly as self-service sign-up does
(auth_service.create_organization). Billing's own email/password login is unchanged, and all of
this is off until OIDC_ISSUER and OIDC_CLIENT_ID are set. See docs/rooman-one-sign-in.md.

The browser flow lives in api/v1/endpoints/rooman_one_login.py; this module holds the parts
worth testing on their own: the flow cookie seal, id_token verification, setting up the person,
the one-time hand-over and the single-use registry.
"""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from typing import Any, Dict, Optional, Tuple, Union

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.encryption import DecryptionError, decrypt_str, encrypt_str
from backend.app.core.exceptions import ConflictError, UnauthorizedError
from backend.app.core.logging import logger
from backend.app.core.security import create_mfa_token
from backend.app.models import MemberRole, Membership, MembershipStatus, Organization, User
from backend.app.models.base import utcnow
from backend.app.schemas.organization import normalize_email
from backend.app.services import audit, auth_service, org_access
from backend.app.services.auth_service import MfaChallenge, TokenBundle

VIA = "rooman_one"
SCOPES = "openid profile email"
DISCOVERY_PATH = "/api/oauth/.well-known/openid-configuration"
FLOW_TTL_SECONDS = 10 * 60
HANDOFF_TTL_SECONDS = 60
DISCOVERY_TTL_SECONDS = 60 * 60
HTTP_TIMEOUT_SECONDS = 10

EMAIL_TAKEN = (
    "This email already has its own Rooman Billing account. "
    "Sign in to Billing with your email and password."
)
ACCOUNT_DISABLED = "Your Rooman Billing account is deactivated. Contact your organization Owner."
HANDOFF_INVALID = "This sign-in link is invalid or has expired. Please sign in again."


class RoomanOneError(Exception):
    """A sign-in that must not go ahead; the message is safe to show the person."""


def enabled() -> bool:
    return bool(settings.OIDC_ISSUER and settings.OIDC_CLIENT_ID)


# --- discovery + signing keys ---------------------------------------------------------

_discovery_cache: Dict[str, Any] = {}
_jwk_clients: Dict[str, jwt.PyJWKClient] = {}


def discovery() -> Dict[str, Any]:
    """Rooman One's OpenID configuration (cached for an hour)."""
    issuer = (settings.OIDC_ISSUER or "").rstrip("/")
    cached = _discovery_cache.get(issuer)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    response = httpx.get(issuer + DISCOVERY_PATH, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    doc = response.json()
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not doc.get(key):
            raise RoomanOneError(f"Rooman One discovery document has no {key}.")
    _discovery_cache[issuer] = (time.monotonic() + DISCOVERY_TTL_SECONDS, doc)
    return doc


def _jwk_client(jwks_uri: str) -> jwt.PyJWKClient:
    client = _jwk_clients.get(jwks_uri)
    if client is None:
        client = _jwk_clients[jwks_uri] = jwt.PyJWKClient(jwks_uri, timeout=HTTP_TIMEOUT_SECONDS)
    return client


# --- flow cookie: state, nonce and PKCE verifier, sealed with SECRET_KEY ----------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _seal_sig(body: str) -> str:
    key = settings.SECRET_KEY.encode("utf-8")
    return _b64(hmac.new(key, b"rooman-one-flow:" + body.encode("ascii"), hashlib.sha256).digest())


def seal(data: Dict[str, Any], ttl_seconds: int = FLOW_TTL_SECONDS) -> str:
    body = _b64(json.dumps({**data, "exp": int(time.time()) + ttl_seconds}, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_seal_sig(body)}"


def unseal(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """The sealed data, or None when it is missing, tampered with or expired."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _seal_sig(body)):
        return None
    try:
        data = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or int(data.get("exp", 0)) < int(time.time()):
        return None
    return data


def new_flow() -> Dict[str, str]:
    verifier = secrets.token_urlsafe(48)
    return {
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32),
        "verifier": verifier,
        "challenge": _b64(hashlib.sha256(verifier.encode("ascii")).digest()),
    }


def safe_next(path: Optional[str]) -> str:
    """Only same-origin app paths: no "//host", "/\\host" or other backslash forms."""
    if path and path.startswith("/") and not path.startswith("//") and "\\" not in path:
        return path
    return "/dashboard"


# --- single use: flow states and hand-overs ------------------------------------------

_used_local: Dict[str, float] = {}
_used_lock = threading.Lock()


def use_once(kind: str, value: str, ttl_seconds: int) -> bool:
    """True the first time `value` is seen within `ttl_seconds`, False on any replay.

    Redis (REDIS_URL) makes this hold across workers and replicas; without it (development,
    tests, a single process) an in-process registry is used.
    """
    key = f"rooman-one:{kind}:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
    if settings.REDIS_URL:
        import redis

        client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5)
        return bool(client.set(key, "1", nx=True, ex=ttl_seconds))
    now = time.monotonic()
    with _used_lock:
        for stale in [k for k, until in _used_local.items() if until <= now]:
            del _used_local[stale]
        if key in _used_local:
            return False
        _used_local[key] = now + ttl_seconds
        return True


# --- id_token --------------------------------------------------------------------------


def exchange_code(code: str, verifier: str) -> str:
    """POST the authorization code to Rooman One's token endpoint; returns the raw id_token."""
    response = httpx.post(
        discovery()["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.OIDC_REDIRECT_URI or "",
            "code_verifier": verifier,
            "client_id": settings.OIDC_CLIENT_ID or "",
            "client_secret": settings.OIDC_CLIENT_SECRET or "",
        },
        headers={"Accept": "application/json"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    id_token = response.json().get("id_token")
    if not id_token:
        raise RoomanOneError("Rooman One returned no id_token.")
    return id_token


def verify_id_token(id_token: str, nonce: str) -> Dict[str, Any]:
    """Verify signature (RS256, Rooman One's JWKS), audience, issuer, lifetime and nonce."""
    signing_key = _jwk_client(discovery()["jwks_uri"]).get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.OIDC_CLIENT_ID,
        issuer=settings.OIDC_ISSUER,
        leeway=60,
        options={"require": ["exp", "iat", "sub", "iss", "aud"]},
    )
    if not hmac.compare_digest(str(claims.get("nonce") or ""), nonce):
        raise RoomanOneError("The Rooman One sign-in does not match this browser (nonce).")
    for claim in ("org_id", "email"):
        if not claims.get(claim):
            raise RoomanOneError(f"The Rooman One sign-in carries no {claim}.")
    return claims


# --- set up the person, then sign in -------------------------------------------------


def map_role(role: Optional[str], *, creates_organization: bool) -> MemberRole:
    """Rooman One role -> Billing role. Unknown roles get the least privilege (viewer)."""
    r = (role or "").strip().lower()
    if r in ("admin", "owner"):
        return MemberRole.OWNER if creates_organization else MemberRole.ADMIN
    if r == "staff":
        return MemberRole.FINANCE
    return MemberRole.VIEWER


def _join(
    db: Session,
    organization: Organization,
    user: User,
    role: MemberRole,
    *,
    creates_organization: bool,
    now,
    ip: Optional[str],
    user_agent: Optional[str],
) -> Membership:
    if not creates_organization:
        org_access.ensure_seat_available(db, organization)
    membership = Membership(
        organization_id=organization.id,
        user_id=user.id,
        role=role,
        status=MembershipStatus.ACTIVE,
        accepted_at=now,
    )
    db.add(membership)
    db.flush()
    audit.record(
        db,
        action="MEMBER_JOINED",
        entity_type="membership",
        entity_id=membership.id,
        entity_label=user.email,
        ctx=auth_service.make_ctx(user, organization, membership, ip, user_agent),
        actor_label=user.email,
        after={"role": role.value, "via": VIA, "created_organization": creates_organization},
    )
    return membership


def provision(db: Session, claims: Dict[str, Any], ip: Optional[str], user_agent: Optional[str]) -> User:
    """Find the person by Rooman One's ids, setting up what Billing has not seen yet."""
    now = utcnow()
    user_id = str(claims["sub"])
    organization_id = str(claims["org_id"])
    user = db.get(User, user_id)

    if user is None:
        email = normalize_email(str(claims["email"]))
        if auth_service.get_user_by_email(db, email) is not None:
            # Billing emails are unique; never merge into (or take over) an existing account.
            raise ConflictError(EMAIL_TAKEN)
        user = User(
            id=user_id,
            email=email,
            full_name=(claims.get("name") or email)[:200],
            hashed_password=None,  # signs in with Rooman One; "Forgot password" can add one
            is_active=True,
            email_verified_at=now,
        )
        db.add(user)
        db.flush()

    if not user.is_active:
        raise UnauthorizedError(ACCOUNT_DISABLED)

    membership = db.scalars(
        select(Membership).where(Membership.user_id == user.id, Membership.organization_id == organization_id)
    ).first()
    if membership is None:
        organization = db.get(Organization, organization_id)
        creates = organization is None
        if creates:
            organization = auth_service.create_organization(
                db,
                (claims.get("org_name") or "My organization")[:200],
                user,
                now=now,
                organization_id=organization_id,
                ip=ip,
                user_agent=user_agent,
            )
        _join(
            db,
            organization,
            user,
            map_role(claims.get("role"), creates_organization=creates),
            creates_organization=creates,
            now=now,
            ip=ip,
            user_agent=user_agent,
        )
    # Committed before the sign-in checks, so an organization that cannot be used yet is still
    # there for the platform administrators.
    auth_service._commit(db, "This Rooman One account conflicts with an existing Billing account.")
    return user


def sign_in(
    db: Session, claims: Dict[str, Any], ip: Optional[str], user_agent: Optional[str]
) -> Union[TokenBundle, MfaChallenge]:
    """The same outcome as POST /auth/login, for a verified Rooman One id_token."""
    user = provision(db, claims, ip, user_agent)
    membership = auth_service.pick_membership(db, user.id, str(claims["org_id"]))
    if membership is None:
        auth_service._record_login_failure(db, user.email, user, "no_active_membership", ip, user_agent)
        db.commit()
        raise UnauthorizedError(auth_service.NOT_A_MEMBER)
    if user.totp_enabled_at is not None:
        db.commit()
        return MfaChallenge(mfa_token=create_mfa_token(user.id))
    return auth_service._complete_login(db, user, membership, ip, user_agent, via=VIA)


# --- hand-over to the browser -------------------------------------------------------


def make_handoff(result: Union[TokenBundle, MfaChallenge], next_path: str) -> str:
    """Encrypted, 60-second, single-use carrier of the sign-in result for the URL fragment."""
    payload = {
        "id": secrets.token_urlsafe(24),
        "exp": int(time.time()) + HANDOFF_TTL_SECONDS,
        "result": result.as_dict(),
        "next": safe_next(next_path),
    }
    return encrypt_str(json.dumps(payload, separators=(",", ":")))


def redeem_handoff(handoff: str) -> Tuple[Dict[str, Any], str]:
    """(sign-in result, next path) - once, within its lifetime."""
    try:
        payload = json.loads(decrypt_str(handoff))
    except (DecryptionError, ValueError, TypeError):
        raise UnauthorizedError(HANDOFF_INVALID)
    if not isinstance(payload, dict) or int(payload.get("exp", 0)) < int(time.time()):
        raise UnauthorizedError(HANDOFF_INVALID)
    if not use_once("handoff", str(payload.get("id")), HANDOFF_TTL_SECONDS * 2):
        logger.warning("Rooman One hand-over replayed (id hash only is stored)")
        raise UnauthorizedError(HANDOFF_INVALID)
    return payload["result"], safe_next(payload.get("next"))

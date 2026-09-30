"""Password hashing, JWT access tokens and opaque token helpers.

Access tokens are short-lived signed JWTs carrying the user id and the active
organization id. Refresh, invite and password-reset tokens are opaque random
strings; only their SHA-256 hash is persisted so a database leak cannot be
replayed.
"""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from backend.app.core.config import settings
from backend.app.core.encryption import DecryptionError, decrypt_str, encrypt_str

ACCESS_TOKEN_TYPE = "access"
MFA_TOKEN_TYPE = "mfa"
MFA_TOKEN_EXPIRE_MINUTES = 5

# Tenant access tokens are bound to this audience and issuer so a future platform token
# (different key, aud="platform") can never be replayed against tenant endpoints, nor a
# tenant token against platform ones.
TENANT_TOKEN_AUDIENCE = "tenant"
TOKEN_ISSUER = "rooman-billing"

# Transition for access tokens minted before tokens carried aud/iss (see
# decode_access_token): accepted only if issued before this process started, and only during
# the first ACCESS_TOKEN_EXPIRE_MINUTES of uptime - by then every such token has expired.
LEGACY_TOKENS_ISSUED_BEFORE = time.time()


# --- Passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    # bcrypt has a 72 byte input limit; pre-hashing keeps long passphrases safe.
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")
    return bcrypt.hashpw(digest, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed_password: Optional[str]) -> bool:
    if not hashed_password:
        return False
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")
    try:
        return bcrypt.checkpw(digest, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def validate_password_strength(password: str) -> Optional[str]:
    """Return a human readable problem, or None when the password is acceptable."""
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long."
    if password.lower() == password or password.upper() == password:
        return "Password must mix upper and lower case letters."
    if not any(ch.isdigit() for ch in password):
        return "Password must contain at least one digit."
    return None


# --- JWT access tokens -------------------------------------------------------------


def create_access_token(
    user_id: str,
    organization_id: Optional[str],
    role: Optional[str],
    session_id: Optional[str] = None,
) -> str:
    """`session_id` is the refresh-token row this access token was issued with; when present
    get_current_user rejects the access token once that session is revoked."""
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "org": organization_id,
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "aud": TENANT_TOKEN_AUDIENCE,
        "iss": TOKEN_ISSUER,
        "iat": now.timestamp(),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_mfa_token(user_id: str) -> str:
    """Short-lived token proving the password step of a two-factor login succeeded.

    It is useless on its own: get_current_user only accepts type=access tokens, and
    /auth/login/mfa still requires a valid TOTP code alongside it.
    """
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "type": MFA_TOKEN_TYPE,
        "iat": now.timestamp(),
        "exp": int((now + timedelta(minutes=MFA_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_mfa_token(token: str) -> Dict[str, Any]:
    """Decode and verify an MFA token. Raises jwt.PyJWTError on any problem."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != MFA_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Not an MFA token")
    return payload


def _decode_legacy_access_token(token: str) -> Dict[str, Any]:
    """Accept a pre-aud/iss tenant access token, only while one could still legitimately exist.

    Such a token has NEITHER `aud` NOR `iss` (never one without the other), was issued before
    this process started, lives no longer than the configured access-token lifetime, and is
    only accepted during that lifetime after start-up. This path exists only in the tenant
    decoder; a platform decoder will require aud="platform" and a different key.
    """
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp", "iat", "sub"]},
    )
    if "aud" in payload or "iss" in payload:
        raise jwt.InvalidTokenError("Access token has an incomplete audience/issuer")
    lifetime = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    issued_at = payload["iat"]
    if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)):
        raise jwt.InvalidIssuedAtError("Access token is invalid")
    if issued_at >= LEGACY_TOKENS_ISSUED_BEFORE:
        raise jwt.InvalidTokenError("Legacy access token issued after the transition started")
    if time.time() >= LEGACY_TOKENS_ISSUED_BEFORE + lifetime:
        raise jwt.InvalidTokenError("Legacy access token transition has ended")
    if payload["exp"] - issued_at > lifetime + 60:
        raise jwt.InvalidTokenError("Legacy access token outlives the configured lifetime")
    return payload


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and verify a tenant access token. Raises jwt.PyJWTError on any problem.

    Requires aud="tenant" (exactly, not merely listed) and iss="rooman-billing". The only
    exception is the short, bounded legacy transition in _decode_legacy_access_token, for
    tokens that carry neither claim.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=TENANT_TOKEN_AUDIENCE,
            issuer=TOKEN_ISSUER,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.MissingRequiredClaimError as exc:
        if exc.claim not in ("aud", "iss"):
            raise
        payload = _decode_legacy_access_token(token)
    else:
        if payload.get("aud") != TENANT_TOKEN_AUDIENCE:
            raise jwt.InvalidAudienceError("Access token audience must be exactly 'tenant'")
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Not an access token")
    return payload


# --- Opaque tokens (refresh / invite / reset) -----------------------------------------


def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def invite_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=settings.INVITE_TOKEN_EXPIRE_HOURS)


def password_reset_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)


# --- Symmetric encryption for small secrets at rest (e.g. TOTP seeds) -----------------
# Delegates to the keyring provider in core/encryption.py (ENCRYPTION_KEYS, with the legacy
# SECRET_KEY-derived key as a decrypt fallback), shared with integrations_service.


def encrypt_secret(value: str) -> str:
    return encrypt_str(value)


def decrypt_secret(token: Optional[str]) -> Optional[str]:
    """Return the plaintext, or None when missing or undecryptable (no configured key fits)."""
    if not token:
        return None
    try:
        return decrypt_str(token)
    except DecryptionError:
        return None

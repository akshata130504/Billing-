"""Platform access tokens (Rooman staff) - deliberately separate from tenant tokens.

Signed with PLATFORM_JWT_SECRET (never SECRET_KEY), aud="platform", iss="rooman-billing-platform",
typ="platform_access", always HS256. A tenant token fails here on the signature alone, and a
platform token fails in the tenant decoder (core/security.decode_access_token) the same way;
audience, issuer and type are checked as well so that no single forgotten check is enough.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt

from backend.app.core.config import settings

PLATFORM_TOKEN_AUDIENCE = "platform"
PLATFORM_TOKEN_ISSUER = "rooman-billing-platform"
PLATFORM_ACCESS_TOKEN_TYPE = "platform_access"
# Fixed, not configurable: the platform key must never be verified with a weaker algorithm.
PLATFORM_JWT_ALGORITHM = "HS256"
REQUIRED_CLAIMS = ["exp", "iat", "sub", "sid", "aud", "iss", "typ", "jti"]


class PlatformAuthNotConfigured(RuntimeError):
    """PLATFORM_JWT_SECRET is not set: platform sign-in is disabled."""


def _signing_key() -> str:
    key = (settings.PLATFORM_JWT_SECRET or "").strip()
    if not key:
        raise PlatformAuthNotConfigured("Platform authentication is not configured.")
    return key


def create_platform_access_token(*, staff_id: str, session_id: str, role: str, auth_time: datetime) -> str:
    """Short-lived access token for an authenticated (password + TOTP) platform session."""
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": staff_id,
        "sid": session_id,
        "role": role,  # informational only: authorisation always reloads the role from the database
        "aud": PLATFORM_TOKEN_AUDIENCE,
        "iss": PLATFORM_TOKEN_ISSUER,
        "typ": PLATFORM_ACCESS_TOKEN_TYPE,
        "amr": ["pwd", "otp"],
        "auth_time": int(auth_time.timestamp()),
        "iat": now.timestamp(),
        "exp": int((now + timedelta(minutes=settings.PLATFORM_ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, _signing_key(), algorithm=PLATFORM_JWT_ALGORITHM)


def decode_platform_access_token(token: str) -> Dict[str, Any]:
    """Verify a platform access token. Raises jwt.PyJWTError on any problem (or
    PlatformAuthNotConfigured when platform sign-in is disabled)."""
    payload = jwt.decode(
        token,
        _signing_key(),
        algorithms=[PLATFORM_JWT_ALGORITHM],
        audience=PLATFORM_TOKEN_AUDIENCE,
        issuer=PLATFORM_TOKEN_ISSUER,
        options={"require": REQUIRED_CLAIMS},
    )
    if payload.get("aud") != PLATFORM_TOKEN_AUDIENCE:  # a list merely containing it is not enough
        raise jwt.InvalidAudienceError("Platform token audience must be exactly 'platform'")
    if payload.get("typ") != PLATFORM_ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Not a platform access token")
    if "type" in payload or "org" in payload:
        raise jwt.InvalidTokenError("Tenant-shaped claims are not allowed in a platform token")
    if not isinstance(payload.get("sub"), str) or not isinstance(payload.get("sid"), str):
        raise jwt.InvalidTokenError("Platform token subject/session must be strings")
    return payload

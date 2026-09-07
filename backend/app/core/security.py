"""Password hashing, JWT access tokens and opaque token helpers.

Access tokens are short-lived signed JWTs carrying the user id and the active
organization id. Refresh, invite and password-reset tokens are opaque random
strings; only their SHA-256 hash is persisted so a database leak cannot be
replayed.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from backend.app.core.config import settings

ACCESS_TOKEN_TYPE = "access"


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


def create_access_token(user_id: str, organization_id: Optional[str], role: Optional[str]) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "org": organization_id,
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and verify an access token. Raises jwt.PyJWTError on any problem."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
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

"""RFC 6238 time-based one-time passwords (TOTP), stdlib only.

Compatible with Google Authenticator, 1Password, Authy, Microsoft Authenticator:
HMAC-SHA1, 6 digits, 30 second step, base32 secret without padding.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Optional
from urllib.parse import quote, urlencode

TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
# Accept the previous and next step too, to absorb clock drift between phone and server.
TOTP_WINDOW_STEPS = 1


def generate_totp_secret(nbytes: int = 20) -> str:
    """A random base32 secret (160 bits, the RFC 4226 recommended length), unpadded."""
    return base64.b32encode(secrets.token_bytes(nbytes)).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    cleaned = secret.strip().replace(" ", "").upper()
    cleaned += "=" * (-len(cleaned) % 8)
    return base64.b32decode(cleaned, casefold=True)


def hotp(secret: str, counter: int, digits: int = TOTP_DIGITS) -> str:
    """RFC 4226 HOTP value for `counter`."""
    digest = hmac.new(_decode_secret(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10**digits)).zfill(digits)


def current_step(at: Optional[float] = None) -> int:
    return int((time.time() if at is None else at) // TOTP_PERIOD_SECONDS)


def totp(secret: str, at: Optional[float] = None) -> str:
    return hotp(secret, current_step(at))


def verify_totp(secret: str, code: str, at: Optional[float] = None, window: int = TOTP_WINDOW_STEPS) -> Optional[int]:
    """Return the matching time step when `code` is valid within +/- `window` steps, else None."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != TOTP_DIGITS or not code.isdigit():
        return None
    step = current_step(at)
    matched: Optional[int] = None
    for candidate in range(step - window, step + window + 1):
        # Compare every candidate (no early exit) so timing does not reveal which step matched.
        if hmac.compare_digest(hotp(secret, candidate), code):
            matched = candidate
    return matched


def provisioning_uri(secret: str, account_name: str, issuer: str) -> str:
    """otpauth:// URI that authenticator apps import (usually rendered as a QR code)."""
    label = quote(f"{issuer}:{account_name}", safe="@:")
    params = urlencode(
        {"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": TOTP_DIGITS, "period": TOTP_PERIOD_SECONDS}
    )
    return f"otpauth://totp/{label}?{params}"

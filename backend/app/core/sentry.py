"""Optional Sentry error tracking.

Entirely driven by ``SENTRY_DSN``. When it is unset nothing here runs and
``sentry-sdk`` is never imported, so the package being absent cannot break boot
(same tolerance pattern as ``_load_scheduler`` in ``main.py``).

Everything that leaves this process passes through :func:`before_send`, which
strips credentials and Indian tax/PII identifiers out of the event. The SDK is
also configured with ``send_default_pii=False`` so request bodies, cookies and
user IP addresses are not attached in the first place.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger

REDACTED = "[redacted]"

#: Substrings that make a key sensitive. Matched case-insensitively against the
#: key, so "authorization", "X-Api-Key", "razorpay_key_secret" all match.
SENSITIVE_KEY_PARTS: tuple[str, ...] = (
    "authorization",
    "auth_token",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "x-api-key",
    "cookie",
    "session",
    "signature",
    "credential",
    "private_key",
    "otp",
    "pin",
    "gstin",
    "gst_number",
    "pan",
    "pan_number",
    "aadhaar",
    "aadhar",
    "card",
    "card_number",
    "cardnumber",
    "cvv",
    "cvc",
    "expiry",
    "account_number",
    "ifsc",
    "upi",
    "vpa",
)

#: Keys that contain "pan"/"card" as a substring but are harmless business fields.
SENSITIVE_KEY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "company",         # contains "pan"
        "company_name",
        "companyname",
        "plan",            # contains "pan"
        "plan_id",
        "plan_name",
        "plan_code",
        "expansion",
        "card_title",
        "discard",
    }
)

# 22AAAAA0000A1Z5 - 15 char GSTIN. Also catches the embedded PAN.
_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]Z?[A-Z\d]\b")
# ABCDE1234F - 10 char PAN.
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
# 13-19 digit card numbers, optionally grouped by spaces or dashes.
_CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
# Bearer / Basic credentials that show up inside free-text messages and URLs.
_BEARER_RE = re.compile(r"\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_QUERY_SECRET_RE = re.compile(
    r"((?:token|access_token|refresh_token|api_key|apikey|secret|password|signature)=)[^&\s\"']+",
    re.IGNORECASE,
)

_MAX_DEPTH = 12


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.strip().lower()
    if lowered in SENSITIVE_KEY_ALLOWLIST:
        return False
    normalised = lowered.replace("-", "_")
    if normalised in SENSITIVE_KEY_ALLOWLIST:
        return False
    return any(part.replace("-", "_") in normalised for part in SENSITIVE_KEY_PARTS)


def scrub_text(value: str) -> str:
    """Redact credentials and tax/card identifiers embedded in free text."""
    value = _BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", value)
    value = _QUERY_SECRET_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", value)
    value = _GSTIN_RE.sub(REDACTED, value)
    value = _PAN_RE.sub(REDACTED, value)
    value = _CARD_RE.sub(REDACTED, value)
    return value


def scrub(value: Any, _depth: int = 0) -> Any:
    """Recursively redact sensitive keys and patterns in an arbitrary structure."""
    if _depth > _MAX_DEPTH:
        return value
    if isinstance(value, dict):
        return {
            key: (REDACTED if _is_sensitive_key(key) else scrub(item, _depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        scrubbed: Iterable[Any] = [scrub(item, _depth + 1) for item in value]
        return type(value)(scrubbed) if isinstance(value, tuple) else list(scrubbed)
    if isinstance(value, str):
        return scrub_text(value)
    return value


def before_send(event: Optional[Dict[str, Any]], hint: Any = None) -> Optional[Dict[str, Any]]:
    """Sentry ``before_send`` hook: scrub the whole event before it is transmitted.

    Never raises - a bug in the scrubber must not turn one error into two, and
    dropping the event (returning ``None``) is safer than leaking PII.
    """
    if not event:
        return event
    try:
        scrubbed = scrub(event)
        # The user context is dropped down to a stable id; never the email/IP.
        user = scrubbed.get("user")
        if isinstance(user, dict):
            scrubbed["user"] = {"id": user.get("id")} if user.get("id") else {}
        return scrubbed
    except Exception:  # pragma: no cover - defensive
        logger.warning("Sentry before_send scrubber failed; dropping event")
        return None


def init_sentry() -> bool:
    """Initialise Sentry when a DSN is configured. Returns True when active.

    A missing ``sentry-sdk`` (or a failure inside it) is logged and ignored so the
    API still boots.
    """
    if not settings.SENTRY_DSN:
        return False
    try:
        import sentry_sdk  # noqa: WPS433 - lazy on purpose
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # noqa: WPS433
        from sentry_sdk.integrations.starlette import StarletteIntegration  # noqa: WPS433
    except ImportError as exc:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed (%s); error tracking disabled", exc)
        return False
    try:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            release=_release(),
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            send_default_pii=False,
            max_request_body_size="never",
            before_send=before_send,
            integrations=[StarletteIntegration(), FastApiIntegration()],
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Sentry initialisation failed (%s); error tracking disabled", exc)
        return False
    logger.info("Sentry error tracking enabled (environment=%s)", settings.ENVIRONMENT)
    return True


def _release() -> str:
    from backend.app import __version__

    return f"rooman-billing@{__version__}"


__all__ = ["before_send", "init_sentry", "scrub", "scrub_text", "REDACTED"]

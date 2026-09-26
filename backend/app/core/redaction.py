"""Secret redaction shared by the log filter (core/logging.py) and alerts (core/alerts.py).

Two layers:

* ``redact_text`` scrubs free text: ``key=value`` / ``"key": "value"`` pairs whose key looks
  sensitive, Authorization/Bearer/Basic credentials, credentials embedded in URLs, known
  API-key shapes (Razorpay, Google, GitHub, Slack, Sentry DSN, JWTs, Fernet tokens) and
  card-number-like digit runs (Luhn-checked).
* ``redact_data`` walks dicts/lists: values under a sensitive key are replaced outright,
  every other string goes through ``redact_text``.

Never raises: redaction must not turn a log line or an alert into an exception.
"""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[redacted]"

# Substrings that make a key sensitive (matched case-insensitively against the key with
# separators removed: "Razorpay-Key-Secret" -> "razorpaykeysecret").
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "apikey",
    "accesskey",
    "privatekey",
    "authorization",
    "cookie",
    "otp",
    "totp",
    "mfacode",
    "pin",
    "cvv",
    "cvc",
    "cardnumber",
    "pan",
    "signature",
    "credential",
    "sessionid",
    "dsn",
    "encryptionkey",
    "webhookurl",
)
# Keys that contain a sensitive fragment but are safe/necessary for triage.
_SAFE_KEYS = {
    "tokentype",
    "tokenexpiresin",
    "expiresin",
    "spanid",
    "company",
    "companyname",
    "pincode",
    "mfaenabled",
    "otpexpiresinseconds",
    "otpattempts",
    "maxattempts",
}

_KEY_NORMALIZE = re.compile(r"[^a-z0-9]")


def is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    norm = _KEY_NORMALIZE.sub("", key.lower())
    if not norm or norm in _SAFE_KEYS:
        return False
    if norm in {"pan", "pin", "otp"}:
        return True
    return any(part in norm for part in _SENSITIVE_KEY_PARTS if part not in {"pan", "pin"})


_KEY_ALTERNATION = (
    r"password|passwd|pwd|secret|client_secret|key_secret|webhook_secret|api[_-]?key|apikey|"
    r"access[_-]?key(?:[_-]?id)?|secret[_-]?access[_-]?key|private[_-]?key|token|access_token|"
    r"refresh_token|id_token|auth_token|mfa_token|otp|totp|code|pin|cvv|cvc|card_number|"
    r"authorization|cookie|set-cookie|x-api-key|signing_secret|signature|dsn|encryption_keys?"
)

_PATTERNS: list[tuple[re.Pattern[str], Any]] = [
    # Authorization: Bearer/Basic/Token <cred>  (header dumps, curl -v output)
    (re.compile(r"(?i)\b(authorization|proxy-authorization)(\s*[:=]\s*)(?:(bearer|basic|token|digest)\s+)?[^\s,;'\"]+"),
     lambda m: f"{m.group(1)}{m.group(2)}{(m.group(3) + ' ') if m.group(3) else ''}{REDACTED}"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9_\-\.=+/]{8,}"), lambda m: f"{m.group(1).capitalize()} {REDACTED}"),
    # key=value / key: value / "key": "value" (quoted or bare values)
    (re.compile(
        r"(?i)(?P<k>['\"]?\b(?:[a-z0-9_\-]*?(?:" + _KEY_ALTERNATION + r"))['\"]?)(?P<sep>\s*[:=]\s*)"
        r"(?P<v>\"[^\"]*\"|'[^']*'|[^\s,;&}\]]+)"
    ), None),
    # scheme://user:password@host  -> scheme://user:[redacted]@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+):[^\s@/]+@"), lambda m: f"{m.group(1)}:{REDACTED}@"),
    # Well-known credential shapes
    (re.compile(r"\brzp_(test|live)_[A-Za-z0-9]{8,}"), lambda m: f"rzp_{m.group(1)}_{REDACTED}"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), lambda m: f"AIza{REDACTED}"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), lambda m: f"gh_{REDACTED}"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), lambda m: f"github_pat_{REDACTED}"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), lambda m: f"xox-{REDACTED}"),
    (re.compile(r"\bsk_(live|test)_[A-Za-z0-9]{10,}"), lambda m: f"sk_{m.group(1)}_{REDACTED}"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), lambda m: f"AKIA{REDACTED}"),
    (re.compile(r"(?i)https://hooks\.slack\.com/services/[A-Za-z0-9/_\-]+"), lambda m: f"https://hooks.slack.com/services/{REDACTED}"),
    # JWTs (header.payload.signature) and Fernet tokens (gAAAAA...)
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), lambda m: f"[jwt {REDACTED}]"),
    (re.compile(r"\bgAAAAA[A-Za-z0-9_\-=]{20,}"), lambda m: f"[ciphertext {REDACTED}]"),
    # PEM private keys
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     lambda m: f"[private key {REDACTED}]"),
]

_CARD_CANDIDATE = re.compile(r"(?<![\d])(?:\d[ \-]?){12,18}\d(?![\d])")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = ord(ch) - 48
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _redact_card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if 13 <= len(digits) <= 19 and _luhn_ok(digits):
        return f"[card {REDACTED} ...{digits[-4:]}]"
    return match.group(0)


def _redact_pair(match: re.Match[str]) -> str:
    key = match.group("k")
    value = match.group("v")
    bare_key = key.strip("'\"")
    norm = _KEY_NORMALIZE.sub("", bare_key.lower())
    if norm == "code":
        # Only OTP/TOTP-shaped codes; keep "code=BAD_REQUEST_ERROR" style error codes readable.
        raw = value.strip("'\"")
        if not (raw.isdigit() and 4 <= len(raw) <= 8):
            return match.group(0)
    elif not is_sensitive_key(bare_key):
        return match.group(0)
    if value.startswith('"'):
        replacement = f'"{REDACTED}"'
    elif value.startswith("'"):
        replacement = f"'{REDACTED}'"
    else:
        replacement = REDACTED
    return f"{key}{match.group('sep')}{replacement}"


def redact_text(text: Any) -> Any:
    """Scrub secrets from free text. Non-strings are returned unchanged."""
    if not isinstance(text, str) or not text:
        return text
    try:
        out = text
        for pattern, repl in _PATTERNS:
            out = pattern.sub(repl if repl is not None else _redact_pair, out)
        out = _CARD_CANDIDATE.sub(_redact_card, out)
        return out
    except Exception:  # pragma: no cover - never let redaction break the caller
        return REDACTED


def _sensitive_item(key: Any, value: Any) -> bool:
    if value is None or value == "":
        return False
    if is_sensitive_key(key):
        return True
    # "code": OTP/TOTP-shaped values only (error codes stay readable).
    if isinstance(key, str) and _KEY_NORMALIZE.sub("", key.lower()) == "code":
        raw = str(value).strip()
        return raw.isdigit() and 4 <= len(raw) <= 8
    return False


def redact_data(value: Any, _depth: int = 0) -> Any:
    """Recursively redact a JSON-like structure (dict/list/tuple/str)."""
    if _depth > 20:
        return REDACTED
    try:
        if isinstance(value, dict):
            return {
                k: (REDACTED if _sensitive_item(k, v) else redact_data(v, _depth + 1))
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [redact_data(v, _depth + 1) for v in value]
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, (int, float, bool)) or value is None:
            # Bare numbers can still be card numbers.
            if isinstance(value, int) and not isinstance(value, bool) and len(str(abs(value))) >= 13:
                return redact_text(str(value))
            return value
        return redact_text(str(value))
    except Exception:  # pragma: no cover
        return REDACTED


def mask_email(email: Any) -> str:
    """'alice.smith@example.com' -> 'a***@example.com' (enough to triage, not to identify)."""
    if not isinstance(email, str) or "@" not in email:
        return "***"
    local, _, domain = email.strip().partition("@")
    return f"{local[:1]}***@{domain.lower()}"


__all__ = ["REDACTED", "is_sensitive_key", "mask_email", "redact_data", "redact_text"]

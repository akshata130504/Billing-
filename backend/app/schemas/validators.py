"""Shared validation utilities and Pydantic field validators for Rooman Billing."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from urllib.parse import urlsplit

# Regex patterns
_NAME_CHARS_RE = re.compile(r"^[A-Za-z0-9\s.,'&\-\(\)\/]{1,200}$")
_HAS_LETTER_RE = re.compile(r"[A-Za-z\u00C0-\u024F]")
_PHONE_RE = re.compile(r"^\+?[0-9\s\-().]{7,20}$")
_URL_RE = re.compile(r"^https?://([a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(:\d+)?([/?#].*)?$")
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_HSN_SAC_RE = re.compile(r"^[0-9]{2,8}$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
_SKU_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,64}$")


def validate_sensible_name(value: Optional[str], field_label: str = "Name") -> Optional[str]:
    """Validates that a name contains at least one letter and no invalid characters.
    
    Allows real-world names like 'Rooman Technologies 2.0', 'A&B Enterprises',
    'St. John's Hospital', 'Windows Server 2026', 'Plan 360'.
    Rejects purely numeric strings (e.g. '123456') and whitespace-only strings.
    """
    if value is None:
        return None
    val = value.strip()
    if not val:
        raise ValueError(f"{field_label} cannot be empty or whitespace-only.")
    if not _HAS_LETTER_RE.search(val):
        raise ValueError(f"{field_label} cannot be numeric-only and must contain at least one letter.")
    if not _NAME_CHARS_RE.match(val):
        raise ValueError(f"{field_label} contains invalid characters.")
    return val


def validate_phone_number(value: Optional[str]) -> Optional[str]:
    """Validates that a phone number has valid phone characters and sensible length."""
    if value is None:
        return None
    val = value.strip()
    if not val:
        return None
    if not _PHONE_RE.match(val):
        raise ValueError("Invalid phone number format. Only digits, spaces, hyphens, and optional leading + are allowed.")
    # Extract only digits to check count
    digits_only = re.sub(r"\D", "", val)
    if len(digits_only) < 7 or len(digits_only) > 15:
        raise ValueError("Phone number must contain between 7 and 15 digits.")
    return val


def validate_website_url(value: Optional[str]) -> Optional[str]:
    """Validates HTTP/HTTPS URL format."""
    if value is None:
        return None
    val = value.strip()
    if not val:
        return None
    if not (val.startswith("http://") or val.startswith("https://")):
        val = f"https://{val}"
    if not _URL_RE.match(val):
        raise ValueError("Invalid website URL. Must be a valid HTTP or HTTPS address.")
    return val


def validate_gstin_format(value: Optional[str]) -> Optional[str]:
    """Validates Indian 15-character GSTIN format."""
    if value is None:
        return None
    val = value.strip().upper()
    if not val:
        return None
    if not _GSTIN_RE.match(val):
        raise ValueError("Invalid GSTIN format. Expected format: 29ABCDE1234F1Z5 (15 characters).")
    return val


def validate_pan_format(value: Optional[str]) -> Optional[str]:
    """Validates Indian 10-character PAN format."""
    if value is None:
        return None
    val = value.strip().upper()
    if not val:
        return None
    if not _PAN_RE.match(val):
        raise ValueError("Invalid PAN format. Expected format: ABCDE1234F (10 characters).")
    return val


def validate_hsn_sac(value: Optional[str]) -> Optional[str]:
    """Validates HSN/SAC code digits."""
    if value is None:
        return None
    val = value.strip()
    if not val:
        return None
    if not _HSN_SAC_RE.match(val):
        raise ValueError("HSN/SAC code must contain only 2 to 8 numeric digits.")
    return val


def validate_slug_format(value: Optional[str], field_label: str = "Code") -> Optional[str]:
    """Validates lowercase identifier slug."""
    if value is None:
        return None
    val = value.strip().lower()
    if not val:
        raise ValueError(f"{field_label} cannot be empty.")
    if not _SLUG_RE.match(val):
        raise ValueError(f"{field_label} must contain only lowercase letters, numbers, hyphens, or underscores.")
    return val


def reject_future_datetime(value: Optional[datetime], field_label: str = "Date") -> Optional[datetime]:
    """Rejects a datetime later than today."""
    if value is None:
        return None
    now = datetime.now(value.tzinfo) if value.tzinfo else max(datetime.now(), datetime.now(timezone.utc).replace(tzinfo=None))
    if value.date() > now.date():
        raise ValueError(f"{field_label} cannot be in the future.")
    return value


def validate_sku_format(value: Optional[str]) -> Optional[str]:
    """Validates product SKU identifier."""
    if value is None:
        return None
    val = value.strip()
    if not val:
        return None
    if not _SKU_RE.match(val):
        raise ValueError("SKU must contain only alphanumeric characters, dashes, dots, or underscores.")
    return val


_UNSAFE_URL_CHARS_RE = re.compile(r"[\s\"'<>\\`]")
_SAME_ORIGIN_IMAGE_RE = re.compile(r"^/(uploads|logos)/[A-Za-z0-9._/-]+$")


def validate_redirect_url(value: Optional[str], field_label: str = "Redirect URL") -> Optional[str]:
    """Absolute http(s) URL with a host; javascript:/data:/vbscript:, protocol-relative and
    relative URLs are rejected. Which external hosts are allowed is a product decision:
    any public host is accepted here."""
    if value is None:
        return None
    val = value.strip()
    if not val:
        return None
    try:
        parts = urlsplit(val)
    except ValueError:
        raise ValueError(f"{field_label} must be a valid http(s) URL.")
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or _UNSAFE_URL_CHARS_RE.search(val):
        raise ValueError(f"{field_label} must be an absolute http(s) URL with a host (e.g. https://example.com/thanks).")
    if parts.username or parts.password:
        raise ValueError(f"{field_label} must not contain credentials.")
    return val


def validate_image_url(value: Optional[str], field_label: str = "Logo URL") -> Optional[str]:
    """An http(s) image URL with a host, or a same-origin /uploads/... (or /logos/...) path."""
    if value is None:
        return None
    val = value.strip()
    if not val:
        return None
    if val.startswith("/") and not val.startswith("//"):
        if not _SAME_ORIGIN_IMAGE_RE.match(val) or ".." in val:
            raise ValueError(f"{field_label} must be an http(s) URL or an /uploads/ path.")
        return val
    return validate_redirect_url(val, field_label)


# Custom CSS for document templates (BUG-48). The CSS is placed inside a <style>
# element and loaded by the viewer's browser, so it must neither break out of that
# element nor make the browser (or any future HTML->PDF renderer) fetch internal or
# arbitrary URLs.
MAX_CUSTOM_CSS_LENGTH = 20_000
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
_CSS_FORBIDDEN = (
    ("<", "HTML markup (such as </style> or <script>) is not allowed"),
    ("\\", "CSS escape sequences are not allowed"),
    ("@import", "@import is not allowed"),
    ("@namespace", "@namespace is not allowed"),
    ("image-set(", "image-set() is not allowed"),
    ("expression(", "expression() is not allowed"),
    ("javascript:", "javascript: URLs are not allowed"),
    ("vbscript:", "vbscript: URLs are not allowed"),
    ("behavior:", "behavior is not allowed"),
    ("-moz-binding", "-moz-binding is not allowed"),
)


def custom_css_problem(css: Optional[str]) -> Optional[str]:
    """Why `css` is unsafe as document-template CSS, or None when it is acceptable.

    Every ``url(...)`` must be a same-origin ``/uploads/`` path, an inline raster
    ``data:image/...`` URI, or an https URL whose host is public (the webhook SSRF
    validator: no private, loopback, link-local or metadata addresses).
    """
    if not css:
        return None
    if len(css) > MAX_CUSTOM_CSS_LENGTH:
        return f"Custom CSS must be at most {MAX_CUSTOM_CSS_LENGTH} characters."
    lowered = css.lower()
    for token, message in _CSS_FORBIDDEN:
        if token in lowered:
            return f"Custom CSS rejected: {message}."
    # Comments could hide or split the tokens checked below.
    stripped = _CSS_COMMENT_RE.sub("", lowered)
    if "/*" in stripped:
        return "Custom CSS rejected: unterminated comment."
    if stripped.count("url(") != len(_CSS_URL_RE.findall(stripped)):
        return "Custom CSS rejected: malformed url()."
    from backend.app.core import network_security

    for _quote, target in _CSS_URL_RE.findall(css):
        target = target.strip()
        low = target.lower()
        if low.startswith("/uploads/") and ".." not in target:
            continue
        if re.match(r"^data:image/(png|jpe?g|gif|webp);base64,[a-z0-9+/=]+$", low):
            continue
        if low.startswith("https://") and network_security.is_safe_url(target):
            continue
        return (
            "Custom CSS rejected: url() must point to an https address on a public host, "
            "an /uploads/ path or an inline image."
        )
    return None


def validate_custom_css(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not value.strip():
        return None
    problem = custom_css_problem(value)
    if problem:
        raise ValueError(problem)
    return value

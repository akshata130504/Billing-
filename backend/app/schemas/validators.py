"""Shared validation utilities and Pydantic field validators for Rooman Billing."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

# Regex patterns
_NAME_CHARS_RE = re.compile(r"^[A-Za-z0-9\s.,'&\-\(\)\/]{1,200}$")
_HAS_LETTER_RE = re.compile(r"[A-Za-z\u00C0-\u024F]")
_PHONE_RE = re.compile(r"^\+?[0-9\s\-().]{7,20}$")
_URL_RE = re.compile(r"^https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=]+$")
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


_MAX_FUTURE_SKEW = timedelta(days=1)


def reject_future_datetime(value: Optional[datetime], field_label: str = "Date") -> Optional[datetime]:
    """Rejects a datetime more than a day ahead of "now" (a day of slack absorbs client/server timezone skew)."""
    if value is None:
        return None
    now = datetime.now(value.tzinfo) if value.tzinfo else datetime.now(timezone.utc).replace(tzinfo=None)
    if value - now > _MAX_FUTURE_SKEW:
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

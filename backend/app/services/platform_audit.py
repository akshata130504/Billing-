"""Platform security audit trail (platform_audit_logs).

Append-only: this module only inserts. Every platform authentication/security event is recorded
here with the staff member (when known), the outcome, the session, IP and user agent. Passwords,
TOTP codes and secrets, challenge / refresh / access token values are never recorded: `details`
passes through `_scrub`, which drops any key that looks like a credential.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.models.platform import PlatformAuditLog, PlatformStaff

# Event names (see docs/platform-administration-design.md, section 10).
LOGIN_PASSWORD_VERIFIED = "PLATFORM_LOGIN_PASSWORD_VERIFIED"  # step 1 ok, 2FA challenge issued
LOGIN_FAILED = "PLATFORM_LOGIN_FAILED"
TWO_FACTOR_SUCCEEDED = "PLATFORM_2FA_SUCCEEDED"
TWO_FACTOR_FAILED = "PLATFORM_2FA_FAILED"
LOGIN_SUCCEEDED = "PLATFORM_LOGIN_SUCCEEDED"  # session established
ACCOUNT_LOCKED = "PLATFORM_ACCOUNT_LOCKED"  # throttle tripped
REFRESH_REUSE_DETECTED = "PLATFORM_REFRESH_REUSE_DETECTED"
LOGOUT = "PLATFORM_LOGOUT"
SESSION_REVOKED = "PLATFORM_SESSION_REVOKED"
ALL_SESSIONS_REVOKED = "PLATFORM_ALL_SESSIONS_REVOKED"
STAFF_CREATED = "PLATFORM_STAFF_CREATED"
STAFF_DEACTIVATED = "PLATFORM_STAFF_DEACTIVATED"
STAFF_ACTIVATED = "PLATFORM_STAFF_ACTIVATED"
TWO_FACTOR_RESET = "PLATFORM_2FA_RESET"
PASSWORD_RESET = "PLATFORM_PASSWORD_RESET"
STEP_UP_SUCCEEDED = "PLATFORM_STEP_UP_SUCCEEDED"  # fresh TOTP accepted for this session
STEP_UP_FAILED = "PLATFORM_STEP_UP_FAILED"
STEP_UP_REQUIRED = "PLATFORM_STEP_UP_REQUIRED"  # a sensitive action was refused: no recent step-up

SUCCESS = "success"
FAILURE = "failure"
DENIED = "denied"

_CREDENTIAL_HINTS = ("password", "passwd", "secret", "token", "code", "otp", "totp", "hash", "cookie", "authorization")


def _scrub(details: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not details:
        return None
    clean: Dict[str, Any] = {}
    for key, value in details.items():
        if any(hint in str(key).lower() for hint in _CREDENTIAL_HINTS):
            continue
        if isinstance(value, str):
            value = value[:500]
        clean[str(key)[:64]] = value
    return clean or None


def record(
    db: Session,
    *,
    action: str,
    result: str,
    staff: Optional[PlatformStaff] = None,
    email: Optional[str] = None,
    session_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> PlatformAuditLog:
    """Add a platform audit row to the current transaction (the caller commits)."""
    entry = PlatformAuditLog(
        platform_staff_id=staff.id if staff is not None else None,
        staff_email_snapshot=((staff.email if staff is not None else email) or None),
        action=action,
        result=result,
        session_id=session_id,
        ip_address=(ip_address or None) and ip_address[:64],
        user_agent=(user_agent or None) and user_agent[:400],
        details=_scrub(details),
    )
    if entry.staff_email_snapshot:
        entry.staff_email_snapshot = entry.staff_email_snapshot[:255]
    db.add(entry)
    return entry

"""FastAPI dependencies for platform (Rooman staff) requests - separate from api/deps.py.

A platform request is authenticated ONLY by a platform access token (core/platform_security): from
the `Authorization: Bearer` header or the HttpOnly platform access cookie. Tenant tokens fail on
the signature, and tenant dependencies (get_current_context) never accept platform tokens, so the
two principals cannot be exchanged. Cookie-authenticated requests that change state must carry
the double-submit CSRF header.

Role checks are explicit sets - there is no "superuser" / wildcard dependency, and nothing here
grants access to any tenant's data.
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Callable, FrozenSet, Optional

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from backend.app.api.deps import client_ip, get_db
from backend.app.core.config import settings
from backend.app.core.exceptions import ForbiddenError, UnauthorizedError
from backend.app.models.platform import PlatformRole, PlatformSession, PlatformStaff
from backend.app.services import platform_auth_service

# Cookies: the access cookie is only sent to platform API paths and the refresh cookie only to the
# platform auth paths; neither is readable by page JavaScript. The CSRF cookie is readable on
# purpose (double submit) and grants nothing on its own.
ACCESS_COOKIE = "rb_platform_access"
REFRESH_COOKIE = "rb_platform_refresh"
CSRF_COOKIE = "rb_platform_csrf"
CSRF_HEADER = "X-Platform-CSRF"
ACCESS_COOKIE_PATH = f"{settings.API_V1_STR.rstrip('/')}/platform"
REFRESH_COOKIE_PATH = f"{settings.API_V1_STR.rstrip('/')}/platform/auth"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class PlatformContext:
    staff: PlatformStaff
    session: PlatformSession
    ip_address: Optional[str]
    user_agent: Optional[str]

    @property
    def role(self) -> PlatformRole:
        return self.staff.role


def user_agent(request: Request) -> Optional[str]:
    return (request.headers.get("user-agent") or "")[:400] or None


def check_csrf(request: Request) -> None:
    """Double-submit check: the header must equal the CSRF cookie (constant-time)."""
    cookie = request.cookies.get(CSRF_COOKIE) or ""
    header = request.headers.get(CSRF_HEADER) or ""
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise ForbiddenError("Missing or invalid CSRF token.")


def _bearer(request: Request) -> Optional[str]:
    header = request.headers.get("authorization") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return None


def get_platform_context(request: Request, db: Session = Depends(get_db)) -> PlatformContext:
    platform_auth_service.ensure_enabled()
    token = _bearer(request)
    from_cookie = False
    if token is None:
        token = request.cookies.get(ACCESS_COOKIE)
        from_cookie = token is not None
    if not token:
        raise UnauthorizedError("Platform authentication required.")
    if from_cookie and request.method.upper() not in SAFE_METHODS:
        check_csrf(request)
    staff, session = platform_auth_service.authenticate(db, token)
    return PlatformContext(staff=staff, session=session, ip_address=client_ip(request), user_agent=user_agent(request))


def require_platform_roles(allowed: FrozenSet[PlatformRole]) -> Callable[..., PlatformContext]:
    def dependency(ctx: PlatformContext = Depends(get_platform_context)) -> PlatformContext:
        if ctx.role not in allowed:
            raise ForbiddenError("Your platform role does not allow this action.")
        return ctx

    return dependency


ALL_PLATFORM_ROLES = frozenset(PlatformRole)
# Any signed-in platform staff member (e.g. their own profile and sessions).
require_platform_staff = require_platform_roles(ALL_PLATFORM_ROLES)
# Platform Administrator ("Super Admin") only.
require_platform_administrator = require_platform_roles(frozenset({PlatformRole.PLATFORM_ADMINISTRATOR}))
# Operations capabilities: Operations staff, and Platform Administrators.
require_platform_operations = require_platform_roles(
    frozenset({PlatformRole.PLATFORM_ADMINISTRATOR, PlatformRole.PLATFORM_OPERATIONS})
)
# Support capabilities: Support staff, and Platform Administrators.
require_platform_support = require_platform_roles(
    frozenset({PlatformRole.PLATFORM_ADMINISTRATOR, PlatformRole.PLATFORM_SUPPORT})
)


# --- cookies ------------------------------------------------------------------------------------------


def set_session_cookies(response: Response, access_token: str, refresh_secret: str, csrf_token: str) -> None:
    secure = settings.platform_cookie_secure
    access_age = settings.PLATFORM_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    session_age = settings.PLATFORM_SESSION_MAX_HOURS * 3600
    response.set_cookie(
        ACCESS_COOKIE, access_token, max_age=access_age, path=ACCESS_COOKIE_PATH,
        httponly=True, secure=secure, samesite="strict",
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh_secret, max_age=session_age, path=REFRESH_COOKIE_PATH,
        httponly=True, secure=secure, samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf_token, max_age=session_age, path="/",
        httponly=False, secure=secure, samesite="strict",
    )


def clear_session_cookies(response: Response) -> None:
    secure = settings.platform_cookie_secure
    for name, path in ((ACCESS_COOKIE, ACCESS_COOKIE_PATH), (REFRESH_COOKIE, REFRESH_COOKIE_PATH), (CSRF_COOKIE, "/")):
        response.delete_cookie(name, path=path, secure=secure, httponly=name != CSRF_COOKIE, samesite="strict")

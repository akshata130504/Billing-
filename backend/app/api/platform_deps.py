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
from backend.app.services import platform_audit, platform_auth_service

# Cookies are host-only (never a Domain attribute) on the platform console origin, HttpOnly except
# the double-submit CSRF cookie (readable on purpose, grants nothing on its own), SameSite=Strict.
# With secure cookies (production) the names carry the browser-enforced prefixes: "__Host-" (Secure,
# Path=/, no Domain - a sibling subdomain such as the tenant app cannot set or overwrite it) for the
# access and CSRF cookies, "__Secure-" for the refresh cookie, which stays on the platform auth path.
# Without secure cookies (local http development/tests) the plain names and narrow paths are used.
ACCESS_COOKIE = "rb_platform_access"
REFRESH_COOKIE = "rb_platform_refresh"
CSRF_COOKIE = "rb_platform_csrf"
CSRF_HEADER = "X-Platform-CSRF"
ACCESS_COOKIE_PATH = f"{settings.API_V1_STR.rstrip('/')}/platform"
REFRESH_COOKIE_PATH = f"{settings.API_V1_STR.rstrip('/')}/platform/auth"


@dataclass(frozen=True)
class CookieSpec:
    name: str
    path: str
    httponly: bool


def cookie_specs() -> tuple[CookieSpec, CookieSpec, CookieSpec]:
    """(access, refresh, csrf) cookie name/path for the current cookie security mode."""
    if settings.platform_cookie_secure:
        return (
            CookieSpec(f"__Host-{ACCESS_COOKIE}", "/", True),
            CookieSpec(f"__Secure-{REFRESH_COOKIE}", REFRESH_COOKIE_PATH, True),
            CookieSpec(f"__Host-{CSRF_COOKIE}", "/", False),
        )
    return (
        CookieSpec(ACCESS_COOKIE, ACCESS_COOKIE_PATH, True),
        CookieSpec(REFRESH_COOKIE, REFRESH_COOKIE_PATH, True),
        CookieSpec(CSRF_COOKIE, "/", False),
    )


def read_refresh_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(cookie_specs()[1].name)


def read_csrf_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(cookie_specs()[2].name)


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
    cookie = read_csrf_cookie(request) or ""
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
        token = request.cookies.get(cookie_specs()[0].name)
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


def require_recent_platform_step_up(
    request: Request, ctx: PlatformContext = Depends(get_platform_context), db: Session = Depends(get_db)
) -> PlatformContext:
    """For sensitive platform actions: the CURRENT session must have completed POST
    /platform/auth/step-up (a fresh TOTP) within PLATFORM_STEP_UP_MINUTES. Otherwise 403
    STEP_UP_REQUIRED (the client asks for a code, then retries). Combine with a role dependency
    for authorization; this only proves recent presence of the second factor."""
    if not platform_auth_service.has_recent_step_up(ctx.staff, ctx.session):
        platform_audit.record(
            db, action=platform_audit.STEP_UP_REQUIRED, result=platform_audit.DENIED, staff=ctx.staff,
            session_id=ctx.session.id, ip_address=ctx.ip_address, user_agent=ctx.user_agent,
            details={"method": request.method, "path": request.url.path[:200]},
        )
        db.commit()
        raise platform_auth_service.StepUpRequiredError()
    return ctx


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
    access, refresh, csrf = cookie_specs()
    access_age = settings.PLATFORM_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    session_age = settings.PLATFORM_SESSION_MAX_HOURS * 3600
    for spec, value, age in ((access, access_token, access_age), (refresh, refresh_secret, session_age),
                             (csrf, csrf_token, session_age)):
        response.set_cookie(spec.name, value, max_age=age, path=spec.path, httponly=spec.httponly,
                            secure=secure, samesite="strict")


def clear_session_cookies(response: Response) -> None:
    secure = settings.platform_cookie_secure
    for spec in cookie_specs():
        response.delete_cookie(spec.name, path=spec.path, secure=secure, httponly=spec.httponly, samesite="strict")

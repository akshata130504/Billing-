"""The browser-origin boundary for the platform (Rooman staff) API.

The platform console is served at /superadmin on the ONE official application origin (the origin
of FRONTEND_URL, settings.platform_origin) - the same origin as the tenant app at /admin. Sharing
the origin does not share authorization: platform requests authenticate only with the platform
session cookies (separate signing key, audience and token type, mandatory TOTP), tenant bearer
tokens are never accepted there, and platform cookies are never accepted by tenant routes.

On platform API paths (/api/v1/platform/...) this module enforces, for every request:

- A present Origin header must be exactly the application origin (any other origin, a sibling
  host, another port or scheme, or "null" is refused), and a browser's Sec-Fetch-Site must be
  "same-origin" (or "none", a user-typed navigation) - so a page on any other site, including a
  sibling subdomain, cannot make a credentialed platform request, not even a "no-cors" simple POST
  that skips CORS preflight. Together with the platform CSRF double-submit check this is the
  cross-site request defence.
- CORS is split by path: tenant paths keep the existing ALLOWED_ORIGINS policy unchanged, platform
  paths only ever allow the application origin (credentials included), never a wildcard or
  reflection.
- Websockets are refused, and platform responses carry a stricter header set than tenant ones.

When platform sign-in is not configured (no PLATFORM_JWT_SECRET) nothing here changes any request.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.core.config import normalize_origin, settings

PLATFORM_PREFIX = f"{settings.API_V1_STR.rstrip('/')}/platform"
# Stricter than the tenant set: platform API responses never render, frame or load anything.
PLATFORM_SECURITY_HEADERS: Dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
PLATFORM_CORS_HEADERS: List[str] = ["Content-Type", "Accept", "X-Platform-CSRF", "X-Request-ID"]
PLATFORM_CORS_METHODS: List[str] = ["GET", "POST", "DELETE", "OPTIONS"]


def is_platform_path(path: str) -> bool:
    return path == PLATFORM_PREFIX or path.startswith(PLATFORM_PREFIX + "/")


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key == name:
            return value.decode("latin-1")
    return None


async def _reject(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message, "details": {}}}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
               (b"cache-control", b"no-store")]
    headers += [(k.lower().encode(), v.encode()) for k, v in PLATFORM_SECURITY_HEADERS.items()]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class PlatformBoundaryMiddleware:
    """Origin / Sec-Fetch-Site checks on the platform API paths (see module doc)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] not in ("http", "websocket")
            or not settings.platform_auth_enabled
            or not is_platform_path(scope.get("path") or "")
        ):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            # The platform console uses no websockets.
            await send({"type": "websocket.close", "code": 1008})
            return
        origin = _header(scope, b"origin")
        if origin is not None and normalize_origin(origin) != settings.platform_origin:
            await _reject(send, 403, "FORBIDDEN", "Cross-origin platform requests are not allowed.")
            return
        fetch_site = (_header(scope, b"sec-fetch-site") or "").strip().lower()
        if fetch_site and fetch_site not in ("same-origin", "none"):
            await _reject(send, 403, "FORBIDDEN", "Cross-site platform requests are not allowed.")
            return
        await self.app(scope, receive, send)


class PathSplitCORSMiddleware:
    """Tenant paths use the tenant CORS policy exactly as before; platform paths use a separate
    policy that only ever allows the application origin."""

    def __init__(self, app: ASGIApp, *, tenant_options: Dict[str, Any]) -> None:
        self.tenant = CORSMiddleware(app, **tenant_options)
        platform_origin = settings.platform_origin
        self.platform = CORSMiddleware(
            app,
            allow_origins=[platform_origin] if platform_origin else [],
            allow_credentials=True,
            allow_methods=PLATFORM_CORS_METHODS,
            allow_headers=PLATFORM_CORS_HEADERS,
            max_age=600,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and is_platform_path(scope.get("path") or ""):
            await self.platform(scope, receive, send)
        else:
            await self.tenant(scope, receive, send)


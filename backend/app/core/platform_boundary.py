"""The browser-origin boundary between the tenant app and the platform (Rooman staff) console.

The platform console is served from its own origin (settings.PLATFORM_APP_ORIGIN, e.g.
https://platform.example.com) with a hostname different from the tenant app. Cookies are not
isolated by port, and sibling subdomains are "same-site", so SameSite alone cannot separate the two:
this module enforces the boundary on the server for every request.

- Platform API paths (/api/v1/platform/...) answer only when the request's Host is the platform
  host; on any other host they are a 404. The platform host answers ONLY platform paths.
- On platform paths, a present Origin header must be exactly the platform origin (a tenant origin,
  any other origin, or "null" is refused), and a browser's Sec-Fetch-Site must be "same-origin"
  (or "none", a user-typed navigation) - so a page on the tenant origin, even with XSS, cannot make
  a credentialed platform request, including simple "no-cors" POSTs that skip CORS preflight.
- CORS is split by path: tenant paths keep the existing ALLOWED_ORIGINS policy unchanged, platform
  paths only ever allow the platform origin (credentials included), never a wildcard or reflection.
- Platform responses carry a stricter header set than tenant ones.

When the platform is not configured (no PLATFORM_APP_ORIGIN) nothing here changes any request.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.core.config import normalize_origin, settings

PLATFORM_PREFIX = f"{settings.API_V1_STR.rstrip('/')}/platform"
# Public website media (uploaded through the CMS). Readable - GET/HEAD only - on the platform host
# too, so the console's landing-page preview can show uploaded images and videos. These files are
# public on the tenant host anyway; nothing else under /uploads is exposed on the platform host.
WEBSITE_MEDIA_PREFIX = "/uploads/website/"

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
    """Host binding plus Origin / Sec-Fetch-Site checks for the platform console (see module doc)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not settings.platform_origin:
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        host = (_header(scope, b"host") or "").strip().lower()
        on_platform_host = host == settings.platform_netloc
        platform_path = is_platform_path(path)

        if scope["type"] == "websocket":
            # The platform console uses no websockets; refuse any on its host or paths.
            if on_platform_host or platform_path:
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
            return

        if (
            on_platform_host
            and path.startswith(WEBSITE_MEDIA_PREFIX)
            and ".." not in path
            and scope.get("method") in ("GET", "HEAD")
        ):
            await self.app(scope, receive, send)
            return
        if platform_path != on_platform_host:
            # Platform API on the tenant host, or anything but the platform API on the platform host.
            await _reject(send, 404, "NOT_FOUND", "Not found.")
            return
        if platform_path:
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
    policy that only ever allows the configured platform origin."""

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


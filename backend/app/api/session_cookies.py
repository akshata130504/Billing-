"""Browser sessions for the tenant app: the refresh token lives in an HttpOnly cookie.

Security fix: the SPA used to keep both tokens in localStorage, where any
injected script could read the long-lived refresh token. Now:

* The SPA sends ``X-Rooman-Session: cookie`` on every API call ("cookie mode").
* Every endpoint that issues tokens (login, 2FA login, refresh, signup, invitation, organization
  switch) then puts the refresh token into an HttpOnly, SameSite=Strict cookie
  scoped to the auth API path (Secure, with the ``__Secure-`` prefix, whenever the app is served
  over HTTPS) and leaves it OUT of the JSON body. The access token stays in the response body and
  the SPA keeps it in memory only; after a reload it gets a new one from /auth/refresh.
* /auth/refresh, /auth/logout and /auth/change-password read the refresh token from that cookie
  when the body carries none. The cookie is only honoured together with the custom header, which a
  cross-site form or <img> cannot send (and a cross-site fetch with it needs a CORS preflight that
  only ALLOWED_ORIGINS pass), so the cookie adds no CSRF surface.

API and native clients that do not send the header keep the documented body-token contract.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request, Response

from backend.app.core.config import settings

SESSION_MODE_HEADER = "X-Rooman-Session"
COOKIE_MODE = "cookie"
_BASE_NAME = "rb_session"


def cookie_secure() -> bool:
    return bool(settings.SECURE_COOKIES or settings.is_production or
                (settings.FRONTEND_URL or "").strip().lower().startswith("https://"))


def cookie_name() -> str:
    # "__Secure-" makes the browser refuse the cookie unless it is Secure and set over HTTPS.
    return f"__Secure-{_BASE_NAME}" if cookie_secure() else _BASE_NAME


def cookie_path() -> str:
    return f"{settings.API_V1_STR.rstrip('/')}/auth"


def cookie_mode(request: Request) -> bool:
    return (request.headers.get(SESSION_MODE_HEADER) or "").strip().lower() == COOKIE_MODE


def read_refresh_token(request: Request, body_token: Optional[str] = None) -> Optional[str]:
    """The refresh token of this request: the body's (API clients), else the session cookie (SPA,
    cookie mode only)."""
    if body_token:
        return body_token
    if cookie_mode(request):
        return request.cookies.get(cookie_name()) or None
    return None


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        cookie_name(),
        refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=cookie_path(),
        httponly=True,
        secure=cookie_secure(),
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(cookie_name(), path=cookie_path(), secure=cookie_secure(), httponly=True,
                           samesite="strict")


def deliver(request: Request, response: Response, tokens: Dict[str, Any]) -> Dict[str, Any]:
    """Token response body for this request. Cookie mode: refresh token -> HttpOnly cookie and
    removed from the body; otherwise the body is returned unchanged."""
    if not cookie_mode(request) or not tokens.get("refresh_token"):
        return tokens
    set_refresh_cookie(response, tokens["refresh_token"])
    return {**tokens, "refresh_token": None}

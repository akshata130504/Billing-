"""Per-client-IP rate limiting for credential endpoints (slowapi).

The limiter is registered on ``app.state.limiter`` in ``main.py``. Endpoints opt
in with ``@limiter.limit(auth_rate_limit)``; the limit string is read from
settings on every request so it can be tuned (or relaxed in tests) at runtime.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from backend.app.api.deps import client_ip
from backend.app.core.config import settings


def rate_limit_key(request: Request) -> str:
    """Rate limit by the real client address (X-Real-IP from our proxy; see deps.client_ip)."""
    return client_ip(request) or "unknown"


def auth_rate_limit() -> str:
    """Limit string for signup/login/forgot/reset/accept-invitation, e.g. "10/minute"."""
    return settings.AUTH_RATE_LIMIT


def public_rate_limit() -> str:
    """Limit for unauthenticated hosted-page reads (/public/invoices, /public/quotes, /checkout/public).

    These are guarded only by an opaque token in the URL, so they are enumerable;
    the limit caps how fast a scanner can walk the token space from one IP.
    """
    return settings.PUBLIC_RATE_LIMIT


def public_action_rate_limit() -> str:
    """Tighter limit for unauthenticated state-changing hosted-page calls.

    Covers quote accept/decline, Razorpay order creation and signature
    verification, and hosted checkout confirmation.
    """
    return settings.PUBLIC_ACTION_RATE_LIMIT


def _get_storage_uri() -> str:
    """Returns Redis storage URI if configured, otherwise falls back to in-memory storage."""
    return settings.REDIS_URL or "memory://"


limiter = Limiter(
    key_func=rate_limit_key,
    # One bucket per (client IP, endpoint). slowapi's default key_style="url" scopes the
    # bucket to the full path, so /public/invoices/<token> gave every token its own bucket
    # and a scanner walking the token space was never limited.
    key_style="endpoint",
    storage_uri=_get_storage_uri(),
    in_memory_fallback_enabled=True,
    headers_enabled=False,
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return the standard error envelope instead of slowapi's plain-text body."""
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many requests. Please wait a moment and try again.",
                "details": {"limit": exc.detail},
            }
        },
        headers={"Retry-After": "60"},
    )


__all__ = [
    "limiter",
    "auth_rate_limit",
    "public_rate_limit",
    "public_action_rate_limit",
    "rate_limit_key",
    "rate_limit_exceeded_handler",
    "RateLimitExceeded",
]

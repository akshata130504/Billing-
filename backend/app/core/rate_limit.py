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
    """Rate limit by the real client address (honours X-Forwarded-For)."""
    return client_ip(request) or "unknown"


def auth_rate_limit() -> str:
    """Limit string for signup/login/forgot/reset/accept-invitation, e.g. "10/minute"."""
    return settings.AUTH_RATE_LIMIT


limiter = Limiter(key_func=rate_limit_key, headers_enabled=False)


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


__all__ = ["limiter", "auth_rate_limit", "rate_limit_key", "rate_limit_exceeded_handler", "RateLimitExceeded"]

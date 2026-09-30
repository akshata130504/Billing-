import time
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from backend.app import __version__
from backend.app.api.v1.api_router import api_router
from backend.app.core.config import settings
from backend.app.core.exceptions import AppException, app_exception_handler, validation_exception_handler
from backend.app.core.platform_boundary import (
    PLATFORM_SECURITY_HEADERS,
    PathSplitCORSMiddleware,
    PlatformBoundaryMiddleware,
    is_platform_path,
)
from backend.app.core.logging import correlation_id_ctx, logger
from backend.app.core.rate_limit import RateLimitExceeded, limiter, rate_limit_exceeded_handler


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "script-src 'self' 'unsafe-inline' https://checkout.razorpay.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self' https://api.razorpay.com https://lumberjack.razorpay.com https://lumberjack-cx.razorpay.com; "
        "frame-src 'self' https://api.razorpay.com https://checkout.razorpay.com; "
        "form-action 'self' https://api.razorpay.com; "
        "frame-ancestors 'self';"
    ),
}
HSTS_HEADER = "max-age=31536000; includeSubDomains"
CORS_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Accept-Language",
    "Idempotency-Key",
    "X-Portal-Token",
    "X-Request-ID",
    "X-Correlation-ID",
]
CORS_EXPOSED_HEADERS = ["X-Request-ID", "Content-Disposition", "Retry-After"]
_DOCS_PATHS = {f"{settings.API_V1_STR}/docs", f"{settings.API_V1_STR}/redoc", f"{settings.API_V1_STR}/docs/oauth2-redirect"}


def _init_error_tracking() -> bool:
    """Sentry is optional; import lazily so a missing package cannot crash boot."""
    if not settings.SENTRY_DSN:
        return False
    try:
        from backend.app.core.sentry import init_sentry  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover - defensive
        logger.warning("SENTRY_DSN is set but error tracking could not be loaded (%s); skipping", exc)
        return False
    return init_sentry()


def _warn_if_scheduler_disabled() -> None:
    """Renewals, overdue marking and dunning only run where SCHEDULER_ENABLED=true.

    Exactly one process in the deployment should have it on (the `scheduler`
    service in docker-compose.prod.yml). This runs in the API lifespan, so it
    fires for API processes only - the scheduler process never starts the app.
    """
    if settings.is_production and not settings.SCHEDULER_ENABLED:
        logger.warning(
            "SCHEDULER_ENABLED is false on this API process. This is correct ONLY if a separate "
            "scheduler process is running (docker-compose.prod.yml service 'scheduler'). If no such "
            "process exists, subscription renewals, trial conversions, overdue invoice marking and "
            "dunning reminders will NEVER run."
        )


def _load_scheduler():
    """The scheduler module is optional during the build; import lazily and tolerate its absence."""
    try:
        from backend.app.services.scheduler import start_scheduler, stop_scheduler  # noqa: WPS433
    except ImportError as exc:
        logger.warning("Scheduler enabled but backend.app.services.scheduler is unavailable (%s); skipping", exc)
        return None, None
    return start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application %s started in %s mode (v%s)", settings.PROJECT_NAME, settings.ENVIRONMENT, __version__)
    _warn_if_scheduler_disabled()
    stop_scheduler = None
    if settings.SCHEDULER_ENABLED:
        start_scheduler, stop_scheduler = _load_scheduler()
        if start_scheduler is not None:
            try:
                start_scheduler()
            except Exception:  # never let a background job stop the API from serving
                logger.exception("Failed to start the background scheduler")
                stop_scheduler = None
    yield
    if stop_scheduler is not None:
        try:
            stop_scheduler()
        except Exception:
            logger.exception("Failed to stop the background scheduler cleanly")
    logger.info("Application %s shutting down", settings.PROJECT_NAME)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last line of defence: log the traceback, return the standard envelope, leak nothing."""
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method,
        request.url.path,
        exc,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "details": {},
            }
        },
    )


def create_application() -> FastAPI:
    # Before anything else, so failures during app construction are also captured.
    _init_error_tracking()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=__version__,
        description="Rooman Billing - Enterprise Billing and Subscription Management API",
        openapi_url=f"{settings.API_V1_STR}/openapi.json" if not settings.is_production else None,
        docs_url=f"{settings.API_V1_STR}/docs" if not settings.is_production else None,
        redoc_url=f"{settings.API_V1_STR}/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # CORS for the SPA. Explicit methods/headers; a wildcard origin never gets credentials
    # (production refuses "*" and non-https origins at startup, see config.py).
    # The platform console API (/api/v1/platform) has its own, stricter policy - see platform_boundary.
    wildcard_origin = "*" in settings.ALLOWED_ORIGINS
    app.add_middleware(
        PathSplitCORSMiddleware,
        tenant_options=dict(
            allow_origins=settings.ALLOWED_ORIGINS,
            allow_credentials=not wildcard_origin,
            allow_methods=CORS_ALLOWED_METHODS,
            allow_headers=CORS_ALLOWED_HEADERS,
            expose_headers=CORS_EXPOSED_HEADERS,
            max_age=600,
        ),
    )
    # Platform console host binding and Origin / Sec-Fetch-Site checks (no-op when not configured).
    app.add_middleware(PlatformBoundaryMiddleware)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        # Swagger UI / ReDoc (development only) load their bundles from a CDN, which the CSP
        # would block; every other response (JSON API, uploads) keeps the full header set.
        skip_csp = request.url.path in _DOCS_PATHS
        headers = PLATFORM_SECURITY_HEADERS if is_platform_path(request.url.path) else SECURITY_HEADERS
        for header, value in headers.items():
            if skip_csp and header == "Content-Security-Policy":
                continue
            response.headers.setdefault(header, value)
        if settings.SECURE_COOKIES:
            response.headers.setdefault("Strict-Transport-Security", HSTS_HEADER)
        path = request.url.path
        if path.startswith(settings.API_V1_STR) and not path.startswith(f"{settings.API_V1_STR}/uploads"):
            # API responses carry tokens and tenant data: never store them in shared caches.
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.middleware("http")
    async def request_correlation_and_logging(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.request_id = req_id
        token = correlation_id_ctx.set(req_id)
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response.headers["X-Request-ID"] = req_id
            if not request.url.path.endswith("/health"):
                logger.info(
                    "%s %s -> %s (%sms)",
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                    extra={
                        "request_id": req_id,
                        "path": request.url.path,
                        "method": request.method,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    },
                )
            return response
        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception(
                "Request failed: %s %s (%sms)",
                request.method,
                request.url.path,
                duration_ms,
                extra={
                    "request_id": req_id,
                    "path": request.url.path,
                    "method": request.method,
                    "duration_ms": duration_ms,
                },
            )
            raise
        finally:
            correlation_id_ctx.reset(token)


    # Rate limiting (per client IP) on credential endpoints
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Register Domain Exception Handlers
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Mount API routers
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # Host-header allowlist (outermost middleware). "*" (development/test default) = disabled.
    allowed_hosts = settings.effective_allowed_hosts
    if allowed_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    # Static files for avatars / uploads
    import os
    from fastapi.staticfiles import StaticFiles

    upload_dir = os.path.abspath(settings.UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    app.mount("/api/v1/uploads", StaticFiles(directory=upload_dir), name="api_uploads")
    app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

    @app.get("/", tags=["Root"])
    def root():
        return {
            "name": settings.PROJECT_NAME,
            "version": __version__,
            "docs": None if settings.is_production else f"{settings.API_V1_STR}/docs",
            "health": f"{settings.API_V1_STR}/health",
        }

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=settings.DEBUG,
    )

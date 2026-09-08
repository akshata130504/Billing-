import time
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app import __version__
from backend.app.api.v1.api_router import api_router
from backend.app.core.config import settings
from backend.app.core.exceptions import AppException, app_exception_handler, validation_exception_handler
from backend.app.core.logging import correlation_id_ctx, logger
from backend.app.core.rate_limit import RateLimitExceeded, limiter, rate_limit_exceeded_handler


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
HSTS_HEADER = "max-age=31536000; includeSubDomains"


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
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=__version__,
        description="Rooman Billing - Enterprise Billing and Subscription Management API",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
        lifespan=lifespan,
    )

    # Configure CORS for frontend access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.SECURE_COOKIES:
            response.headers.setdefault("Strict-Transport-Security", HSTS_HEADER)
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

    @app.get("/", tags=["Root"])
    def root():
        return {
            "name": settings.PROJECT_NAME,
            "version": __version__,
            "docs": f"{settings.API_V1_STR}/docs",
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

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app import __version__
from backend.app.core.config import settings
from backend.app.core.exceptions import AppException, app_exception_handler
from backend.app.core.logging import logger
from backend.app.api.v1.api_router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application %s started in %s mode (v%s)", settings.PROJECT_NAME, settings.ENVIRONMENT, __version__)
    yield
    logger.info("Application %s shutting down", settings.PROJECT_NAME)


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

    # Register Domain Exception Handlers
    app.add_exception_handler(AppException, app_exception_handler)

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

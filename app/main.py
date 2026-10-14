"""Main FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import chat
from app.api.v1.endpoints.health import get_health, get_liveness, get_readiness
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import mongodb
from app.core.errors import register_error_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import SecurityHeadersMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for application startup and shutdown lifecycle."""
    # Startup
    setup_logging()
    logger.info(
        "Starting %s [version=%s, env=%s, debug=%s]",
        settings.PROJECT_NAME,
        settings.VERSION,
        settings.ENVIRONMENT,
        settings.DEBUG,
    )

    # Validate production environment configuration
    validation_issues = settings.validate_production_configuration()
    if validation_issues:
        for issue in validation_issues:
            logger.warning("CONFIGURATION WARNING: %s", issue)
        if settings.is_production and any("JWT_SECRET_KEY" in iss for iss in validation_issues):
            raise RuntimeError("Critical production security misconfiguration. Server startup aborted.")

    logger.info("Allowed CORS Origins: %s", settings.CORS_ORIGINS)

    # Initialize MongoDB Atlas connection
    await mongodb.connect()

    yield

    # Shutdown
    logger.info("Shutting down %s", settings.PROJECT_NAME)
    await mongodb.disconnect()


def create_app() -> FastAPI:
    """Application factory for configuring and instantiating the FastAPI application."""
    fastapi_app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=settings.DESCRIPTION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Inject Security Headers Middleware (X-Content-Type-Options, X-Frame-Options, HSTS, etc.)
    fastapi_app.add_middleware(SecurityHeadersMiddleware)

    # Configure CORS Middleware
    if getattr(settings, "CORS_ORIGIN_REGEX", None):
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=settings.CORS_ORIGIN_REGEX,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
        )
    elif getattr(settings, "CORS_ALLOW_ALL_ORIGINS", True):
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=r"^https?://.*$",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
        )
    else:
        cors_origins = (
            settings.CORS_ORIGINS
            if isinstance(settings.CORS_ORIGINS, list)
            else [settings.CORS_ORIGINS]
        )
        if cors_origins:
            fastapi_app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
                expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
            )

    # Register centralized exception handlers
    register_error_handlers(fastapi_app)

    # Root probe endpoints for Kubernetes / Docker / load balancers
    fastapi_app.add_api_route("/health", get_health, methods=["GET"], include_in_schema=False)
    fastapi_app.add_api_route("/live", get_liveness, methods=["GET"], include_in_schema=False)
    fastapi_app.add_api_route("/ready", get_readiness, methods=["GET"], include_in_schema=False)

    # Register Public Chatbot API routes (/api/chat)
    fastapi_app.include_router(chat.router, prefix="/api")

    # Register versioned API routes (/api/v1/...)
    fastapi_app.include_router(api_router, prefix=settings.API_V1_STR)

    # Root informational endpoint
    @fastapi_app.get("/", tags=["Root"])
    async def root() -> Dict[str, str]:
        """Root endpoint displaying service metadata and navigation links."""
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "status": "online",
            "docs_url": "/docs",
            "health_url": f"{settings.API_V1_STR}/health",
        }

    return fastapi_app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

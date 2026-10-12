"""Main FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import mongodb
from app.core.errors import register_error_handlers
from app.core.logging import get_logger, setup_logging

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

    # Configure CORS Middleware
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
        )

    # Register centralized exception handlers
    register_error_handlers(fastapi_app)

    # Register API routes
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

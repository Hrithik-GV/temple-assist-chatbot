"""API v1 router registry aggregating all v1 sub-routers."""

from fastapi import APIRouter
from app.api.v1.endpoints import health

api_router = APIRouter()

# Register endpoint routers
api_router.include_router(health.router)

# Future modules will be registered here:
# api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
# api_router.include_router(ingestion.router, prefix="/ingestion", tags=["Ingestion"])

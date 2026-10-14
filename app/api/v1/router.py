"""API v1 router registry aggregating all v1 sub-routers."""

from fastapi import APIRouter
from app.api.endpoints import chat
from app.api.v1.endpoints import admin_auth, admin_knowledge, admin_temples, health, rag

api_router = APIRouter()

# Register endpoint routers
api_router.include_router(health.router)
api_router.include_router(rag.router)
api_router.include_router(chat.router)

# Register Admin & Authentication routers
api_router.include_router(admin_auth.router)
api_router.include_router(admin_temples.router)
api_router.include_router(admin_knowledge.router)

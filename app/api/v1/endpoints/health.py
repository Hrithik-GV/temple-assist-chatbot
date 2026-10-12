"""Health check and diagnostic API endpoints."""

from typing import Any, Dict
from fastapi import APIRouter, status
from app.core.database import mongodb
from app.models.health import HealthResponse
from app.services.health_service import health_service

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="System Health Check",
    description="Returns the operational status, application version, environment, and dependencies health.",
)
async def get_health() -> HealthResponse:
    """Return comprehensive system health information including MongoDB status."""
    return await health_service.check_health()


@router.get(
    "/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Kubernetes / Docker liveness probe to verify if the server process is alive.",
)
async def get_liveness() -> Dict[str, str]:
    """Return lightweight liveness status."""
    return {"status": "alive"}


@router.get(
    "/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness Probe",
    description="Kubernetes / Docker readiness probe to check if the app is ready to accept traffic.",
)
async def get_readiness() -> Dict[str, Any]:
    """Return readiness status with database readiness flag."""
    return {
        "status": "ready",
        "database": "connected" if mongodb.is_connected else "disconnected",
    }

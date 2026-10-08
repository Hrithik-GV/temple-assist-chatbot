"""Health check response models."""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel, Field

from app.utils.helpers import get_utc_now


class HealthStatus(str, Enum):
    """System health status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health information for a specific subsystem/dependency."""

    status: HealthStatus = Field(default=HealthStatus.HEALTHY, description="Status of the component")
    details: Optional[str] = Field(default=None, description="Optional diagnostic details or latency")


class HealthResponse(BaseModel):
    """Overall system health check response model."""

    status: HealthStatus = Field(default=HealthStatus.HEALTHY, description="Overall system health")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Current running environment")
    timestamp: datetime = Field(default_factory=get_utc_now, description="Current UTC timestamp")
    components: Dict[str, ComponentHealth] = Field(
        default_factory=dict,
        description="Health status of external services (e.g. database, vector store)",
    )

"""Service for checking application health, database connectivity, and readiness."""

from typing import Dict
from app.core.config import settings
from app.core.database import mongodb
from app.models.health import ComponentHealth, HealthResponse, HealthStatus
from app.services.base import BaseService
from app.utils.helpers import get_utc_now


class HealthService(BaseService):
    """Encapsulates system health inspection and dependency status checks."""

    def __init__(self) -> None:
        super().__init__()

    async def check_health(self) -> HealthResponse:
        """Evaluate application health including MongoDB Atlas connectivity."""
        self.logger.debug("Executing system health check")

        components: Dict[str, ComponentHealth] = {}

        # 1. MongoDB connectivity check
        mongo_health = await mongodb.check_health()
        components["mongodb"] = mongo_health

        # Compute overall system health status
        overall_status = HealthStatus.HEALTHY
        if mongo_health.status != HealthStatus.HEALTHY:
            overall_status = HealthStatus.DEGRADED

        return HealthResponse(
            status=overall_status,
            app_name=settings.PROJECT_NAME,
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
            timestamp=get_utc_now(),
            components=components,
        )


health_service = HealthService()

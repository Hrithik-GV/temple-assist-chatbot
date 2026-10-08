"""Service for checking application health and readiness."""

from typing import Dict
from app.core.config import settings
from app.models.health import ComponentHealth, HealthResponse, HealthStatus
from app.services.base import BaseService
from app.utils.helpers import get_utc_now


class HealthService(BaseService):
    """Encapsulates system health inspection and dependency status checks."""

    def __init__(self) -> None:
        super().__init__()

    async def check_health(self) -> HealthResponse:
        """Evaluate application health.

        In future phases, this will check connections to MongoDB, Vector Store, etc.
        """
        self.logger.debug("Executing system health check")

        # Future extensions can append checks for MongoDB, Qdrant/Chroma, etc.
        components: Dict[str, ComponentHealth] = {}

        return HealthResponse(
            status=HealthStatus.HEALTHY,
            app_name=settings.PROJECT_NAME,
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
            timestamp=get_utc_now(),
            components=components,
        )


health_service = HealthService()

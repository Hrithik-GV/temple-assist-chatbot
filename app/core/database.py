"""MongoDB connection manager and lifecycle handling using the official Motor/PyMongo driver."""

from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, PyMongoError

from app.core.config import settings
from app.core.errors import ServiceUnavailableException
from app.core.logging import get_logger
from app.models.collections import Collections
from app.models.health import ComponentHealth, HealthStatus

logger = get_logger(__name__)


class MongoDBManager:
    """Manages the MongoDB Atlas client lifecycle, session pools, and health checks."""

    def __init__(self) -> None:
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self._is_connected: bool = False

    @property
    def is_connected(self) -> bool:
        """Return whether the database is currently marked as connected."""
        return self._is_connected

    async def connect(self) -> None:
        """Establish asynchronous connection pool to MongoDB Atlas."""
        if self.client is not None and self._is_connected:
            logger.info("MongoDB client is already connected.")
            return

        logger.info(
            "Connecting to MongoDB Atlas (database: %s, minPool: %d, maxPool: %d)...",
            settings.MONGODB_DB_NAME,
            settings.MONGODB_MIN_POOL_SIZE,
            settings.MONGODB_MAX_POOL_SIZE,
        )

        try:
            self.client = AsyncIOMotorClient(
                settings.MONGODB_URI,
                minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
                maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
                serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
                connectTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
            )
            self.db = self.client[settings.MONGODB_DB_NAME]

            # Verify connection with a lightweight ping
            await self.ping()
            self._is_connected = True
            logger.info("Successfully connected to MongoDB Atlas database: '%s'", settings.MONGODB_DB_NAME)

            # Auto-ensure indexes for collections
            await self.create_indexes()

        except (ConnectionFailure, PyMongoError, Exception) as exc:
            self._is_connected = False
            logger.warning(
                "Could not establish active connection to MongoDB Atlas: %s. Application continuing in degraded mode.",
                str(exc),
            )

    async def disconnect(self) -> None:
        """Gracefully close the MongoDB Atlas connection pool."""
        if self.client is not None:
            logger.info("Closing MongoDB Atlas connection pool...")
            self.client.close()
            self.client = None
            self.db = None
            self._is_connected = False
            logger.info("MongoDB connection pool closed.")

    def get_database(self) -> AsyncIOMotorDatabase:
        """Retrieve active database handle.

        Raises:
            ServiceUnavailableException: If client is not connected.
        """
        if self.db is None:
            raise ServiceUnavailableException(
                message="MongoDB connection is not initialized or currently unavailable."
            )
        return self.db

    def get_collection(self, collection_name: str) -> AsyncIOMotorCollection:
        """Retrieve collection reference by name.

        Args:
            collection_name: Name of collection.

        Returns:
            AsyncIOMotorCollection instance.
        """
        return self.get_database()[collection_name]

    async def ping(self) -> bool:
        """Send ping command to verify database availability.

        Returns:
            bool: True if database responds with ok: 1, False otherwise.
        """
        if self.client is None or self.db is None:
            return False
        try:
            result = await self.db.command("ping")
            return bool(result and result.get("ok") == 1.0)
        except Exception as exc:
            logger.debug("MongoDB ping failed: %s", exc)
            return False

    async def check_health(self) -> ComponentHealth:
        """Perform diagnostic health check on MongoDB connection.

        Returns:
            ComponentHealth: Structured status for the health endpoint.
        """
        if self.client is None or self.db is None:
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                details="MongoDB client is not initialized",
            )

        try:
            result = await self.db.command("ping")
            if result and result.get("ok") == 1.0:
                return ComponentHealth(
                    status=HealthStatus.HEALTHY,
                    details=f"Connected to MongoDB database '{settings.MONGODB_DB_NAME}'",
                )
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                details="MongoDB ping command did not return success",
            )
        except Exception as exc:
            logger.warning("MongoDB health check ping failed: %s", exc)
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                details=f"MongoDB ping failed: {str(exc)}",
            )

    async def create_indexes(self) -> Dict[str, List[str]]:
        """Create necessary indexes on core collections for multi-temple support."""
        if self.db is None:
            return {}

        results: Dict[str, List[str]] = {}

        try:
            # 1. Temples: unique slug
            temples_col = self.db[Collections.TEMPLES]
            idx_slug = await temples_col.create_index("slug", unique=True, background=True)
            idx_active = await temples_col.create_index("isActive", background=True)
            results[Collections.TEMPLES] = [idx_slug, idx_active]

            # 2. Knowledge Documents: templeId + createdAt, templeId + contentHash
            docs_col = self.db[Collections.KNOWLEDGE_DOCUMENTS]
            idx_doc_temple = await docs_col.create_index([("templeId", 1), ("createdAt", -1)], background=True)
            idx_doc_status = await docs_col.create_index([("templeId", 1), ("status", 1)], background=True)
            idx_doc_hash = await docs_col.create_index([("templeId", 1), ("contentHash", 1)], background=True)
            results[Collections.KNOWLEDGE_DOCUMENTS] = [idx_doc_temple, idx_doc_status, idx_doc_hash]

            # 3. Knowledge Chunks: templeId + documentId + chunkIndex
            chunks_col = self.db[Collections.KNOWLEDGE_CHUNKS]
            idx_chunk = await chunks_col.create_index(
                [("templeId", 1), ("documentId", 1), ("chunkIndex", 1)],
                background=True,
            )
            results[Collections.KNOWLEDGE_CHUNKS] = [idx_chunk]

            # 4. Admins: unique email, templeId + role
            admins_col = self.db[Collections.ADMINS]
            idx_email = await admins_col.create_index("email", unique=True, background=True)
            idx_admin_temple = await admins_col.create_index([("templeId", 1), ("role", 1)], background=True)
            results[Collections.ADMINS] = [idx_email, idx_admin_temple]

            # 5. Conversations: templeId + sessionId
            conv_col = self.db[Collections.CONVERSATIONS]
            idx_conv = await conv_col.create_index([("templeId", 1), ("sessionId", 1)], background=True)
            results[Collections.CONVERSATIONS] = [idx_conv]

            # 6. Messages: templeId + conversationId + createdAt
            msg_col = self.db[Collections.MESSAGES]
            idx_msg = await msg_col.create_index(
                [("templeId", 1), ("conversationId", 1), ("createdAt", 1)],
                background=True,
            )
            results[Collections.MESSAGES] = [idx_msg]

            logger.info("MongoDB initial collection indexes ensured successfully.")
        except Exception as exc:
            logger.warning("Could not create MongoDB indexes: %s", str(exc))

        return results


# Global singleton instance
mongodb = MongoDBManager()


def get_db() -> AsyncIOMotorDatabase:
    """FastAPI dependency for injecting the active database into endpoint handlers."""
    return mongodb.get_database()

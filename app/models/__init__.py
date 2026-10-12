"""Domain models and Pydantic schemas."""

from app.models.admin import Admin, AdminRole
from app.models.base import MongoBaseModel
from app.models.collections import Collections
from app.models.common import ErrorDetail, StandardResponse
from app.models.conversation import Conversation
from app.models.health import ComponentHealth, HealthResponse, HealthStatus
from app.models.knowledge import (
    DocumentSourceType,
    DocumentStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    VectorSearchResult,
)
from app.models.message import Message, MessageRole
from app.models.temple import Temple, TempleContact, TempleLocation, TempleTimings

__all__ = [
    # Common
    "StandardResponse",
    "ErrorDetail",
    "MongoBaseModel",
    "Collections",
    # Health
    "HealthResponse",
    "HealthStatus",
    "ComponentHealth",
    # Temple
    "Temple",
    "TempleLocation",
    "TempleTimings",
    "TempleContact",
    # Knowledge
    "KnowledgeDocument",
    "KnowledgeChunk",
    "VectorSearchResult",
    "DocumentStatus",
    "DocumentSourceType",
    # Admin
    "Admin",
    "AdminRole",
    # Conversation & Message
    "Conversation",
    "Message",
    "MessageRole",
]

"""Domain models and Pydantic schemas."""

from app.models.admin import Admin, AdminRole
from app.models.base import MongoBaseModel
from app.models.collections import Collections
from app.models.common import ErrorDetail, StandardResponse
from app.models.chat import ChatRequest, ChatResponse, ChatSource
from app.models.conversation import Conversation
from app.models.health import ComponentHealth, HealthResponse, HealthStatus
from app.models.knowledge import (
    DocumentSourceType,
    DocumentStatus,
    IngestionResult,
    KnowledgeChunk,
    KnowledgeDocument,
    VectorSearchResult,
)
from app.models.message import Message, MessageRole
from app.models.rag import LLMResponse, RAGAnswerResponse, RAGQueryRequest, RAGSourceCitation
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
    "IngestionResult",
    "DocumentStatus",
    "DocumentSourceType",
    # RAG
    "RAGQueryRequest",
    "RAGAnswerResponse",
    "RAGSourceCitation",
    "LLMResponse",
    # Chat
    "ChatRequest",
    "ChatResponse",
    "ChatSource",
    # Admin
    "Admin",
    "AdminRole",
    # Conversation & Message
    "Conversation",
    "Message",
    "MessageRole",
]

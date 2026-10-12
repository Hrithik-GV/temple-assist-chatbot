"""Chat message model for conversational exchange history."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field
from app.models.base import MongoBaseModel


class MessageRole(str, Enum):
    """Origin role for a conversational message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(MongoBaseModel):
    """Single dialogue message within a conversation."""

    temple_id: str = Field(
        ...,
        alias="templeId",
        serialization_alias="templeId",
        description="ID of the temple context for this message (required for multi-tenancy)",
    )
    conversation_id: str = Field(
        ...,
        alias="conversationId",
        serialization_alias="conversationId",
        description="Foreign key pointing to the parent Conversation",
    )
    role: MessageRole = Field(
        default=MessageRole.USER,
        description="Role of the sender (user, assistant, system)",
    )
    content: str = Field(..., description="Message text content")
    sources: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Citations/grounding references (for future RAG responses)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Message telemetry (token usage, latency, feedback rating, etc.)",
    )

    @property
    def templeId(self) -> str:
        """Convenience property for camelCase templeId access."""
        return self.temple_id

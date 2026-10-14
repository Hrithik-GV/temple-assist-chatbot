"""Conversation model for tracking multi-turn chat sessions per temple."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import Field
from app.models.base import MongoBaseModel


class Conversation(MongoBaseModel):
    """Chat session model scoped to a specific temple."""

    temple_id: str = Field(
        ...,
        alias="templeId",
        serialization_alias="templeId",
        description="ID of the temple this conversation belongs to (required for multi-tenancy)",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        alias="conversationId",
        serialization_alias="conversationId",
        description="Explicit unique conversation identifier",
    )
    session_id: Optional[str] = Field(
        default=None,
        alias="sessionId",
        serialization_alias="sessionId",
        description="Unique client/browser session identifier",
    )
    user_id: Optional[str] = Field(
        default=None,
        alias="userId",
        serialization_alias="userId",
        description="Optional unique identifier for registered or returning visitor",
    )
    user_language: str = Field(
        default="en",
        alias="userLanguage",
        description="Preferred visitor language (e.g. 'en', 'te', 'hi')",
    )
    title: Optional[str] = Field(
        default=None,
        description="Auto-generated or inferred topic title of the dialogue",
    )
    is_active: bool = Field(
        default=True,
        alias="isActive",
        description="Whether conversation is ongoing or archived",
    )
    message_count: int = Field(
        default=0,
        alias="messageCount",
        description="Total number of messages exchanged in this conversation",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        alias="expiresAt",
        description="TTL expiration timestamp for automatic history retention",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Session metadata (client device, referrer, channel, etc. scrubbed of PII)",
    )

    @property
    def templeId(self) -> str:
        """Convenience property for camelCase templeId access."""
        return self.temple_id

    @property
    def conversationId(self) -> Optional[str]:
        """Convenience property for conversationId access."""
        return self.conversation_id or self.id

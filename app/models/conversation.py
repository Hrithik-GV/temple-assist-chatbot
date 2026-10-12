"""Conversation model for tracking multi-turn chat sessions per temple."""

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
    session_id: str = Field(
        ...,
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
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Session metadata (client IP, device, referrer, channel, etc.)",
    )

    @property
    def templeId(self) -> str:
        """Convenience property for camelCase templeId access."""
        return self.temple_id

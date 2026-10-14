"""Pydantic schemas for the public Chatbot API."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ChatSource(BaseModel):
    """Source provenance citation for public chat responses."""

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(..., description="Document or page title")
    source: Optional[str] = Field(default=None, description="Original source filename or reference")
    url: Optional[str] = Field(default=None, description="Direct URL if sourced from website")
    snippet: Optional[str] = Field(default=None, description="Relevant content snippet excerpt")
    score: Optional[float] = Field(default=None, description="Relevance similarity score")


class ChatRequest(BaseModel):
    """Request payload for the public chat endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    temple_id: str = Field(
        ...,
        alias="templeId",
        min_length=1,
        max_length=100,
        description="Identifier of the temple to converse with",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User message or question",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        alias="conversationId",
        description="Optional conversation/session identifier to continue an ongoing multi-turn dialogue",
    )
    session_id: Optional[str] = Field(
        default=None,
        alias="sessionId",
        description="Optional client browser/device session identifier",
    )


class ChatResponse(BaseModel):
    """Response payload for the public chat endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    answer: str = Field(..., description="Grounded answer from the Temple Assistant")
    sources: List[ChatSource] = Field(
        default_factory=list,
        description="Attribution source citations from verified temple records",
    )
    temple_id: str = Field(..., alias="templeId", description="Target temple identifier")
    conversation_id: str = Field(
        ...,
        alias="conversationId",
        description="Active conversation identifier for multi-turn continuity",
    )
    session_id: Optional[str] = Field(
        default=None,
        alias="sessionId",
        description="Session identifier if provided or associated",
    )
    has_relevant_context: bool = Field(
        default=False,
        alias="hasRelevantContext",
        description="Whether answer was grounded in verified temple knowledge records",
    )

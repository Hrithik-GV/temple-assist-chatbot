"""Knowledge document and chunk models for temple knowledge bases."""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import Field
from app.models.base import MongoBaseModel


class DocumentStatus(str, Enum):
    """Lifecycle status of an ingested knowledge document."""

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class DocumentSourceType(str, Enum):
    """Source provenance of the knowledge document."""

    WEBSITE = "website"
    PDF = "pdf"
    FAQ = "faq"
    TEXT = "text"
    MANUAL = "manual"


class KnowledgeDocument(MongoBaseModel):
    """Document containing ingested knowledge for a specific temple."""

    temple_id: str = Field(
        ...,
        alias="templeId",
        serialization_alias="templeId",
        description="ID of the associated temple (required for multi-tenancy)",
    )
    title: str = Field(..., description="Document title or section headline")
    source_type: DocumentSourceType = Field(
        default=DocumentSourceType.MANUAL,
        alias="sourceType",
        description="Origin source type",
    )
    source_url: Optional[str] = Field(
        default=None,
        alias="sourceUrl",
        description="Original web URL or file URL if applicable",
    )
    raw_content: Optional[str] = Field(
        default=None,
        alias="rawContent",
        description="Full unchunked text of the document",
    )
    summary: Optional[str] = Field(default=None, description="Optional brief summary")
    status: DocumentStatus = Field(
        default=DocumentStatus.PENDING,
        description="Current processing state",
    )
    chunk_count: int = Field(
        default=0,
        alias="chunkCount",
        description="Number of chunks generated from this document",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom metadata attributes (tags, section headers, author, etc.)",
    )

    @property
    def templeId(self) -> str:
        """Convenience property for camelCase templeId access."""
        return self.temple_id


class KnowledgeChunk(MongoBaseModel):
    """Processed text segment derived from a KnowledgeDocument for retrieval."""

    temple_id: str = Field(
        ...,
        alias="templeId",
        serialization_alias="templeId",
        description="ID of the associated temple (required for multi-tenancy)",
    )
    document_id: str = Field(
        ...,
        alias="documentId",
        serialization_alias="documentId",
        description="Reference ID of the parent KnowledgeDocument",
    )
    chunk_index: int = Field(
        default=0,
        alias="chunkIndex",
        description="0-indexed position within the parent document",
    )
    content: str = Field(..., description="Segment text content")
    token_count: Optional[int] = Field(
        default=None,
        alias="tokenCount",
        description="Calculated token length of the chunk",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Chunk-level metadata (e.g. section title, page number, url)",
    )

    @property
    def templeId(self) -> str:
        """Convenience property for camelCase templeId access."""
        return self.temple_id

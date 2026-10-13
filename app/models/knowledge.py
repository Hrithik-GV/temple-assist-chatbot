"""Knowledge document and chunk models for temple knowledge bases."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
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
    DOCX = "docx"
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
    source: Optional[str] = Field(
        default=None,
        description="Original file path, filename, or source identifier",
    )
    source_url: Optional[str] = Field(
        default=None,
        alias="sourceUrl",
        description="Original web URL or file URL if applicable",
    )
    category: Optional[str] = Field(
        default=None,
        description="Classification category (e.g. 'history', 'rituals', 'timings')",
    )
    content_hash: Optional[str] = Field(
        default=None,
        alias="contentHash",
        serialization_alias="contentHash",
        description="SHA-256 hash of cleaned text for deduplication",
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
    """Processed text segment derived from a KnowledgeDocument for vector retrieval."""

    temple_id: str = Field(
        ...,
        min_length=1,
        alias="templeId",
        serialization_alias="templeId",
        description="ID of the associated temple (required for multi-tenancy)",
    )
    document_id: str = Field(
        ...,
        min_length=1,
        alias="documentId",
        serialization_alias="documentId",
        description="Reference ID of the parent KnowledgeDocument",
    )
    content: str = Field(..., min_length=1, description="Segment text content")
    embedding: Optional[List[float]] = Field(
        default=None,
        description="Dense vector embedding representation of the chunk text",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Chunk-level metadata (e.g. section title, page number, url)",
    )
    source: Optional[str] = Field(
        default=None,
        description="Source provenance (e.g. website URL or document title)",
    )
    title: Optional[str] = Field(
        default=None,
        description="Headline or topic title for this chunk",
    )
    category: Optional[str] = Field(
        default=None,
        description="Category classification (e.g. 'rituals', 'history', 'timings', 'darshan')",
    )
    chunk_index: int = Field(
        default=0,
        alias="chunkIndex",
        description="0-indexed position within the parent document",
    )
    token_count: Optional[int] = Field(
        default=None,
        alias="tokenCount",
        description="Calculated token length of the chunk",
    )
    score: Optional[float] = Field(
        default=None,
        description="Vector search similarity score (populated during retrieval)",
    )

    @property
    def templeId(self) -> str:
        """Convenience property for camelCase templeId access."""
        return self.temple_id

    @property
    def documentId(self) -> str:
        """Convenience property for camelCase documentId access."""
        return self.document_id


class VectorSearchResult(BaseModel):
    """Result item returned by vector similarity search."""

    model_config = ConfigDict(populate_by_name=True)

    chunk: KnowledgeChunk = Field(..., description="Retrieved knowledge chunk")
    score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")


class IngestionResult(BaseModel):
    """Result report returned after processing an ingested document."""

    model_config = ConfigDict(populate_by_name=True)

    document_id: str = Field(..., alias="documentId", description="ID of the created or updated KnowledgeDocument")
    temple_id: str = Field(..., alias="templeId", description="Associated temple ID")
    title: str = Field(..., description="Document title")
    status: DocumentStatus = Field(..., description="Final processing status")
    chunks_created: int = Field(default=0, alias="chunksCreated", description="Number of vector chunks generated")
    is_duplicate: bool = Field(default=False, alias="isDuplicate", description="Whether document was skipped due to duplicate hash")
    message: str = Field(default="Ingestion completed successfully.", description="Status narrative or error explanation")
    content_hash: Optional[str] = Field(default=None, alias="contentHash", description="SHA-256 fingerprint of the cleaned content")


class CrawlPageResult(BaseModel):
    """Result of crawling and ingesting an individual web page."""

    model_config = ConfigDict(populate_by_name=True)

    url: str = Field(..., description="Target page URL")
    title: str = Field(default="", description="Extracted page title")
    status: str = Field(..., description="Outcome: ingested, skipped_duplicate, empty, or failed")
    chunks_created: int = Field(default=0, alias="chunksCreated", description="Number of vector chunks created")
    document_id: Optional[str] = Field(default=None, alias="documentId", description="ID of KnowledgeDocument in MongoDB")
    error: Optional[str] = Field(default=None, description="Error message if crawling or ingestion failed")


class CrawlSummary(BaseModel):
    """Overall summary of a website crawl run for a temple."""

    model_config = ConfigDict(populate_by_name=True)

    temple_id: str = Field(..., alias="templeId", description="Associated temple ID")
    start_url: str = Field(..., alias="startUrl", description="Initial entry URL of the crawl")
    total_pages_visited: int = Field(default=0, alias="totalPagesVisited", description="Total pages visited by Playwright")
    pages_ingested: int = Field(default=0, alias="pagesIngested", description="Pages successfully cleaned and indexed")
    pages_skipped: int = Field(default=0, alias="pagesSkipped", description="Pages skipped (empty content or duplicates)")
    pages_failed: int = Field(default=0, alias="pagesFailed", description="Pages that failed with errors or timeouts")
    total_chunks_created: int = Field(default=0, alias="totalChunksCreated", description="Total vector chunks generated")
    duration_seconds: float = Field(default=0.0, alias="durationSeconds", description="Total crawl duration in seconds")
    page_results: List[CrawlPageResult] = Field(default_factory=list, alias="pageResults", description="Individual page crawl results")

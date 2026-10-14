"""Pydantic schemas and domain models for RAG (Retrieval-Augmented Generation)."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RAGSourceCitation(BaseModel):
    """Citation metadata for a knowledge chunk used in grounding the answer."""

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(..., description="Document or section headline")
    source: Optional[str] = Field(default=None, description="Source provenance (filename or URL)")
    source_url: Optional[str] = Field(default=None, alias="sourceUrl", description="Web URL if available")
    category: Optional[str] = Field(default=None, description="Topic or category tag")
    chunk_index: int = Field(default=0, alias="chunkIndex", description="Zero-based index within parent document")
    score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")
    content_snippet: str = Field(..., alias="contentSnippet", description="Preview snippet of the chunk text")
    document_id: Optional[str] = Field(default=None, alias="documentId", description="Parent KnowledgeDocument ID")


class RAGQueryRequest(BaseModel):
    """Incoming user question request for temple knowledge retrieval."""

    model_config = ConfigDict(populate_by_name=True)

    temple_id: str = Field(
        ...,
        alias="templeId",
        min_length=1,
        description="Target temple ID (mandatory for multi-tenant isolation)",
    )
    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language question from the devotee/visitor",
    )
    top_k: Optional[int] = Field(
        default=None,
        alias="topK",
        ge=1,
        le=50,
        description="Number of candidate chunks to retrieve",
    )
    similarity_threshold: Optional[float] = Field(
        default=None,
        alias="similarityThreshold",
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity cutoff score",
    )
    category: Optional[str] = Field(
        default=None,
        description="Optional filter by category (e.g. 'rituals', 'history', 'timings')",
    )


class RAGAnswerResponse(BaseModel):
    """Generated response with grounded answer and attribution sources."""

    model_config = ConfigDict(populate_by_name=True)

    answer: str = Field(..., description="LLM-generated answer or no-context disclaimer")
    temple_id: str = Field(..., alias="templeId", description="Target temple ID")
    question: str = Field(..., description="Original user query")
    sources: List[RAGSourceCitation] = Field(
        default_factory=list,
        description="Knowledge chunks that grounded the answer",
    )
    has_relevant_context: bool = Field(
        default=False,
        alias="hasRelevantContext",
        description="True if chunks met the relevance threshold",
    )
    top_score: Optional[float] = Field(
        default=None,
        alias="topScore",
        description="Highest similarity score among retrieved chunks",
    )
    latency_ms: Optional[float] = Field(
        default=None,
        alias="latencyMs",
        description="End-to-end question answering latency in milliseconds",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Operational metadata (model name, chunks retrieved, etc.)",
    )


class LLMResponse(BaseModel):
    """Normalized response payload returned by any LLM provider."""

    model_config = ConfigDict(populate_by_name=True)

    content: str = Field(..., description="Generated text completion")
    model: str = Field(..., description="Exact model name used")
    usage: Optional[Dict[str, int]] = Field(
        default=None,
        description="Token consumption metrics (prompt, completion, total)",
    )

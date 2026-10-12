"""Tests for knowledge chunk vector schema, embedding generation, and vector search service."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import BadRequestException
from app.models.knowledge import KnowledgeChunk, VectorSearchResult
from app.services.embedding_service import (
    EmbeddingService,
    FastEmbedProvider,
    MockEmbeddingProvider,
)
from app.services.vector_search_service import VectorSearchService, cosine_similarity


# ==============================================================================
# 1. KnowledgeChunk Schema Tests
# ==============================================================================


def test_knowledge_chunk_schema_all_fields() -> None:
    """Verify that KnowledgeChunk supports all required schema fields including vector & metadata."""
    sample_embedding = [0.05] * 384
    chunk = KnowledgeChunk(
        templeId="temple_tirumala",
        documentId="doc_rituals_01",
        content="Suprabhata Seva is performed early morning to awaken the Lord.",
        embedding=sample_embedding,
        source="https://tirumala.org/rituals",
        title="Daily Seva Routine",
        category="rituals",
        chunkIndex=0,
        tokenCount=14,
        metadata={"section": "Daily Sevas", "author": "Administration"},
    )

    assert chunk.temple_id == "temple_tirumala"
    assert chunk.templeId == "temple_tirumala"
    assert chunk.document_id == "doc_rituals_01"
    assert chunk.documentId == "doc_rituals_01"
    assert chunk.content == "Suprabhata Seva is performed early morning to awaken the Lord."
    assert chunk.embedding is not None and len(chunk.embedding) == 384
    assert chunk.source == "https://tirumala.org/rituals"
    assert chunk.title == "Daily Seva Routine"
    assert chunk.category == "rituals"
    assert chunk.chunk_index == 0
    assert chunk.token_count == 14
    assert chunk.metadata["section"] == "Daily Sevas"
    assert chunk.created_at is not None
    assert chunk.updated_at is not None

    # Check MongoDB serialization
    mongo_dict = chunk.to_mongo_dict()
    assert mongo_dict["templeId"] == "temple_tirumala"
    assert mongo_dict["documentId"] == "doc_rituals_01"
    assert mongo_dict["title"] == "Daily Seva Routine"
    assert mongo_dict["category"] == "rituals"
    assert mongo_dict["source"] == "https://tirumala.org/rituals"
    assert len(mongo_dict["embedding"]) == 384


def test_knowledge_chunk_validation_errors() -> None:
    """Verify that missing templeId or content raises ValidationError."""
    with pytest.raises(ValidationError):
        KnowledgeChunk(documentId="doc_1", content="Text without templeId")

    with pytest.raises(ValidationError):
        KnowledgeChunk(templeId="temple_1", documentId="doc_1", content="")


# ==============================================================================
# 2. Embedding Service & Provider Tests
# ==============================================================================


def test_fastembed_local_generation() -> None:
    """Verify local embedding generation with FastEmbed produces 384-dim vectors."""
    provider = FastEmbedProvider(model_name=settings.EMBEDDING_MODEL_NAME)
    assert provider.dimension == 384
    assert provider.model_name == settings.EMBEDDING_MODEL_NAME

    vec = provider.embed_text("Lord Venkateswara Darshan Timings")
    assert isinstance(vec, list)
    assert len(vec) == 384
    assert all(isinstance(x, float) for x in vec)

    # Batch generation
    batch_vecs = provider.embed_texts(["First text", "Second text"])
    assert len(batch_vecs) == 2
    assert len(batch_vecs[0]) == 384
    assert len(batch_vecs[1]) == 384


def test_embedding_service_empty_text_error() -> None:
    """Verify embedding service rejects empty text input."""
    service = EmbeddingService(MockEmbeddingProvider())
    with pytest.raises(BadRequestException):
        service.generate_embedding("")

    with pytest.raises(BadRequestException):
        service.generate_embedding("   ")


def test_embedding_service_swappable_provider() -> None:
    """Verify that embedding provider can be switched cleanly."""
    service = EmbeddingService(MockEmbeddingProvider(dimension=256, model_name="mock-256"))
    assert service.get_dimension() == 256
    vec1 = service.generate_embedding("Temple festival")
    assert len(vec1) == 256

    # Swap provider
    service.set_provider(MockEmbeddingProvider(dimension=384, model_name="mock-384"))
    assert service.get_dimension() == 384
    vec2 = service.generate_embedding("Temple festival")
    assert len(vec2) == 384


def test_embedding_service_embed_chunk() -> None:
    """Verify embed_chunk populates the chunk's embedding attribute."""
    service = EmbeddingService(MockEmbeddingProvider())
    chunk = KnowledgeChunk(
        templeId="temple_1",
        documentId="doc_1",
        content="Poojas begin at 5 AM every morning.",
    )
    assert chunk.embedding is None

    service.embed_chunk(chunk)
    assert chunk.embedding is not None
    assert len(chunk.embedding) == 384


def test_embedding_service_embed_chunks_batch() -> None:
    """Verify embed_chunks batch populates embeddings on multiple chunks."""
    service = EmbeddingService(MockEmbeddingProvider())
    c1 = KnowledgeChunk(templeId="t1", documentId="d1", content="Text one")
    c2 = KnowledgeChunk(templeId="t1", documentId="d1", content="Text two")

    res = service.embed_chunks([c1, c2])
    assert len(res) == 2
    assert c1.embedding is not None and len(c1.embedding) == 384
    assert c2.embedding is not None and len(c2.embedding) == 384


# ==============================================================================
# 3. Vector Search Service Tests
# ==============================================================================


@pytest.mark.anyio
async def test_vector_search_validation() -> None:
    """Verify input validation rules for semantic vector search."""
    service = VectorSearchService(embed_service=EmbeddingService(MockEmbeddingProvider()))

    # Missing templeId
    with pytest.raises(BadRequestException):
        await service.search(temple_id="", query="darshan")

    # Empty query
    with pytest.raises(BadRequestException):
        await service.search(temple_id="temple_1", query="   ")


@pytest.mark.anyio
async def test_vector_search_atlas_pipeline_construction() -> None:
    """Verify that search builds the correct MongoDB Atlas $vectorSearch aggregation pipeline."""
    mock_provider = MockEmbeddingProvider()
    service = VectorSearchService(embed_service=EmbeddingService(mock_provider))

    # Mock MongoDB aggregation cursor
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {
                "_id": "670ab349f123456789abcdef",
                "templeId": "temple_tirupati",
                "documentId": "doc_timings",
                "content": "Special Darshan begins at 9:00 AM.",
                "title": "Darshan Schedule",
                "source": "https://tirupati.org/timings",
                "category": "timings",
                "metadata": {},
                "score": 0.88,
            }
        ]
    )

    mock_collection = MagicMock()
    mock_collection.aggregate = MagicMock(return_value=mock_cursor)

    with patch.object(VectorSearchService, "chunks_collection", new=mock_collection):
        results = await service.search(
            temple_id="temple_tirupati",
            query="When does Special Darshan begin?",
            top_k=5,
            category="timings",
            min_score=0.7,
        )

        assert len(results) == 1
        assert isinstance(results[0], VectorSearchResult)
        assert results[0].score == 0.88
        assert results[0].chunk.title == "Darshan Schedule"
        assert results[0].chunk.temple_id == "temple_tirupati"

        # Verify pipeline structure passed to aggregate()
        mock_collection.aggregate.assert_called_once()
        pipeline = mock_collection.aggregate.call_args[0][0]
        assert len(pipeline) == 2

        v_search_stage = pipeline[0]["$vectorSearch"]
        assert v_search_stage["index"] == settings.VECTOR_SEARCH_INDEX_NAME
        assert v_search_stage["path"] == "embedding"
        assert len(v_search_stage["queryVector"]) == 384
        assert v_search_stage["limit"] == 5
        assert v_search_stage["filter"] == {
            "templeId": {"$eq": "temple_tirupati"},
            "category": {"$eq": "timings"},
        }


@pytest.mark.anyio
async def test_store_chunk_auto_generates_embedding() -> None:
    """Verify store_chunk generates embedding if missing before persisting."""
    service = VectorSearchService(embed_service=EmbeddingService(MockEmbeddingProvider()))

    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="new_chunk_id"))

    chunk = KnowledgeChunk(
        templeId="temple_somnath",
        documentId="doc_somnath_history",
        content="Somnath is the first among the twelve Aadi Jyotirlingas.",
        title="First Jyotirlinga",
        category="history",
    )
    assert chunk.embedding is None

    with patch.object(VectorSearchService, "chunks_collection", new=mock_collection):
        stored = await service.store_chunk(chunk)
        assert stored.id == "new_chunk_id"
        assert stored.embedding is not None
        assert len(stored.embedding) == 384
        mock_collection.insert_one.assert_called_once()


@pytest.mark.anyio
async def test_fallback_in_memory_search_similarity_ranking() -> None:
    """Verify local fallback ranking by cosine similarity when $vectorSearch is not active."""
    service = VectorSearchService(embed_service=EmbeddingService(MockEmbeddingProvider()))

    # Build 3 chunks with different mock embeddings
    query_vec = [1.0, 0.0, 0.0] + [0.0] * 381
    high_match_vec = [0.99, 0.01, 0.0] + [0.0] * 381
    low_match_vec = [0.1, 0.9, 0.0] + [0.0] * 381

    raw_docs = [
        {
            "_id": "c1",
            "templeId": "temple_kashi",
            "documentId": "doc_1",
            "content": "Kashi Vishwanath morning aarti timing.",
            "embedding": low_match_vec,
            "category": "rituals",
        },
        {
            "_id": "c2",
            "templeId": "temple_kashi",
            "documentId": "doc_1",
            "content": "Exact match for aarti schedule.",
            "embedding": high_match_vec,
            "category": "rituals",
        },
    ]

    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=raw_docs)
    mock_col = MagicMock()
    mock_col.find = MagicMock(return_value=mock_cursor)

    with patch.object(VectorSearchService, "chunks_collection", new=mock_col):
        results = await service._fallback_in_memory_search(
            temple_id="temple_kashi",
            query_vector=query_vec,
            limit=2,
        )

        assert len(results) == 2
        # Highest match should be first
        assert results[0].chunk.id == "c2"
        assert results[0].score > results[1].score
        assert results[1].chunk.id == "c1"


def test_cosine_similarity_edge_cases() -> None:
    """Test cosine similarity function edge cases (empty, orthogonal, identical)."""
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert abs(cosine_similarity([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-6
    assert abs(cosine_similarity([1.0, 1.0], [2.0, 2.0]) - 1.0) < 1e-6

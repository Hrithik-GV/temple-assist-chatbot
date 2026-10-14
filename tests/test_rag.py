"""Tests for RAG question-answering service, context synthesis, prompt construction, and LLM providers."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.core.errors import AppException, BadRequestException
from app.models.knowledge import KnowledgeChunk, VectorSearchResult
from app.models.rag import LLMResponse, RAGAnswerResponse, RAGQueryRequest
from app.services.embedding_service import EmbeddingService, MockEmbeddingProvider
from app.services.llm_service import (
    BaseLLMProvider,
    GeminiLLMProvider,
    LLMService,
    MockLLMProvider,
    OpenAILLMProvider,
)
from app.services.rag_service import (
    NO_CONTEXT_FALLBACK_ANSWER,
    SYSTEM_PROMPT_TEMPLATE,
    RAGService,
)
from app.services.vector_search_service import VectorSearchService


# ==============================================================================
# Helper Fixtures
# ==============================================================================


@pytest.fixture
def mock_chunks() -> list[VectorSearchResult]:
    """Sample ranked knowledge chunks for testing."""
    chunk1 = KnowledgeChunk(
        id="chunk_001",
        templeId="temple_somnath",
        documentId="doc_somnath_darshan",
        title="Somnath Darshan Timings",
        source="somnath_timings.pdf",
        category="timings",
        content="The temple opens for devotees daily at 6:00 AM and closes at 10:00 PM. Morning Aarti is held at 7:00 AM.",
        chunkIndex=0,
        metadata={"url": "https://somnath.org/darshan-timings"},
    )
    chunk2 = KnowledgeChunk(
        id="chunk_002",
        templeId="temple_somnath",
        documentId="doc_somnath_darshan",
        title="Somnath Evening Aarti",
        source="somnath_timings.pdf",
        category="rituals",
        content="Evening Aarti takes place at 7:00 PM followed by the Sound and Light Show 'Jay Somnath' at 8:00 PM.",
        chunkIndex=1,
        metadata={"url": "https://somnath.org/darshan-timings"},
    )
    return [
        VectorSearchResult(chunk=chunk1, score=0.89),
        VectorSearchResult(chunk=chunk2, score=0.78),
    ]


@pytest.fixture
def test_rag_service(mock_chunks: list[VectorSearchResult]) -> RAGService:
    """Fixture providing RAGService wired to mocked VectorSearch and MockLLMProvider."""
    mock_vector = MagicMock(spec=VectorSearchService)
    mock_vector.search = AsyncMock(return_value=mock_chunks)

    mock_llm = LLMService(
        provider=MockLLMProvider(
            fixed_response="According to temple records, Morning Aarti is held at 7:00 AM daily."
        )
    )
    return RAGService(vector_service=mock_vector, llm_svc=mock_llm)


# ==============================================================================
# 1. Retrieval & Multi-Tenant Isolation Tests
# ==============================================================================


class TestRAGRetrieval:
    """Tests for vector retrieval filtering, scoping, and parameter validation."""

    @pytest.mark.anyio
    async def test_retrieval_filtered_by_temple_id(self, test_rag_service: RAGService) -> None:
        """Retrieval must strictly query vector search with the provided templeId."""
        response = await test_rag_service.answer_question(
            temple_id="temple_somnath",
            question="What time is Morning Aarti?",
        )

        assert response.has_relevant_context is True
        assert response.temple_id == "temple_somnath"
        assert len(response.sources) == 2

        # Verify search call arguments on vector service
        test_rag_service._vector_service.search.assert_called_once_with(
            temple_id="temple_somnath",
            query="What time is Morning Aarti?",
            top_k=5,
            category=None,
            min_score=0.4,
        )

    @pytest.mark.anyio
    async def test_retrieval_custom_top_k_and_threshold(self) -> None:
        """Configurable top_k, similarity_threshold, and category filters are passed to vector service."""
        mock_vector = MagicMock(spec=VectorSearchService)
        mock_vector.search = AsyncMock(return_value=[])
        mock_llm = LLMService(provider=MockLLMProvider())

        rag = RAGService(vector_service=mock_vector, llm_svc=mock_llm)

        await rag.answer_question(
            temple_id="temple_tirupati",
            question="Special entry darshan details",
            top_k=3,
            similarity_threshold=0.75,
            category="darshan",
        )

        mock_vector.search.assert_called_once_with(
            temple_id="temple_tirupati",
            query="Special entry darshan details",
            top_k=3,
            category="darshan",
            min_score=0.75,
        )

    @pytest.mark.anyio
    async def test_retrieval_input_validation(self, test_rag_service: RAGService) -> None:
        """Validation errors are raised for empty templeId or query."""
        with pytest.raises(BadRequestException):
            await test_rag_service.answer_question(temple_id="", question="When does the temple open?")

        with pytest.raises(BadRequestException):
            await test_rag_service.answer_question(temple_id="temple_somnath", question="   ")


# ==============================================================================
# 2. Context Generation Tests
# ==============================================================================


class TestRAGContextGeneration:
    """Tests for synthesizing raw knowledge chunks into formatted context blocks."""

    def test_build_context_and_citations_structure(
        self, test_rag_service: RAGService, mock_chunks: list[VectorSearchResult]
    ) -> None:
        """Context string includes title, category, origin, and chunk content."""
        context_str, citations = test_rag_service.build_context_and_citations(mock_chunks)

        # Context string assertions
        assert "Source [1]: Somnath Darshan Timings" in context_str
        assert "Category: timings" in context_str
        assert "Origin: somnath_timings.pdf" in context_str
        assert "Morning Aarti is held at 7:00 AM" in context_str
        assert "Source [2]: Somnath Evening Aarti" in context_str

        # Citations list assertions
        assert len(citations) == 2
        cit1 = citations[0]
        assert cit1.title == "Somnath Darshan Timings"
        assert cit1.source == "somnath_timings.pdf"
        assert cit1.source_url == "https://somnath.org/darshan-timings"
        assert cit1.score == 0.89
        assert cit1.document_id == "doc_somnath_darshan"
        assert "The temple opens for devotees daily" in cit1.content_snippet

    def test_build_context_empty_results(self, test_rag_service: RAGService) -> None:
        """Empty vector search results produce empty context and citations."""
        context_str, citations = test_rag_service.build_context_and_citations([])
        assert context_str == ""
        assert citations == []


# ==============================================================================
# 3. No-Context Guardrail Behavior Tests
# ==============================================================================


class TestRAGNoContextBehavior:
    """Tests for safe guardrails when no relevant knowledge records match."""

    @pytest.mark.anyio
    async def test_no_context_returns_standard_fallback(self) -> None:
        """When vector search returns no matching chunks, returns safe fallback without hallucination."""
        mock_vector = MagicMock(spec=VectorSearchService)
        mock_vector.search = AsyncMock(return_value=[])

        mock_llm_provider = MagicMock(spec=BaseLLMProvider)
        mock_llm_svc = LLMService(provider=mock_llm_provider)

        rag = RAGService(vector_service=mock_vector, llm_svc=mock_llm_svc)

        response: RAGAnswerResponse = await rag.answer_question(
            temple_id="temple_somnath",
            question="What is the price of a helicopter ticket to Mars?",
        )

        assert response.has_relevant_context is False
        assert response.answer == NO_CONTEXT_FALLBACK_ANSWER
        assert response.sources == []
        assert response.top_score is None
        assert response.metadata["chunksRetrieved"] == 0

        # LLM completion must NOT be called when no context exists (cost & safety optimization)
        mock_llm_provider.generate_response.assert_not_called()


# ==============================================================================
# 4. Prompt Construction Tests
# ==============================================================================


class TestRAGPromptConstruction:
    """Tests for system and user prompt formulation."""

    def test_system_prompt_strictly_forbids_hallucination(self, test_rag_service: RAGService) -> None:
        """System prompt contains strict grounding and anti-hallucination constraints."""
        system_prompt = test_rag_service.build_system_prompt()

        assert "ONLY answer using the verified facts in the TEMPLE CONTEXT" in system_prompt
        assert "Do NOT extrapolate, speculate, or invent" in system_prompt
        assert "information is not available in the current temple records" in system_prompt
        assert "devotional tone" in system_prompt

    def test_user_prompt_combines_context_and_question(self, test_rag_service: RAGService) -> None:
        """User prompt embeds TEMPLE CONTEXT and DEVOTEE QUESTION in clean template."""
        context = "Source [1]: Morning Darshan at 6:00 AM."
        question = "What time does Darshan begin?"

        user_prompt = test_rag_service.build_user_prompt(question=question, context=context)

        assert "TEMPLE CONTEXT:" in user_prompt
        assert "Source [1]: Morning Darshan at 6:00 AM." in user_prompt
        assert "DEVOTEE QUESTION:\nWhat time does Darshan begin?" in user_prompt
        assert "ANSWER:" in user_prompt

    def test_user_prompt_includes_conversation_history(self, test_rag_service: RAGService) -> None:
        """User prompt embeds RECENT CONVERSATION HISTORY when dialogue history is provided."""
        context = "Source [1]: Special laddu prasadam is available at counter 4."
        question = "What is the price?"
        history = [
            {"role": "user", "content": "Where can I get prasadam?"},
            {"role": "assistant", "content": "Special laddu prasadam is available at counter 4."},
        ]

        user_prompt = test_rag_service.build_user_prompt(
            question=question,
            context=context,
            conversation_history=history,
        )

        assert "TEMPLE CONTEXT:" in user_prompt
        assert "RECENT CONVERSATION HISTORY:" in user_prompt
        assert "Devotee: Where can I get prasadam?" in user_prompt
        assert "Assistant: Special laddu prasadam is available at counter 4." in user_prompt
        assert "DEVOTEE QUESTION:\nWhat is the price?" in user_prompt
        assert "ANSWER:" in user_prompt


# ==============================================================================
# 5. LLM Provider & Swappable Interface Tests
# ==============================================================================


class TestLLMProviders:
    """Tests for BaseLLMProvider implementations and dynamic provider swapping."""

    @pytest.mark.anyio
    async def test_mock_llm_provider(self) -> None:
        """MockLLMProvider generates completion and tracks system/user prompts."""
        mock = MockLLMProvider()
        resp: LLMResponse = await mock.generate_response(
            system_prompt="You are a temple guide.",
            user_prompt="Explain the history.",
        )

        assert resp.content != ""
        assert resp.model == "mock-temple-llm"
        assert mock.last_system_prompt == "You are a temple guide."
        assert mock.last_user_prompt == "Explain the history."

    def test_gemini_provider_requires_api_key_when_instantiated_directly(self) -> None:
        """GeminiLLMProvider raises error if initialized without API key."""
        with pytest.raises(AppException) as exc_info:
            GeminiLLMProvider(api_key="")
        assert exc_info.value.error_code == "CONFIG_ERROR"

    def test_openai_provider_requires_api_key_when_instantiated_directly(self) -> None:
        """OpenAILLMProvider raises error if initialized without API key."""
        with pytest.raises(AppException) as exc_info:
            OpenAILLMProvider(api_key="", base_url="https://api.openai.com/v1")
        assert exc_info.value.error_code == "CONFIG_ERROR"

    @pytest.mark.anyio
    async def test_swappable_llm_provider_in_rag_service(
        self, test_rag_service: RAGService
    ) -> None:
        """LLM provider can be dynamically swapped without modifying RAGService."""
        custom_provider = MockLLMProvider(fixed_response="Custom swapped response from alternative model.")
        test_rag_service._llm_service.set_provider(custom_provider)

        response = await test_rag_service.answer_question(
            temple_id="temple_somnath",
            question="Tell me about Aarti.",
        )

        assert response.answer == "Custom swapped response from alternative model."
        assert response.has_relevant_context is True


# ==============================================================================
# 6. API Endpoint Integration Tests
# ==============================================================================


class TestRAGApiEndpoint:
    """Tests for POST /api/v1/rag/query endpoint."""

    def test_api_rag_query_success(self, client) -> None:
        """Endpoint accepts valid query and returns grounded response structure."""
        payload = {
            "templeId": "temple_somnath",
            "question": "What are the darshan timings?",
            "topK": 3,
            "similarityThreshold": 0.5,
        }
        response = client.post("/api/v1/rag/query", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "answer" in data
        assert data["templeId"] == "temple_somnath"
        assert data["question"] == "What are the darshan timings?"
        assert "sources" in data
        assert "hasRelevantContext" in data
        assert "latencyMs" in data
        assert "metadata" in data

    def test_api_rag_query_missing_fields_validation(self, client) -> None:
        """Endpoint validates required fields and rejects empty request."""
        # Missing question
        response = client.post("/api/v1/rag/query", json={"templeId": "temple_1"})
        assert response.status_code == 422

        # Missing templeId
        response = client.post("/api/v1/rag/query", json={"question": "When does it open?"})
        assert response.status_code == 422

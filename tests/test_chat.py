"""API tests for the public Chatbot endpoint POST /api/chat."""

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppException
from app.core.rate_limiter import InMemorySlidingWindowRateLimiter, RateLimiter
from app.models.rag import RAGAnswerResponse, RAGSourceCitation
from app.services.rag_service import rag_service


# ==============================================================================
# Public Chat API Tests
# ==============================================================================


def test_post_api_chat_success(client: TestClient) -> None:
    """POST /api/chat returns grounded response with answer, sources, and templeId."""
    payload = {
        "templeId": "temple-001",
        "message": "What time is the morning pooja?",
    }

    mock_rag_response = RAGAnswerResponse(
        answer="Morning pooja commences daily at 6:00 AM.",
        templeId="temple-001",
        question="What time is the morning pooja?",
        sources=[
            RAGSourceCitation(
                title="Pooja Timings Schedule",
                source="temple_pooja.pdf",
                sourceUrl="https://temple.org/pooja",
                category="rituals",
                chunkIndex=0,
                score=0.885,
                contentSnippet="Morning pooja commences daily at 6:00 AM...",
                documentId="doc_123",
            )
        ],
        hasRelevantContext=True,
        topScore=0.885,
        latencyMs=120.0,
    )

    with patch.object(rag_service, "answer_question", new=AsyncMock(return_value=mock_rag_response)):
        response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["templeId"] == "temple-001"
    assert data["answer"] == "Morning pooja commences daily at 6:00 AM."
    assert data["hasRelevantContext"] is True
    assert len(data["sources"]) == 1

    source = data["sources"][0]
    assert source["title"] == "Pooja Timings Schedule"
    assert source["source"] == "temple_pooja.pdf"
    assert source["url"] == "https://temple.org/pooja"
    assert source["score"] == 0.885

    # Verify rate-limit headers
    assert "x-ratelimit-limit" in response.headers
    assert "x-ratelimit-remaining" in response.headers


def test_post_api_v1_chat_alias(client: TestClient) -> None:
    """POST /api/v1/chat works as versioned alias."""
    payload = {
        "templeId": "somnath-01",
        "message": "When is the evening aarti?",
    }

    mock_rag_response = RAGAnswerResponse(
        answer="Evening aarti is held at 7:00 PM.",
        templeId="somnath-01",
        question="When is the evening aarti?",
        sources=[],
        hasRelevantContext=True,
    )

    with patch.object(rag_service, "answer_question", new=AsyncMock(return_value=mock_rag_response)):
        response = client.post("/api/v1/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["templeId"] == "somnath-01"
    assert data["answer"] == "Evening aarti is held at 7:00 PM."


def test_post_api_chat_validation_missing_temple_id(client: TestClient) -> None:
    """POST /api/chat rejects payload with missing templeId."""
    payload = {
        "message": "What are the timings?",
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code in (400, 422)


def test_post_api_chat_validation_empty_message(client: TestClient) -> None:
    """POST /api/chat rejects empty or whitespace-only messages."""
    payload = {
        "templeId": "temple-001",
        "message": "     ",
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "Message cannot be empty" in str(data)


def test_post_api_chat_validation_invalid_temple_id_format(client: TestClient) -> None:
    """POST /api/chat rejects invalid templeId containing dangerous or invalid characters."""
    payload = {
        "templeId": "temple/../../admin",
        "message": "Hello",
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "Invalid templeId" in str(data)


def test_post_api_chat_rate_limiting(client: TestClient) -> None:
    """Endpoint enforces rate limit and returns 429 Too Many Requests when threshold exceeded."""
    from app.api.endpoints.chat import chat_rate_limiter

    # Configure a temporary strict in-memory rate limiter with limit of 2 requests
    strict_limiter = InMemorySlidingWindowRateLimiter()
    original_limiter = chat_rate_limiter.limiter
    original_rpm = chat_rate_limiter.requests_per_minute

    chat_rate_limiter.limiter = strict_limiter
    chat_rate_limiter.requests_per_minute = 2

    mock_rag_response = RAGAnswerResponse(
        answer="Response",
        templeId="temple-001",
        question="Query",
        sources=[],
    )

    try:
        with patch.object(rag_service, "answer_question", new=AsyncMock(return_value=mock_rag_response)):
            # First request: Allowed
            resp1 = client.post("/api/chat", json={"templeId": "temple-001", "message": "msg 1"})
            assert resp1.status_code == 200

            # Second request: Allowed
            resp2 = client.post("/api/chat", json={"templeId": "temple-001", "message": "msg 2"})
            assert resp2.status_code == 200

            # Third request: Exceeds limit -> 429 Too Many Requests
            resp3 = client.post("/api/chat", json={"templeId": "temple-001", "message": "msg 3"})
            assert resp3.status_code == 429
            assert "Retry-After" in resp3.headers
    finally:
        # Restore rate limiter
        chat_rate_limiter.limiter = original_limiter
        chat_rate_limiter.requests_per_minute = original_rpm


def test_post_api_chat_cors_headers_for_embeddable_widget(client: TestClient) -> None:
    """CORS allows cross-origin requests from external temple websites."""
    headers = {
        "Origin": "https://external-temple-site.org",
        "Access-Control-Request-Method": "POST",
    }
    response = client.options("/api/chat", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://external-temple-site.org"


def test_post_api_chat_error_sanitization(client: TestClient) -> None:
    """Internal exceptions or database errors do not leak sensitive details to client."""
    payload = {
        "templeId": "temple-001",
        "message": "Tell me about pooja",
    }

    # Simulate an unexpected internal database error with sensitive info
    sensitive_internal_error = Exception("Authentication failed on mongodb+srv://admin:SECRET_PASSWORD@cluster.mongodb.net")

    with patch.object(rag_service, "answer_question", new=AsyncMock(side_effect=sensitive_internal_error)):
        response = client.post("/api/chat", json=payload)

    # Must be 500 or standard application error, and must NEVER contain the secret or stack trace
    data = response.json()
    response_text = str(data)

    assert "SECRET_PASSWORD" not in response_text
    assert "mongodb+srv" not in response_text
    assert "Please try again later" in response_text

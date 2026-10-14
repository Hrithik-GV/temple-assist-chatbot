"""Tests for Conversation and Session Support, Multi-Temple Isolation, PII Redaction,
and Configurable Retention.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import BadRequestException, NotFoundException
from app.models.collections import Collections
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.models.rag import RAGAnswerResponse, RAGSourceCitation
from app.services.conversation_service import ConversationService, conversation_service
from app.services.rag_service import rag_service
from app.utils.helpers import get_utc_now
from app.utils.pii import anonymize_ip, sanitize_session_metadata, scrub_pii


# ==============================================================================
# 1. PII Sanitization Tests (Requirement 4)
# ==============================================================================


def test_scrub_pii_emails() -> None:
    """Scrub PII replaces email addresses with redaction tag."""
    text = "Please send darshan receipt to devotee.sharma@example.com or admin@temple.org"
    cleaned = scrub_pii(text)
    assert "devotee.sharma@example.com" not in cleaned
    assert "admin@temple.org" not in cleaned
    assert "[EMAIL_REDACTED]" in cleaned


def test_scrub_pii_phone_numbers() -> None:
    """Scrub PII replaces Indian and international phone numbers."""
    # Indian mobile
    text1 = "My mobile number is +91 9876543210 for pooja confirmation."
    cleaned1 = scrub_pii(text1)
    assert "9876543210" not in cleaned1
    assert "[PHONE_REDACTED]" in cleaned1

    # US phone format
    text2 = "Call me back at (555) 123-4567 please."
    cleaned2 = scrub_pii(text2)
    assert "123-4567" not in cleaned2
    assert "[PHONE_REDACTED]" in cleaned2


def test_scrub_pii_credit_cards_and_national_ids() -> None:
    """Scrub PII replaces credit cards and national identifiers (Aadhaar, SSN)."""
    # Credit card
    text_card = "I paid donation using card 4111 2222 3333 4444 yesterday."
    cleaned_card = scrub_pii(text_card)
    assert "4111 2222 3333 4444" not in cleaned_card
    assert "[CARD_REDACTED]" in cleaned_card

    # Indian Aadhaar
    text_aadhaar = "My Aadhaar is 1234 5678 9012 for VIP entry."
    cleaned_aadhaar = scrub_pii(text_aadhaar)
    assert "1234 5678 9012" not in cleaned_aadhaar
    assert "[ID_REDACTED]" in cleaned_aadhaar

    # US SSN
    text_ssn = "Tax id is 123-45-6789."
    cleaned_ssn = scrub_pii(text_ssn)
    assert "123-45-6789" not in cleaned_ssn
    assert "[ID_REDACTED]" in cleaned_ssn


def test_sanitize_session_metadata_removes_auth_and_anonymizes_ip() -> None:
    """Session metadata sanitization strips tokens and anonymizes IP addresses."""
    raw_meta = {
        "ip": "203.0.113.195",
        "authorization": "Bearer secret_token_xyz",
        "cookie": "session=sensitive_cookie",
        "userAgent": "Mozilla/5.0",
        "notes": "Devotee email: test@example.com",
    }
    sanitized = sanitize_session_metadata(raw_meta)

    assert "authorization" not in sanitized
    assert "cookie" not in sanitized
    assert sanitized["ip"] == "203.0.113.0"  # Last octet zeroed
    assert sanitized["userAgent"] == "Mozilla/5.0"
    assert "test@example.com" not in sanitized["notes"]
    assert "[EMAIL_REDACTED]" in sanitized["notes"]


# ==============================================================================
# 2. Conversation & Session ID Generation Tests (Requirement 1 & 2)
# ==============================================================================


def test_generate_conversation_and_session_ids() -> None:
    """Conversation and session IDs have unique, prefixed identifiers."""
    conv_id1 = ConversationService.generate_conversation_id()
    conv_id2 = ConversationService.generate_conversation_id()
    sess_id1 = ConversationService.generate_session_id()

    assert conv_id1.startswith("conv_")
    assert conv_id2.startswith("conv_")
    assert sess_id1.startswith("sess_")
    assert conv_id1 != conv_id2
    assert len(conv_id1) >= 15


def test_conversation_retention_expiry_calculation() -> None:
    """Retention expiry calculates correct UTC future timestamp based on days."""
    now = get_utc_now()
    expiry_30 = ConversationService.calculate_expiry(days=30)
    assert expiry_30 is not None
    assert (expiry_30 - now).days in (29, 30)

    # Indefinite retention (days=0)
    expiry_0 = ConversationService.calculate_expiry(days=0)
    assert expiry_0 is None


# ==============================================================================
# 3. Cross-Temple Isolation Tests (Requirements 8, 9, 10)
# ==============================================================================


@pytest.mark.anyio
async def test_cross_temple_conversation_access_is_strictly_blocked() -> None:
    """A conversation created under Temple A CANNOT be accessed by Temple B."""
    service = ConversationService()

    # Conversation belongs to temple_alpha
    temple_alpha_id = "temple-alpha"
    temple_beta_id = "temple-beta"
    target_conv_id = "conv_alpha_secret_999"

    mock_conv_col = MagicMock()

    # find_one returns None when scoped to temple-beta, but returns record when queried without templeId
    async def mock_find_one(query: dict) -> dict | None:
        if query.get("templeId") == temple_alpha_id:
            return {
                "_id": target_conv_id,
                "conversationId": target_conv_id,
                "templeId": temple_alpha_id,
                "sessionId": "sess_alpha_1",
            }
        elif query.get("templeId") == temple_beta_id:
            return None
        # Unscoped query (security cross-temple check)
        elif "$or" in query:
            return {
                "_id": target_conv_id,
                "conversationId": target_conv_id,
                "templeId": temple_alpha_id,
                "sessionId": "sess_alpha_1",
            }
        return None

    mock_conv_col.find_one = AsyncMock(side_effect=mock_find_one)

    with patch.object(ConversationService, "conversations_collection", new=mock_conv_col):
        # 1. Temple Alpha can access its own conversation
        conv_alpha = await service.get_or_create_conversation(
            temple_id=temple_alpha_id,
            conversation_id=target_conv_id,
        )
        assert conv_alpha["templeId"] == temple_alpha_id
        assert conv_alpha["conversationId"] == target_conv_id

        # 2. Temple Beta attempting to access Temple Alpha's conversation ID MUST be rejected with NotFoundException
        with pytest.raises(NotFoundException) as exc_info:
            await service.get_or_create_conversation(
                temple_id=temple_beta_id,
                conversation_id=target_conv_id,
            )

        assert "not found for temple 'temple-beta'" in str(exc_info.value)


@pytest.mark.anyio
async def test_cross_temple_message_history_isolation() -> None:
    """Message history queries are strictly scoped to templeId, preventing cross-tenant leakage."""
    service = ConversationService()

    mock_msg_col = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)

    # When queried with temple-beta, cursor returns empty list
    async def mock_to_list(length: int) -> list:
        # Check that find was called with templeId
        return []

    mock_cursor.to_list = AsyncMock(side_effect=mock_to_list)
    mock_msg_col.find = MagicMock(return_value=mock_cursor)

    with patch.object(ConversationService, "messages_collection", new=mock_msg_col):
        history = await service.load_recent_history(
            temple_id="temple-beta",
            conversation_id="conv_alpha_secret_999",
        )

        assert history == []
        mock_msg_col.find.assert_called_once_with(
            {"templeId": "temple-beta", "conversationId": "conv_alpha_secret_999"}
        )


def test_conversations_separate_from_knowledge_base() -> None:
    """Conversations and messages collections are completely separate from knowledge base."""
    assert Collections.CONVERSATIONS == "conversations"
    assert Collections.MESSAGES == "messages"
    assert Collections.KNOWLEDGE_CHUNKS == "knowledge_chunks"
    assert Collections.KNOWLEDGE_DOCUMENTS == "knowledge_documents"
    assert Collections.CONVERSATIONS != Collections.KNOWLEDGE_CHUNKS
    assert Collections.MESSAGES != Collections.KNOWLEDGE_CHUNKS


# ==============================================================================
# 4. Message Persistence & History Loading Tests (Requirements 3, 5, 7)
# ==============================================================================


@pytest.mark.anyio
async def test_store_user_message_scrubs_pii_and_sets_retention() -> None:
    """User message storing scrubs PII and stores in messages collection."""
    service = ConversationService()

    mock_msg_col = MagicMock()
    mock_msg_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="msg_obj_123"))

    mock_conv_col = MagicMock()
    mock_conv_col.update_one = AsyncMock()

    with patch.object(ConversationService, "messages_collection", new=mock_msg_col), \
         patch.object(ConversationService, "conversations_collection", new=mock_conv_col):

        stored = await service.store_user_message(
            temple_id="somnath-01",
            conversation_id="conv_12345",
            content="My phone is +91 9988776655 and email is devotee@somnath.org",
        )

        assert stored["templeId"] == "somnath-01"
        assert stored["conversationId"] == "conv_12345"
        assert stored["role"] == "user"
        # Verify PII redacted
        assert "+91 9988776655" not in stored["content"]
        assert "devotee@somnath.org" not in stored["content"]
        assert "[PHONE_REDACTED]" in stored["content"]
        assert "[EMAIL_REDACTED]" in stored["content"]
        assert stored["expiresAt"] is not None

        # Verify message count incremented on conversation
        mock_conv_col.update_one.assert_called_once()


@pytest.mark.anyio
async def test_store_assistant_message_preserves_sources() -> None:
    """Assistant message storing preserves sources and role."""
    service = ConversationService()

    mock_msg_col = MagicMock()
    mock_msg_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="msg_obj_456"))

    mock_conv_col = MagicMock()
    mock_conv_col.update_one = AsyncMock()

    sources = [{"title": "Aarti Timings", "source": "schedule.pdf", "score": 0.95}]

    with patch.object(ConversationService, "messages_collection", new=mock_msg_col), \
         patch.object(ConversationService, "conversations_collection", new=mock_conv_col):

        stored = await service.store_assistant_message(
            temple_id="somnath-01",
            conversation_id="conv_12345",
            content="Evening aarti is at 7:00 PM.",
            sources=sources,
        )

        assert stored["role"] == "assistant"
        assert stored["content"] == "Evening aarti is at 7:00 PM."
        assert len(stored["sources"]) == 1
        assert stored["sources"][0]["title"] == "Aarti Timings"


@pytest.mark.anyio
async def test_load_recent_history_respects_max_turns() -> None:
    """load_recent_history retrieves messages bounded by max_turns in chronological order."""
    service = ConversationService()

    # Simulate 6 messages in DB (3 turns)
    db_messages = [
        {"role": "user", "content": "Question 3", "createdAt": datetime(2026, 1, 1, 10, 5)},
        {"role": "assistant", "content": "Answer 3", "createdAt": datetime(2026, 1, 1, 10, 6)},
        {"role": "user", "content": "Question 2", "createdAt": datetime(2026, 1, 1, 10, 3)},
        {"role": "assistant", "content": "Answer 2", "createdAt": datetime(2026, 1, 1, 10, 4)},
    ]

    mock_msg_col = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    # DESCENDING sort in DB returns newest first
    mock_cursor.to_list = AsyncMock(return_value=db_messages)
    mock_msg_col.find = MagicMock(return_value=mock_cursor)

    with patch.object(ConversationService, "messages_collection", new=mock_msg_col):
        # Request 2 turns = 4 messages
        history = await service.load_recent_history(
            temple_id="somnath-01",
            conversation_id="conv_12345",
            max_turns=2,
        )

        assert len(history) == 4
        # Chronological reversal check: oldest of the batch comes first
        assert history[0]["content"] == "Answer 2"
        assert history[1]["content"] == "Question 2"


# ==============================================================================
# 5. History Retention Purge Tests (Requirement 5)
# ==============================================================================


@pytest.mark.anyio
async def test_cleanup_expired_history_purges_only_expired_records() -> None:
    """Retention cleanup purges expired records scoped to temple."""
    service = ConversationService()

    mock_conv_col = MagicMock()
    mock_conv_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=3))

    mock_msg_col = MagicMock()
    mock_msg_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=12))

    with patch.object(ConversationService, "conversations_collection", new=mock_conv_col), \
         patch.object(ConversationService, "messages_collection", new=mock_msg_col):

        result = await service.cleanup_expired_history(temple_id="tirupati-01")

        assert result["conversationsPurged"] == 3
        assert result["messagesPurged"] == 12

        # Verify filter checked expiresAt <= now
        call_args = mock_conv_col.delete_many.call_args[0][0]
        assert "expiresAt" in call_args
        assert call_args["templeId"] == "tirupati-01"


# ==============================================================================
# 6. Public Chat API Multi-Turn & Isolation Tests (Requirements 6, 9, 10)
# ==============================================================================


def test_api_chat_creates_and_returns_conversation_id(client: TestClient) -> None:
    """POST /api/chat auto-creates and returns conversationId when none provided."""
    payload = {
        "templeId": "tirupati-01",
        "message": "When is the morning darshan?",
    }

    mock_rag_response = RAGAnswerResponse(
        answer="Morning darshan begins at 6:00 AM.",
        templeId="tirupati-01",
        question="When is the morning darshan?",
        sources=[],
        hasRelevantContext=True,
    )

    with patch.object(rag_service, "answer_question", new=AsyncMock(return_value=mock_rag_response)):
        response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["templeId"] == "tirupati-01"
    assert "conversationId" in data
    assert data["conversationId"] is not None
    assert len(data["conversationId"]) > 5


def test_api_chat_accepts_existing_conversation_id(client: TestClient) -> None:
    """POST /api/chat accepts conversationId and passes prior dialogue history to RAG."""
    conv_id = "conv_test_session_888"

    mock_history = [
        {"role": "user", "content": "What are the timings?"},
        {"role": "assistant", "content": "6 AM to 9 PM."},
    ]

    mock_rag_response = RAGAnswerResponse(
        answer="On festival days, special darshan starts at 5:00 AM.",
        templeId="tirupati-01",
        question="What about festival days?",
        sources=[],
        hasRelevantContext=True,
    )

    with patch.object(conversation_service, "get_or_create_conversation", new=AsyncMock(return_value={"_id": conv_id, "conversationId": conv_id, "sessionId": "sess_1"})), \
         patch.object(conversation_service, "load_recent_history", new=AsyncMock(return_value=mock_history)), \
         patch.object(conversation_service, "store_user_message", new=AsyncMock()), \
         patch.object(conversation_service, "store_assistant_message", new=AsyncMock()), \
         patch.object(rag_service, "answer_question", new=AsyncMock(return_value=mock_rag_response)) as mock_rag_call:

        response = client.post(
            "/api/chat",
            json={
                "templeId": "tirupati-01",
                "message": "What about festival days?",
                "conversationId": conv_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["conversationId"] == conv_id

        # Verify that RAG was called with the conversation_history
        mock_rag_call.assert_called_once_with(
            temple_id="tirupati-01",
            question="What about festival days?",
            conversation_history=mock_history,
        )


def test_api_chat_cross_temple_conversation_rejected(client: TestClient) -> None:
    """POST /api/chat rejects attempts to access Temple A's conversation with Temple B's ID."""
    foreign_conv_id = "conv_temple_alpha_private"

    # Simulate cross-temple rejection in conversation_service
    rejection_error = NotFoundException(f"Conversation '{foreign_conv_id}' not found for temple 'temple-beta'.")

    with patch.object(conversation_service, "get_or_create_conversation", new=AsyncMock(side_effect=rejection_error)):
        response = client.post(
            "/api/chat",
            json={
                "templeId": "temple-beta",
                "message": "What was previously discussed?",
                "conversationId": foreign_conv_id,
            },
        )

    # Must be 404 Not Found and sanitized
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert "not found for temple 'temple-beta'" in str(data)

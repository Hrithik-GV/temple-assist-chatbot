"""Tests for MongoDB models, connection manager, database service, and multi-temple scoping."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pydantic import ValidationError
from pymongo.errors import ConnectionFailure

from app.core.database import MongoDBManager, get_db, mongodb
from app.core.errors import ServiceUnavailableException
from app.models.admin import Admin, AdminRole
from app.models.collections import Collections
from app.models.conversation import Conversation
from app.models.health import HealthStatus
from app.models.knowledge import (
    DocumentSourceType,
    DocumentStatus,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.models.message import Message, MessageRole
from app.models.temple import Temple, TempleLocation, TempleTimings
from app.services.database_service import DatabaseService


# ==============================================================================
# 1. Multi-Temple Data Model Tests
# ==============================================================================


def test_temple_model_instantiation() -> None:
    """Verify Temple model creation and serialization."""
    temple = Temple(
        name="Brihadeeswarar Temple",
        slug="thanjavur-brihadeeswarar",
        deity="Lord Shiva",
        location=TempleLocation(
            address="Membalam Rd",
            city="Thanjavur",
            state="Tamil Nadu",
            country="India",
        ),
        timings=TempleTimings(
            morning_hours="06:00 - 12:30",
            evening_hours="16:00 - 20:30",
        ),
        languages=["en", "ta"],
    )
    assert temple.name == "Brihadeeswarar Temple"
    assert temple.slug == "thanjavur-brihadeeswarar"
    assert temple.is_active is True
    assert temple.location is not None and temple.location.city == "Thanjavur"

    mongo_data = temple.to_mongo_dict()
    assert mongo_data["slug"] == "thanjavur-brihadeeswarar"
    assert mongo_data["isActive"] is True


def test_knowledge_document_requires_temple_id() -> None:
    """Verify that KnowledgeDocument strictly requires templeId for multi-tenancy."""
    # Attempt creation without templeId should fail validation
    with pytest.raises(ValidationError):
        KnowledgeDocument(title="Temple History")

    # Creation with templeId succeeds
    doc = KnowledgeDocument(
        templeId="temple_101",
        title="Temple History & Legends",
        sourceType=DocumentSourceType.WEBSITE,
        sourceUrl="https://temple.example.org/history",
        rawContent="Historical accounts of the temple...",
        status=DocumentStatus.PENDING,
    )
    assert doc.temple_id == "temple_101"
    assert doc.templeId == "temple_101"
    assert doc.source_type == DocumentSourceType.WEBSITE

    mongo_dict = doc.to_mongo_dict()
    assert mongo_dict["templeId"] == "temple_101"
    assert mongo_dict["sourceType"] == "website"


def test_knowledge_chunk_requires_temple_id_and_document_id() -> None:
    """Verify that KnowledgeChunk requires templeId and documentId."""
    # Missing templeId and documentId
    with pytest.raises(ValidationError):
        KnowledgeChunk(content="Some chunk text")

    # Valid chunk
    chunk = KnowledgeChunk(
        templeId="temple_101",
        documentId="doc_999",
        chunkIndex=0,
        content="Segment describing morning abhishekham ritual.",
        tokenCount=45,
    )
    assert chunk.temple_id == "temple_101"
    assert chunk.templeId == "temple_101"
    assert chunk.document_id == "doc_999"
    assert chunk.chunk_index == 0

    mongo_dict = chunk.to_mongo_dict()
    assert mongo_dict["templeId"] == "temple_101"
    assert mongo_dict["documentId"] == "doc_999"
    assert mongo_dict["chunkIndex"] == 0


def test_admin_model_multi_tenancy() -> None:
    """Verify Admin supports both superadmin (None templeId) and temple-scoped admins."""
    # Superadmin
    superadmin = Admin(
        email="super@templeplatform.org",
        username="superadmin",
        role=AdminRole.SUPERADMIN,
    )
    assert superadmin.temple_id is None
    assert superadmin.templeId is None
    assert superadmin.role == AdminRole.SUPERADMIN

    # Temple-scoped admin
    temple_admin = Admin(
        email="admin@tirupati.org",
        username="tirupati_admin",
        templeId="temple_tirupati",
        role=AdminRole.TEMPLE_ADMIN,
    )
    assert temple_admin.temple_id == "temple_tirupati"
    assert temple_admin.templeId == "temple_tirupati"
    assert temple_admin.role == AdminRole.TEMPLE_ADMIN


def test_conversation_model_requires_temple_id() -> None:
    """Verify that Conversation is strictly scoped by templeId."""
    with pytest.raises(ValidationError):
        Conversation(sessionId="sess_123")

    conv = Conversation(
        templeId="temple_101",
        sessionId="sess_123",
        userLanguage="te",
    )
    assert conv.temple_id == "temple_101"
    assert conv.templeId == "temple_101"
    assert conv.session_id == "sess_123"
    assert conv.is_active is True

    mongo_dict = conv.to_mongo_dict()
    assert mongo_dict["templeId"] == "temple_101"
    assert mongo_dict["sessionId"] == "sess_123"


def test_message_model_requires_temple_id() -> None:
    """Verify that Message is strictly scoped by templeId and conversationId."""
    with pytest.raises(ValidationError):
        Message(content="Hello", conversationId="conv_1")

    msg = Message(
        templeId="temple_101",
        conversationId="conv_1",
        role=MessageRole.USER,
        content="What are the morning darshan timings?",
    )
    assert msg.temple_id == "temple_101"
    assert msg.templeId == "temple_101"
    assert msg.conversation_id == "conv_1"
    assert msg.role == MessageRole.USER

    mongo_dict = msg.to_mongo_dict()
    assert mongo_dict["templeId"] == "temple_101"
    assert mongo_dict["conversationId"] == "conv_1"


# ==============================================================================
# 2. Database Connection Manager Tests
# ==============================================================================


@pytest.mark.anyio
async def test_mongo_manager_uninitialized_state() -> None:
    """Verify behavior when database manager has no active connection."""
    mgr = MongoDBManager()
    assert mgr.is_connected is False

    # Calling get_database when uninitialized raises ServiceUnavailableException
    with pytest.raises(ServiceUnavailableException):
        mgr.get_database()

    with pytest.raises(ServiceUnavailableException):
        mgr.get_collection("temples")

    # ping returns False
    assert await mgr.ping() is False

    # check_health returns UNHEALTHY
    health = await mgr.check_health()
    assert health.status == HealthStatus.UNHEALTHY
    assert "not initialized" in health.details


@pytest.mark.anyio
async def test_mongo_manager_check_health_healthy() -> None:
    """Verify health check returns HEALTHY when ping succeeds."""
    mgr = MongoDBManager()
    mgr.client = MagicMock()
    mgr.db = MagicMock()
    mgr.db.command = AsyncMock(return_value={"ok": 1.0})

    health = await mgr.check_health()
    assert health.status == HealthStatus.HEALTHY
    assert "Connected to MongoDB" in health.details


@pytest.mark.anyio
async def test_mongo_manager_check_health_ping_failure() -> None:
    """Verify health check returns UNHEALTHY when ping fails."""
    mgr = MongoDBManager()
    mgr.client = MagicMock()
    mgr.db = MagicMock()
    mgr.db.command = AsyncMock(return_value={"ok": 0.0})

    health = await mgr.check_health()
    assert health.status == HealthStatus.UNHEALTHY


@pytest.mark.anyio
async def test_mongo_manager_check_health_ping_exception() -> None:
    """Verify health check handles network exceptions gracefully."""
    mgr = MongoDBManager()
    mgr.client = MagicMock()
    mgr.db = MagicMock()
    mgr.db.command = AsyncMock(side_effect=ConnectionFailure("Connection reset by peer"))

    health = await mgr.check_health()
    assert health.status == HealthStatus.UNHEALTHY
    assert "Connection reset" in health.details


@pytest.mark.anyio
async def test_mongo_manager_disconnect() -> None:
    """Verify disconnect closes client and resets state."""
    mgr = MongoDBManager()
    mock_client = MagicMock()
    mgr.client = mock_client
    mgr.db = MagicMock()
    mgr._is_connected = True

    await mgr.disconnect()
    mock_client.close.assert_called_once()
    assert mgr.client is None
    assert mgr.db is None
    assert mgr.is_connected is False


# ==============================================================================
# 3. Database Service Tests
# ==============================================================================


@pytest.mark.anyio
async def test_database_service_collection_routing() -> None:
    """Verify DatabaseService collection properties route to correct collection names."""
    service = DatabaseService()
    mock_db = MagicMock()
    service._db_manager = MagicMock()
    service._db_manager.get_collection = MagicMock(side_effect=lambda name: f"col_{name}")

    assert service.temples_collection == f"col_{Collections.TEMPLES}"
    assert service.knowledge_documents_collection == f"col_{Collections.KNOWLEDGE_DOCUMENTS}"
    assert service.knowledge_chunks_collection == f"col_{Collections.KNOWLEDGE_CHUNKS}"
    assert service.admins_collection == f"col_{Collections.ADMINS}"
    assert service.conversations_collection == f"col_{Collections.CONVERSATIONS}"
    assert service.messages_collection == f"col_{Collections.MESSAGES}"


@pytest.mark.anyio
async def test_database_service_multi_temple_query_scoping() -> None:
    """Verify repository methods strictly scope document and chunk queries to templeId."""
    service = DatabaseService()

    # Mock knowledge_documents_collection
    mock_doc_col = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[{"title": "Doc 1", "templeId": "t1"}])
    mock_doc_col.find = MagicMock(return_value=mock_cursor)

    with patch.object(DatabaseService, "knowledge_documents_collection", new=mock_doc_col):
        results = await service.get_knowledge_documents_by_temple(temple_id="t1", limit=10)
        assert len(results) == 1
        # Crucial multi-tenant check: ensure query had {"templeId": "t1"}
        mock_doc_col.find.assert_called_once_with({"templeId": "t1"})


@pytest.mark.anyio
async def test_database_service_get_or_create_conversation() -> None:
    """Verify conversation retrieval / creation enforces templeId tenancy."""
    service = DatabaseService()

    mock_conv_col = MagicMock()
    mock_conv_col.find_one = AsyncMock(return_value=None)
    mock_conv_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="new_id_123"))

    with patch.object(DatabaseService, "conversations_collection", new=mock_conv_col):
        conv = await service.get_or_create_conversation(
            temple_id="temple_somnath",
            session_id="client_sess_555",
            user_language="gu",
        )
        assert conv["templeId"] == "temple_somnath"
        assert conv["sessionId"] == "client_sess_555"
        assert conv["userLanguage"] == "gu"
        mock_conv_col.find_one.assert_called_once_with(
            {"templeId": "temple_somnath", "sessionId": "client_sess_555"}
        )

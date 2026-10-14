"""Comprehensive unit and integration tests for Protected Admin Knowledge APIs.

Covers:
1. Uploading documents
2. Listing documents with filtering and pagination
3. Deleting documents and cascading chunk purging
4. Triggering website crawling
5. Viewing crawl status and history
6. Viewing knowledge chunks and document metadata
7. Adding, listing, updating, and deleting FAQs
8. Viewing unanswered devotee questions
9. Chatbot analytics and metrics
10. Strict temple-level multi-tenant authorization (HTTP 403 Forbidden enforcement)
"""

import io
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.admin import AdminRole
from app.models.knowledge import CrawlPageResult, CrawlSummary, DocumentStatus, IngestionResult
from app.services.auth_service import auth_service
from app.services.crawler_service import crawler_service
from app.services.database_service import DatabaseService, database_service
from app.services.embedding_service import embedding_service
from app.services.ingestion_service import ingestion_service
from app.services.vector_search_service import vector_search_service


# ==============================================================================
# Helper Mock Factories
# ==============================================================================


def create_mock_admin(admin_id: str, temple_id: str, role: AdminRole = AdminRole.TEMPLE_ADMIN) -> Dict[str, Any]:
    """Helper to generate admin dict for dependency mocking."""
    return {
        "_id": admin_id,
        "id": admin_id,
        "email": f"{admin_id}@temple.org",
        "username": admin_id,
        "fullName": "Temple Admin",
        "templeId": temple_id,
        "role": role.value if hasattr(role, "value") else str(role),
        "isActive": True,
    }


def make_admin_headers(admin_id: str, temple_id: str, role: str = "temple_admin") -> Dict[str, str]:
    """Generate Authorization Bearer token header."""
    token = create_access_token({"sub": admin_id, "templeId": temple_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. Document Upload & Ingestion Tests
# ==============================================================================


def test_admin_upload_document_success(client: TestClient) -> None:
    """Temple admin can upload a valid document file (.txt) to their temple."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    mock_ingest_res = IngestionResult(
        document_id="doc_upl_123",
        temple_id=temple_id,
        title="Temple History Guide",
        status=DocumentStatus.PROCESSED,
        chunks_created=3,
        is_duplicate=False,
        message="Ingestion completed successfully.",
    )

    file_content = b"The ancient temple was consecrated in the 11th century."
    files = {"file": ("temple_history.txt", io.BytesIO(file_content), "text/plain")}
    data = {"title": "Temple History Guide", "category": "history"}

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(ingestion_service, "ingest_document", new=AsyncMock(return_value=mock_ingest_res)):

        response = client.post(
            f"/api/v1/admin/knowledge/{temple_id}/upload",
            headers=headers,
            files=files,
            data=data,
        )

    assert response.status_code == 201
    res = response.json()
    assert res["success"] is True
    assert res["documentId"] == "doc_upl_123"
    assert res["chunksCreated"] == 3
    assert res["status"] == "processed"
    assert res["isDuplicate"] is False


def test_admin_upload_document_invalid_extension(client: TestClient) -> None:
    """Uploading unsupported file formats (e.g. .exe, .sh) returns 400 Bad Request."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    files = {"file": ("malicious.exe", io.BytesIO(b"binary data"), "application/octet-stream")}

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)):
        response = client.post(
            f"/api/v1/admin/knowledge/{temple_id}/upload",
            headers=headers,
            files=files,
        )

    assert response.status_code == 400
    assert "unsupported file format" in response.json()["error"]["message"].lower()


def test_admin_upload_document_empty_file(client: TestClient) -> None:
    """Uploading an empty file returns 400 Bad Request."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)):
        response = client.post(
            f"/api/v1/admin/knowledge/{temple_id}/upload",
            headers=headers,
            files=files,
        )

    assert response.status_code == 400
    assert "empty" in response.json()["error"]["message"].lower()


def test_admin_upload_document_cross_temple_forbidden(client: TestClient) -> None:
    """CRITICAL: Temple admin for Temple A CANNOT upload documents to Temple B (403 Forbidden)."""
    admin_id = "admin_001"
    temple_a = "temple-001"
    temple_b = "temple-002"
    headers = make_admin_headers(admin_id, temple_a)
    mock_admin = create_mock_admin(admin_id, temple_a)

    files = {"file": ("notes.txt", io.BytesIO(b"Temple notes"), "text/plain")}

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)):
        response = client.post(
            f"/api/v1/admin/knowledge/{temple_b}/upload",
            headers=headers,
            files=files,
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# ==============================================================================
# 2. Document Listing & 3. Document Deletion Tests
# ==============================================================================


def test_admin_list_documents_with_filters(client: TestClient) -> None:
    """Listing documents supports filtering by sourceType, category, and search query."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    mock_docs = [
        {
            "_id": "doc_1",
            "templeId": temple_id,
            "title": "Morning Pooja Guidelines",
            "sourceType": "pdf",
            "category": "rituals",
            "status": "processed",
            "chunkCount": 4,
            "createdAt": "2026-10-14T08:00:00Z",
        },
        {
            "_id": "doc_2",
            "templeId": temple_id,
            "title": "Temple History",
            "sourceType": "docx",
            "category": "history",
            "status": "processed",
            "chunkCount": 8,
            "createdAt": "2026-10-14T09:00:00Z",
        },
    ]

    mock_doc_col = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=mock_docs)
    mock_doc_col.find.return_value = mock_cursor

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "knowledge_documents_collection", new=mock_doc_col):

        response = client.get(
            f"/api/v1/admin/knowledge/{temple_id}/documents?sourceType=pdf&category=rituals&limit=10",
            headers=headers,
        )

    assert response.status_code == 200
    docs = response.json()
    assert len(docs) == 2
    assert docs[0]["_id"] == "doc_1"
    assert docs[0]["sourceType"] == "pdf"


def test_admin_delete_document_and_cascade_chunks(client: TestClient) -> None:
    """Deleting a document purges the document and all associated knowledge chunks."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    mock_doc = {"_id": "doc_to_delete", "templeId": temple_id, "title": "Obsolete Timings"}
    mock_del_result = MagicMock(deleted_count=5)

    mock_doc_col = MagicMock()
    mock_doc_col.find_one = AsyncMock(return_value=mock_doc)
    mock_doc_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

    mock_chunk_col = MagicMock()
    mock_chunk_col.delete_many = AsyncMock(return_value=mock_del_result)

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "knowledge_documents_collection", new=mock_doc_col), \
         patch.object(DatabaseService, "knowledge_chunks_collection", new=mock_chunk_col):

        response = client.delete(
            f"/api/v1/admin/knowledge/{temple_id}/documents/doc_to_delete",
            headers=headers,
        )

    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["chunksPurged"] == 5


def test_admin_delete_document_not_found(client: TestClient) -> None:
    """Deleting a non-existent document returns 404 Not Found."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    mock_doc_col = MagicMock()
    mock_doc_col.find_one = AsyncMock(return_value=None)

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "knowledge_documents_collection", new=mock_doc_col):

        response = client.delete(
            f"/api/v1/admin/knowledge/{temple_id}/documents/non_existent_doc",
            headers=headers,
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# ==============================================================================
# 4. Website Crawl Trigger & 5. Crawl Status Tests
# ==============================================================================


def test_admin_trigger_website_crawl_success(client: TestClient) -> None:
    """Triggering website crawling saves crawl record and returns crawl summary."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    mock_summary = CrawlSummary(
        temple_id=temple_id,
        start_url="https://somnath.org",
        total_pages_visited=4,
        pages_ingested=4,
        pages_skipped=0,
        pages_failed=0,
        total_chunks_created=12,
        duration_seconds=5.2,
        page_results=[
            CrawlPageResult(
                url="https://somnath.org/about",
                title="About Somnath",
                status="ingested",
                chunks_created=3,
            )
        ],
    )

    mock_crawl_col = MagicMock()
    mock_crawl_col.insert_one = AsyncMock()
    mock_crawl_col.update_one = AsyncMock()

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "crawl_jobs_collection", new=mock_crawl_col), \
         patch.object(crawler_service, "crawl_temple_website", new=AsyncMock(return_value=mock_summary)):

        response = client.post(
            f"/api/v1/admin/knowledge/{temple_id}/crawl",
            headers=headers,
            json={
                "startUrl": "https://somnath.org",
                "maxPages": 10,
                "maxDepth": 2,
            },
        )

    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert "crawlId" in res
    assert res["status"] == "completed"
    assert res["totalPagesVisited"] == 4
    assert res["pagesIngested"] == 4
    assert res["totalChunksCreated"] == 12


def test_admin_get_crawl_status_and_history(client: TestClient) -> None:
    """Retrieving crawl status returns latest crawl job and historical runs."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    mock_crawls = [
        {
            "_id": "crawl_1",
            "templeId": temple_id,
            "startUrl": "https://somnath.org",
            "status": "completed",
            "totalPagesVisited": 8,
            "pagesIngested": 7,
            "durationSeconds": 9.4,
            "startedAt": "2026-10-14T10:00:00Z",
        }
    ]

    mock_crawl_col = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=mock_crawls)
    mock_crawl_col.find.return_value = mock_cursor
    mock_crawl_col.count_documents = AsyncMock(return_value=1)

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "crawl_jobs_collection", new=mock_crawl_col):

        response = client.get(
            f"/api/v1/admin/knowledge/{temple_id}/crawl/status",
            headers=headers,
        )

    assert response.status_code == 200
    res = response.json()
    assert res["templeId"] == temple_id
    assert res["totalCrawls"] == 1
    assert res["latestCrawl"]["_id"] == "crawl_1"
    assert res["latestCrawl"]["status"] == "completed"


def test_admin_get_specific_crawl_job_details(client: TestClient) -> None:
    """Retrieving specific crawl job details by crawlId."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    mock_job = {
        "_id": "crawl_xyz",
        "templeId": temple_id,
        "startUrl": "https://somnath.org",
        "status": "completed",
        "totalPagesVisited": 3,
        "pagesIngested": 3,
        "pageResults": [{"url": "https://somnath.org", "status": "ingested"}],
    }

    mock_crawl_col = MagicMock()
    mock_crawl_col.find_one = AsyncMock(return_value=mock_job)

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "crawl_jobs_collection", new=mock_crawl_col):

        response = client.get(
            f"/api/v1/admin/knowledge/{temple_id}/crawl/crawl_xyz",
            headers=headers,
        )

    assert response.status_code == 200
    res = response.json()
    assert res["id"] == "crawl_xyz"
    assert res["status"] == "completed"
    assert len(res["pageResults"]) == 1


# ==============================================================================
# 6. Knowledge Chunks & Document Metadata Tests
# ==============================================================================


def test_admin_get_document_details_with_chunks(client: TestClient) -> None:
    """Viewing document metadata and associated indexed knowledge chunks."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    mock_doc = {
        "_id": "doc_meta_1",
        "templeId": temple_id,
        "title": "Aarti Procedures",
        "sourceType": "pdf",
        "status": "processed",
    }
    mock_chunks = [
        {
            "_id": "chunk_1",
            "documentId": "doc_meta_1",
            "chunkIndex": 0,
            "content": "Aarti takes place at 7:00 PM every evening.",
            "tokenCount": 15,
            "embedding": [0.1, 0.2, 0.3],  # should be stripped
        }
    ]

    mock_doc_col = MagicMock()
    mock_doc_col.find_one = AsyncMock(return_value=mock_doc)

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "knowledge_documents_collection", new=mock_doc_col), \
         patch.object(database_service, "get_knowledge_chunks_by_temple", new=AsyncMock(return_value=mock_chunks)):

        response = client.get(
            f"/api/v1/admin/knowledge/{temple_id}/documents/doc_meta_1",
            headers=headers,
        )

    assert response.status_code == 200
    res = response.json()
    assert res["document"]["_id"] == "doc_meta_1"
    assert res["chunksCount"] == 1
    assert "embedding" not in res["chunks"][0]
    assert res["chunks"][0]["content"] == "Aarti takes place at 7:00 PM every evening."


def test_admin_list_knowledge_chunks(client: TestClient) -> None:
    """Listing knowledge chunks directly across a temple's knowledge base."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    mock_chunks = [
        {"_id": "c1", "templeId": temple_id, "documentId": "d1", "content": "Chunk content one"},
        {"_id": "c2", "templeId": temple_id, "documentId": "d1", "content": "Chunk content two"},
    ]

    mock_chunk_col = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=mock_chunks)
    mock_chunk_col.find.return_value = mock_cursor

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "knowledge_chunks_collection", new=mock_chunk_col):

        response = client.get(
            f"/api/v1/admin/knowledge/{temple_id}/chunks?limit=10",
            headers=headers,
        )

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["_id"] == "c1"


# ==============================================================================
# 7. Adding and Managing FAQs Tests
# ==============================================================================


def test_admin_faq_lifecycle_add_list_update_delete(client: TestClient) -> None:
    """End-to-end management of FAQs: add, list, get, update, and delete."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    # 1. Add FAQ
    mock_ingest_res = MagicMock(
        document_id="faq_doc_999",
        chunks_created=1,
        status=MagicMock(value="processed"),
    )

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(ingestion_service, "ingest_text", new=AsyncMock(return_value=mock_ingest_res)):

        add_resp = client.post(
            f"/api/v1/admin/knowledge/{temple_id}/faq",
            headers=headers,
            json={
                "question": "Can I bring cameras inside?",
                "answer": "Cameras and phones are strictly prohibited.",
                "category": "security",
            },
        )

    assert add_resp.status_code == 201
    assert add_resp.json()["success"] is True
    assert add_resp.json()["documentId"] == "faq_doc_999"

    # 2. List FAQs
    mock_faq_doc = {
        "_id": "faq_doc_999",
        "templeId": temple_id,
        "title": "FAQ: Can I bring cameras inside?",
        "category": "security",
        "sourceType": "faq",
        "metadata": {
            "question": "Can I bring cameras inside?",
            "answer": "Cameras and phones are strictly prohibited.",
            "type": "faq",
        },
        "chunkCount": 1,
    }

    mock_doc_col = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[mock_faq_doc])
    mock_doc_col.find.return_value = mock_cursor
    mock_doc_col.find_one = AsyncMock(return_value=mock_faq_doc)
    mock_doc_col.update_one = AsyncMock()
    mock_doc_col.delete_one = AsyncMock()

    mock_chunk_col = MagicMock()
    mock_chunk_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "knowledge_documents_collection", new=mock_doc_col):

        list_resp = client.get(
            f"/api/v1/admin/knowledge/{temple_id}/faqs",
            headers=headers,
        )

    assert list_resp.status_code == 200
    faqs = list_resp.json()
    assert len(faqs) == 1
    assert faqs[0]["question"] == "Can I bring cameras inside?"
    assert faqs[0]["answer"] == "Cameras and phones are strictly prohibited."

    # 3. Get single FAQ
    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "knowledge_documents_collection", new=mock_doc_col):

        get_resp = client.get(
            f"/api/v1/admin/knowledge/{temple_id}/faqs/faq_doc_999",
            headers=headers,
        )

    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == "faq_doc_999"

    # 4. Update FAQ
    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "knowledge_documents_collection", new=mock_doc_col), \
         patch.object(vector_search_service, "delete_chunks_by_document", new=AsyncMock()), \
         patch.object(embedding_service, "embed_chunks", new=AsyncMock(return_value=[MagicMock()])), \
         patch.object(vector_search_service, "store_chunk", new=AsyncMock()):

        update_resp = client.put(
            f"/api/v1/admin/knowledge/{temple_id}/faqs/faq_doc_999",
            headers=headers,
            json={
                "question": "Can I bring cameras inside the sanctum?",
                "answer": "Cameras are allowed in the courtyard only, forbidden in sanctum.",
                "category": "security",
            },
        )

    assert update_resp.status_code == 200
    assert update_resp.json()["question"] == "Can I bring cameras inside the sanctum?"

    # 5. Delete FAQ
    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "knowledge_documents_collection", new=mock_doc_col), \
         patch.object(DatabaseService, "knowledge_chunks_collection", new=mock_chunk_col):

        del_resp = client.delete(
            f"/api/v1/admin/knowledge/{temple_id}/faqs/faq_doc_999",
            headers=headers,
        )

    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True


# ==============================================================================
# 8. Unanswered Questions & 9. Basic Analytics Tests
# ==============================================================================


def test_admin_view_unanswered_questions(client: TestClient) -> None:
    """Temple admin can view logged questions that triggered fallback responses."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    mock_assistant_msgs = [
        {
            "_id": "msg_a_1",
            "conversationId": "conv_123",
            "role": "assistant",
            "content": "I apologize, but that information is not available in the current temple records.",
            "createdAt": "2026-10-14T11:00:00Z",
        }
    ]

    mock_user_msg = {
        "_id": "msg_u_1",
        "conversationId": "conv_123",
        "role": "user",
        "content": "What is the fee for photography?",
        "createdAt": "2026-10-14T10:59:58Z",
    }

    mock_msg_col = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=mock_assistant_msgs)
    mock_msg_col.find.return_value = mock_cursor
    mock_msg_col.find_one = AsyncMock(return_value=mock_user_msg)

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "messages_collection", new=mock_msg_col):

        response = client.get(
            f"/api/v1/admin/knowledge/{temple_id}/unanswered",
            headers=headers,
        )

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["conversationId"] == "conv_123"
    assert items[0]["question"] == "What is the fee for photography?"


def test_admin_get_chatbot_analytics(client: TestClient) -> None:
    """Retrieving chatbot traffic, conversations, message distribution, and knowledge stats."""
    admin_id = "admin_001"
    temple_id = "temple-001"
    headers = make_admin_headers(admin_id, temple_id)
    mock_admin = create_mock_admin(admin_id, temple_id)

    # Mock count_documents calls
    async def mock_count_docs(query: Dict[str, Any], **kwargs: Any) -> int:
        role = query.get("role")
        if role == "user":
            return 80
        elif role == "assistant":
            if "content" in query:
                return 8  # fallback/unanswered
            return 80
        return 160

    mock_conv_col = MagicMock()
    mock_conv_col.count_documents = AsyncMock(return_value=40)

    mock_msg_col = MagicMock()
    mock_msg_col.count_documents = AsyncMock(side_effect=mock_count_docs)
    mock_msgs_cursor = MagicMock()
    mock_msgs_cursor.sort.return_value = mock_msgs_cursor
    mock_msgs_cursor.limit.return_value = mock_msgs_cursor
    mock_msgs_cursor.to_list = AsyncMock(return_value=[{"content": "When is darshan?", "createdAt": "2026-10-14T11:00:00Z"}])
    mock_msg_col.find.return_value = mock_msgs_cursor

    mock_doc_col = MagicMock()
    mock_doc_col.count_documents = AsyncMock(return_value=12)
    mock_agg_sources = MagicMock()
    mock_agg_sources.to_list = AsyncMock(return_value=[{"_id": "pdf", "count": 6}, {"_id": "faq", "count": 6}])
    mock_agg_cats = MagicMock()
    mock_agg_cats.to_list = AsyncMock(return_value=[{"_id": "rituals", "count": 8}, {"_id": "history", "count": 4}])
    mock_doc_col.aggregate = MagicMock(side_effect=[mock_agg_sources, mock_agg_cats])

    mock_chunk_col = MagicMock()
    mock_chunk_col.count_documents = AsyncMock(return_value=65)

    mock_crawl_col = MagicMock()
    mock_crawl_col.count_documents = AsyncMock(return_value=3)
    mock_crawl_col.find_one = AsyncMock(return_value={"startedAt": "2026-10-14T08:00:00Z"})

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(DatabaseService, "conversations_collection", new=mock_conv_col), \
         patch.object(DatabaseService, "messages_collection", new=mock_msg_col), \
         patch.object(DatabaseService, "knowledge_documents_collection", new=mock_doc_col), \
         patch.object(DatabaseService, "knowledge_chunks_collection", new=mock_chunk_col), \
         patch.object(DatabaseService, "crawl_jobs_collection", new=mock_crawl_col):

        response = client.get(
            f"/api/v1/admin/knowledge/{temple_id}/analytics",
            headers=headers,
        )

    assert response.status_code == 200
    res = response.json()
    assert res["templeId"] == temple_id

    overview = res["overview"]
    assert overview["totalConversations"] == 40
    assert overview["userQueries"] == 80
    assert overview["unansweredQueries"] == 8
    assert overview["fallbackRatePercentage"] == 10.0
    assert overview["totalKnowledgeDocuments"] == 12
    assert overview["totalKnowledgeChunks"] == 65
    assert overview["totalCrawls"] == 3

    assert res["documentsBySourceType"]["pdf"] == 6
    assert res["documentsByCategory"]["rituals"] == 8
    assert len(res["recentQuestions"]) == 1


# ==============================================================================
# 10. Cross-Temple Isolation & Authorization Enforcement
# ==============================================================================


def test_cross_temple_analytics_and_unanswered_rejected(client: TestClient) -> None:
    """CRITICAL: Temple admin assigned to Temple A CANNOT view analytics or unanswered queries for Temple B."""
    admin_id = "admin_001"
    temple_a = "temple-001"
    temple_b = "temple-002"
    headers = make_admin_headers(admin_id, temple_a)
    mock_admin = create_mock_admin(admin_id, temple_a)

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)):
        # 1. Attempting analytics of temple B
        res_analytics = client.get(f"/api/v1/admin/knowledge/{temple_b}/analytics", headers=headers)
        assert res_analytics.status_code == 403
        assert res_analytics.json()["error"]["code"] == "FORBIDDEN"

        # 2. Attempting unanswered of temple B
        res_unanswered = client.get(f"/api/v1/admin/knowledge/{temple_b}/unanswered", headers=headers)
        assert res_unanswered.status_code == 403
        assert res_unanswered.json()["error"]["code"] == "FORBIDDEN"

        # 3. Attempting crawl status of temple B
        res_crawl = client.get(f"/api/v1/admin/knowledge/{temple_b}/crawl/status", headers=headers)
        assert res_crawl.status_code == 403
        assert res_crawl.json()["error"]["code"] == "FORBIDDEN"

        # 4. Attempting FAQ list of temple B
        res_faqs = client.get(f"/api/v1/admin/knowledge/{temple_b}/faqs", headers=headers)
        assert res_faqs.status_code == 403
        assert res_faqs.json()["error"]["code"] == "FORBIDDEN"

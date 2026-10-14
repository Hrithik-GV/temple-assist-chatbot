"""Protected Admin API for knowledge base management, document ingestion, FAQs, crawling, and analytics."""

from typing import Any, Dict, List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, Path, UploadFile, status

from app.core.auth import RequireTempleAccess
from app.core.errors import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.models.auth import CrawlTriggerRequest, FAQCreateRequest, KnowledgeTextCreateRequest
from app.models.collections import Collections
from app.models.knowledge import DocumentSourceType
from app.services.crawler_service import crawler_service
from app.services.database_service import database_service
from app.services.ingestion_service import ingestion_service
from app.services.rag_service import NO_CONTEXT_FALLBACK_ANSWER

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/knowledge", tags=["Admin Knowledge"])


def _to_object_id_query(id_str: str) -> Dict[str, Any]:
    """Helper to build query matching string or ObjectId."""
    conditions = [{"_id": id_str}, {"id": id_str}]
    if ObjectId.is_valid(id_str):
        conditions.append({"_id": ObjectId(id_str)})
    return {"$or": conditions}


# ==============================================================================
# Document Management & Ingestion Status
# ==============================================================================


@router.get(
    "/{templeId}/documents",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List Knowledge Documents & Status",
    description="View all ingested knowledge documents, their processing status, and chunk counts for a temple.",
)
async def list_documents(
    temple_id: str = Path(..., alias="templeId"),
    limit: int = 50,
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> List[Dict[str, Any]]:
    """List knowledge documents strictly scoped to templeId."""
    docs = await database_service.get_knowledge_documents_by_temple(temple_id=temple_id, limit=limit)
    for doc in docs:
        doc["_id"] = str(doc.get("_id"))
    return docs


@router.get(
    "/{templeId}/documents/{documentId}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get Document Details & Chunks",
    description="Retrieve specific document metadata along with all associated indexed knowledge chunks.",
)
async def get_document_details(
    temple_id: str = Path(..., alias="templeId"),
    document_id: str = Path(..., alias="documentId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Retrieve document details and chunks with strict temple scoping."""
    query: Dict[str, Any] = {
        "templeId": temple_id,
        **_to_object_id_query(document_id),
    }
    doc = await database_service.knowledge_documents_collection.find_one(query)
    if not doc:
        raise NotFoundException(f"Document '{document_id}' not found for temple '{temple_id}'.")

    doc["_id"] = str(doc["_id"])

    # Retrieve chunks
    chunks = await database_service.get_knowledge_chunks_by_temple(
        temple_id=temple_id,
        document_id=doc["_id"],
        limit=500,
    )
    for chunk in chunks:
        chunk["_id"] = str(chunk.get("_id"))
        # Strip large raw embedding vectors from basic display
        chunk.pop("embedding", None)

    return {
        "document": doc,
        "chunksCount": len(chunks),
        "chunks": chunks,
    }


@router.delete(
    "/{templeId}/documents/{documentId}",
    status_code=status.HTTP_200_OK,
    summary="Delete Knowledge Document",
    description="Delete a knowledge document and purge all associated chunks from the vector search index.",
)
async def delete_document(
    temple_id: str = Path(..., alias="templeId"),
    document_id: str = Path(..., alias="documentId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Delete document and all chunks scoped to templeId."""
    query: Dict[str, Any] = {
        "templeId": temple_id,
        **_to_object_id_query(document_id),
    }
    doc = await database_service.knowledge_documents_collection.find_one(query)
    if not doc:
        raise NotFoundException(f"Document '{document_id}' not found for temple '{temple_id}'.")

    doc_id_str = str(doc["_id"])

    # Delete document record
    await database_service.knowledge_documents_collection.delete_one({"_id": doc["_id"], "templeId": temple_id})

    # Purge chunks
    chunk_del = await database_service.knowledge_chunks_collection.delete_many(
        {"templeId": temple_id, "documentId": doc_id_str}
    )

    logger.info(
        "Deleted document '%s' and purged %d chunks for temple '%s'",
        doc_id_str,
        chunk_del.deleted_count,
        temple_id,
    )

    return {
        "success": True,
        "message": f"Document '{doc_id_str}' and {chunk_del.deleted_count} vector chunks deleted.",
        "chunksPurged": chunk_del.deleted_count,
    }


# ==============================================================================
# Document Upload & Ingestion
# ==============================================================================


@router.post(
    "/{templeId}/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload Document File",
    description="Upload a PDF, DOCX, or TXT file to extract, clean, chunk, embed, and index for a temple.",
)
async def upload_document(
    temple_id: str = Path(..., alias="templeId"),
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form("general"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Upload and ingest a document file."""
    if not file.filename:
        raise BadRequestException("Uploaded file must have a filename.")

    content = await file.read()
    if not content:
        raise BadRequestException("Uploaded file is empty.")

    doc_title = title.strip() if title else file.filename

    # Ingest document
    result = await ingestion_service.ingest_document(
        temple_id=temple_id,
        source=content,
        title=doc_title,
        filename=file.filename,
        category=category,
    )

    return {
        "success": True,
        "documentId": result.document_id,
        "chunksCreated": result.chunks_created,
        "status": result.status.value,
        "isDuplicate": result.is_duplicate,
    }


# ==============================================================================
# FAQs and Raw Text Ingestion
# ==============================================================================


@router.post(
    "/{templeId}/faq",
    status_code=status.HTTP_201_CREATED,
    summary="Add Temple FAQ",
    description="Add a verified Question and Answer directly into the temple knowledge base.",
)
async def add_faq(
    faq_data: FAQCreateRequest,
    temple_id: str = Path(..., alias="templeId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Ingest FAQ question and answer into vector-indexed knowledge chunks."""
    faq_text = f"QUESTION: {faq_data.question.strip()}\nANSWER: {faq_data.answer.strip()}"

    result = await ingestion_service.ingest_text(
        text=faq_text,
        temple_id=temple_id,
        title=f"FAQ: {faq_data.question[:60]}",
        category=faq_data.category or "faq",
        source="admin_faq",
    )

    return {
        "success": True,
        "documentId": result.document_id,
        "chunksCreated": result.chunks_created,
        "status": result.status.value,
    }


@router.post(
    "/{templeId}/text",
    status_code=status.HTTP_201_CREATED,
    summary="Add Text Knowledge",
    description="Ingest arbitrary text knowledge (guidelines, pooja timings, history) directly into the knowledge base.",
)
async def add_text_knowledge(
    text_data: KnowledgeTextCreateRequest,
    temple_id: str = Path(..., alias="templeId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Ingest raw text into vector-indexed knowledge chunks."""
    result = await ingestion_service.ingest_text(
        text=text_data.content.strip(),
        temple_id=temple_id,
        title=text_data.title.strip(),
        category=text_data.category or "general",
        source="admin_text",
    )

    return {
        "success": True,
        "documentId": result.document_id,
        "chunksCreated": result.chunks_created,
        "status": result.status.value,
    }


# ==============================================================================
# Website Crawler Ingestion
# ==============================================================================


@router.post(
    "/{templeId}/crawl",
    status_code=status.HTTP_200_OK,
    summary="Trigger Website Crawling",
    description="Trigger a Playwright-based website crawl to discover, render, and index pages for a temple.",
)
async def trigger_website_crawl(
    crawl_data: CrawlTriggerRequest,
    temple_id: str = Path(..., alias="templeId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Crawl a temple website and ingest pages."""
    summary = await crawler_service.crawl_temple_website(
        temple_id=temple_id,
        start_url=crawl_data.start_url.strip(),
        max_pages=crawl_data.max_pages,
        max_depth=crawl_data.max_depth,
    )

    return {
        "success": True,
        "startUrl": summary.start_url,
        "totalPagesVisited": summary.total_pages_visited,
        "pagesIngested": summary.pages_ingested,
        "pagesSkipped": summary.pages_skipped,
        "pagesFailed": summary.pages_failed,
        "totalChunksCreated": summary.total_chunks_created,
        "durationSeconds": summary.duration_seconds,
    }


# ==============================================================================
# Unanswered Questions Analytics
# ==============================================================================


@router.get(
    "/{templeId}/unanswered",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="View Unanswered Devotee Questions",
    description="Retrieve questions where the assistant responded with fallback because temple knowledge was missing.",
)
async def view_unanswered_questions(
    temple_id: str = Path(..., alias="templeId"),
    limit: int = 50,
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> List[Dict[str, Any]]:
    """Retrieve recent queries that returned no-context fallback answers."""
    # Find assistant messages that contain NO_CONTEXT_FALLBACK_ANSWER for this temple
    cursor = (
        database_service.messages_collection.find(
            {
                "templeId": temple_id,
                "role": "assistant",
                "content": {"$regex": "not available in the current temple records"},
            }
        )
        .sort("createdAt", -1)
        .limit(limit)
    )

    fallback_assistant_msgs = await cursor.to_list(length=limit)

    unanswered: List[Dict[str, Any]] = []

    for a_msg in fallback_assistant_msgs:
        conv_id = a_msg.get("conversationId")
        msg_time = a_msg.get("createdAt")

        # Find the immediately preceding user message in that conversation
        user_msg = await database_service.messages_collection.find_one(
            {
                "templeId": temple_id,
                "conversationId": conv_id,
                "role": "user",
                "createdAt": {"$lte": msg_time},
            },
            sort=[("createdAt", -1)],
        )

        if user_msg:
            unanswered.append({
                "conversationId": conv_id,
                "question": user_msg.get("content"),
                "askedAt": user_msg.get("createdAt"),
                "fallbackAnswer": a_msg.get("content"),
            })

    return unanswered

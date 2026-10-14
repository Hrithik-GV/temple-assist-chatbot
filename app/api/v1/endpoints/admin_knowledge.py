"""Protected Admin API for knowledge base management, document ingestion, FAQs, crawling, and analytics.

Enforces strict temple-level authorization across all endpoints.
Reuses existing Ingestion, Vector Search, Crawler, and Database services.
"""

import hashlib
from typing import Any, Dict, List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile, status

from app.core.auth import RequireTempleAccess
from app.core.config import settings
from app.core.errors import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.models.auth import (
    CrawlTriggerRequest,
    FAQCreateRequest,
    FAQUpdateRequest,
    KnowledgeTextCreateRequest,
)
from app.models.knowledge import DocumentSourceType, KnowledgeChunk
from app.services.crawler_service import crawler_service
from app.services.database_service import database_service
from app.services.embedding_service import embedding_service
from app.services.ingestion_service import ingestion_service
from app.services.vector_search_service import vector_search_service
from app.utils.helpers import get_utc_now
from app.utils.text_chunker import chunk_text, count_tokens
from app.utils.text_cleaner import clean_text

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/knowledge", tags=["Admin Knowledge"])


def _to_object_id_query(id_str: str) -> Dict[str, Any]:
    """Helper to build query matching string or ObjectId."""
    conditions: List[Dict[str, Any]] = [{"_id": id_str}, {"id": id_str}]
    if ObjectId.is_valid(id_str):
        conditions.append({"_id": ObjectId(id_str)})
    return {"$or": conditions}


def _format_faq_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Format MongoDB KnowledgeDocument into an FAQ representation."""
    doc_id = str(doc.get("_id"))
    metadata = doc.get("metadata", {}) or {}

    question = metadata.get("question")
    answer = metadata.get("answer")

    if not question or not answer:
        raw = doc.get("rawContent", "")
        if "QUESTION:" in raw and "ANSWER:" in raw:
            parts = raw.split("ANSWER:", 1)
            q_part = parts[0].replace("QUESTION:", "").strip()
            a_part = parts[1].strip()
            question = question or q_part
            answer = answer or a_part
        else:
            question = question or doc.get("title", "").replace("FAQ: ", "")
            answer = answer or raw

    return {
        "id": doc_id,
        "templeId": doc.get("templeId"),
        "question": question or "",
        "answer": answer or "",
        "category": doc.get("category", "faq"),
        "chunkCount": doc.get("chunkCount", 1),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


# ==============================================================================
# 1. Document Upload & Ingestion
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
    """Upload and ingest a document file into the temple knowledge base."""
    if not file.filename:
        raise BadRequestException("Uploaded file must have a filename.")

    content = await file.read()
    if not content:
        raise BadRequestException("Uploaded file is empty.")

    # Validate file extension
    valid_extensions = {".pdf", ".docx", ".txt", ".text", ".md"}
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in valid_extensions:
        raise BadRequestException(f"Unsupported file format '{ext}'. Allowed: {', '.join(sorted(valid_extensions))}")

    doc_title = title.strip() if title else file.filename

    # Execute end-to-end ingestion pipeline
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
        "title": doc_title,
        "chunksCreated": result.chunks_created,
        "status": result.status.value,
        "isDuplicate": result.is_duplicate,
        "message": result.message,
    }


# ==============================================================================
# 2. Document Listing
# ==============================================================================


@router.get(
    "/{templeId}/documents",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List Knowledge Documents & Status",
    description="View all ingested knowledge documents, filtering by status, source type, and category.",
)
async def list_documents(
    temple_id: str = Path(..., alias="templeId"),
    source_type: Optional[str] = Query(None, alias="sourceType"),
    doc_status: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> List[Dict[str, Any]]:
    """List knowledge documents strictly scoped to templeId."""
    query: Dict[str, Any] = {"templeId": temple_id}

    if source_type:
        query["sourceType"] = source_type.lower()
    if doc_status:
        query["status"] = doc_status.lower()
    if category:
        query["category"] = category
    if search:
        query["title"] = {"$regex": search.strip(), "$options": "i"}

    cursor = (
        database_service.knowledge_documents_collection.find(query)
        .sort("createdAt", -1)
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    for doc in docs:
        doc["_id"] = str(doc.get("_id"))
        doc["id"] = doc["_id"]
    return docs


# ==============================================================================
# 3. Document Deletion
# ==============================================================================


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

    # Purge associated vector chunks
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
# 4. Triggering Website Crawl & 5. Viewing Crawl Status
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
    """Crawl a temple website, track job status, and ingest pages into vector storage."""
    crawl_id = str(ObjectId())
    now = get_utc_now()

    # Record crawl job initialization
    crawl_job: Dict[str, Any] = {
        "_id": crawl_id,
        "id": crawl_id,
        "templeId": temple_id,
        "startUrl": crawl_data.start_url.strip(),
        "maxPages": crawl_data.max_pages,
        "maxDepth": crawl_data.max_depth,
        "category": crawl_data.category or "website",
        "status": "running",
        "startedAt": now,
        "completedAt": None,
        "durationSeconds": 0.0,
        "totalPagesVisited": 0,
        "pagesIngested": 0,
        "pagesSkipped": 0,
        "pagesFailed": 0,
        "totalChunksCreated": 0,
        "pageResults": [],
        "error": None,
    }
    await database_service.crawl_jobs_collection.insert_one(crawl_job)

    try:
        summary = await crawler_service.crawl_temple_website(
            temple_id=temple_id,
            start_url=crawl_data.start_url.strip(),
            max_pages=crawl_data.max_pages,
            max_depth=crawl_data.max_depth,
            category=crawl_data.category,
        )

        serialized_pages: List[Dict[str, Any]] = []
        for pr in summary.page_results:
            if hasattr(pr, "model_dump"):
                serialized_pages.append(pr.model_dump())
            elif isinstance(pr, dict):
                serialized_pages.append(pr)

        # Update crawl job as completed
        await database_service.crawl_jobs_collection.update_one(
            {"_id": crawl_id},
            {
                "$set": {
                    "status": "completed",
                    "completedAt": get_utc_now(),
                    "durationSeconds": summary.duration_seconds,
                    "totalPagesVisited": summary.total_pages_visited,
                    "pagesIngested": summary.pages_ingested,
                    "pagesSkipped": summary.pages_skipped,
                    "pagesFailed": summary.pages_failed,
                    "totalChunksCreated": summary.total_chunks_created,
                    "pageResults": serialized_pages,
                }
            },
        )

        return {
            "success": True,
            "crawlId": crawl_id,
            "status": "completed",
            "startUrl": summary.start_url,
            "totalPagesVisited": summary.total_pages_visited,
            "pagesIngested": summary.pages_ingested,
            "pagesSkipped": summary.pages_skipped,
            "pagesFailed": summary.pages_failed,
            "totalChunksCreated": summary.total_chunks_created,
            "durationSeconds": summary.duration_seconds,
        }

    except Exception as exc:
        await database_service.crawl_jobs_collection.update_one(
            {"_id": crawl_id},
            {
                "$set": {
                    "status": "failed",
                    "completedAt": get_utc_now(),
                    "error": str(exc),
                }
            },
        )
        logger.error("Crawl job '%s' failed for temple '%s': %s", crawl_id, temple_id, exc)
        raise


@router.get(
    "/{templeId}/crawl/status",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="View Crawl Status & History",
    description="Retrieve the latest crawl run status and history of crawl jobs for a temple.",
)
async def get_crawl_status(
    temple_id: str = Path(..., alias="templeId"),
    limit: int = Query(10, ge=1, le=50),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Retrieve crawl jobs status and history scoped to templeId."""
    cursor = (
        database_service.crawl_jobs_collection.find({"templeId": temple_id})
        .sort("startedAt", -1)
        .limit(limit)
    )
    crawls = await cursor.to_list(length=limit)
    for c in crawls:
        c["_id"] = str(c.get("_id"))
        c["id"] = c["_id"]

    total_crawls = await database_service.crawl_jobs_collection.count_documents({"templeId": temple_id})
    latest = crawls[0] if crawls else None

    return {
        "templeId": temple_id,
        "latestCrawl": latest,
        "totalCrawls": total_crawls,
        "recentCrawls": crawls,
    }


@router.get(
    "/{templeId}/crawl/{crawlId}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get Specific Crawl Job Details",
    description="Inspect detailed crawl outcomes, error logs, and visited page results for a specific crawl ID.",
)
async def get_crawl_details(
    temple_id: str = Path(..., alias="templeId"),
    crawl_id: str = Path(..., alias="crawlId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Retrieve details and page breakdown of a specific crawl job."""
    query: Dict[str, Any] = {"templeId": temple_id, **_to_object_id_query(crawl_id)}
    job = await database_service.crawl_jobs_collection.find_one(query)
    if not job:
        raise NotFoundException(f"Crawl job '{crawl_id}' not found for temple '{temple_id}'.")

    job["_id"] = str(job["_id"])
    job["id"] = job["_id"]
    return job


# ==============================================================================
# 6. Viewing Knowledge Chunks & Document Metadata
# ==============================================================================


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
    doc["id"] = doc["_id"]

    # Retrieve chunks belonging to this document
    chunks = await database_service.get_knowledge_chunks_by_temple(
        temple_id=temple_id,
        document_id=doc["_id"],
        limit=500,
    )
    for chunk in chunks:
        chunk["_id"] = str(chunk.get("_id"))
        chunk["id"] = chunk["_id"]
        # Strip large raw embedding vectors from response
        chunk.pop("embedding", None)

    return {
        "document": doc,
        "chunksCount": len(chunks),
        "chunks": chunks,
    }


@router.get(
    "/{templeId}/chunks",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List Knowledge Chunks",
    description="Inspect indexed vector knowledge chunks across documents for a temple.",
)
async def list_knowledge_chunks(
    temple_id: str = Path(..., alias="templeId"),
    document_id: Optional[str] = Query(None, alias="documentId"),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> List[Dict[str, Any]]:
    """List knowledge chunks with filtering and pagination."""
    query: Dict[str, Any] = {"templeId": temple_id}
    if document_id:
        query["documentId"] = document_id
    if category:
        query["category"] = category
    if search:
        query["content"] = {"$regex": search.strip(), "$options": "i"}

    cursor = (
        database_service.knowledge_chunks_collection.find(query)
        .sort("chunkIndex", 1)
        .skip(skip)
        .limit(limit)
    )
    chunks = await cursor.to_list(length=limit)
    for chunk in chunks:
        chunk["_id"] = str(chunk.get("_id"))
        chunk["id"] = chunk["_id"]
        chunk.pop("embedding", None)

    return chunks


@router.get(
    "/{templeId}/chunks/{chunkId}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get Specific Knowledge Chunk",
    description="View detailed content and metadata of a specific knowledge chunk.",
)
async def get_chunk_details(
    temple_id: str = Path(..., alias="templeId"),
    chunk_id: str = Path(..., alias="chunkId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Retrieve single chunk details strictly scoped to templeId."""
    query: Dict[str, Any] = {"templeId": temple_id, **_to_object_id_query(chunk_id)}
    chunk = await database_service.knowledge_chunks_collection.find_one(query)
    if not chunk:
        raise NotFoundException(f"Chunk '{chunk_id}' not found for temple '{temple_id}'.")

    chunk["_id"] = str(chunk["_id"])
    chunk["id"] = chunk["_id"]
    chunk.pop("embedding", None)
    return chunk


# ==============================================================================
# 7. Adding and Managing FAQs
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
        title=f"FAQ: {faq_data.question.strip()[:60]}",
        category=faq_data.category or "faq",
        source="admin_faq",
        metadata={
            "question": faq_data.question.strip(),
            "answer": faq_data.answer.strip(),
            "type": "faq",
        },
    )

    return {
        "success": True,
        "documentId": result.document_id,
        "chunksCreated": result.chunks_created,
        "status": result.status.value,
        "question": faq_data.question.strip(),
        "answer": faq_data.answer.strip(),
    }


@router.get(
    "/{templeId}/faqs",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List Temple FAQs",
    description="Retrieve all verified FAQs belonging to a temple with search and category filters.",
)
async def list_faqs(
    temple_id: str = Path(..., alias="templeId"),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> List[Dict[str, Any]]:
    """List temple FAQs formatted with questions and answers."""
    query: Dict[str, Any] = {
        "templeId": temple_id,
        "$or": [
            {"sourceType": DocumentSourceType.FAQ.value},
            {"metadata.type": "faq"},
            {"category": "faq"},
        ],
    }

    if category:
        query["category"] = category
    if search:
        query["$and"] = [
            {
                "$or": [
                    {"title": {"$regex": search.strip(), "$options": "i"}},
                    {"rawContent": {"$regex": search.strip(), "$options": "i"}},
                    {"metadata.question": {"$regex": search.strip(), "$options": "i"}},
                    {"metadata.answer": {"$regex": search.strip(), "$options": "i"}},
                ]
            }
        ]

    cursor = (
        database_service.knowledge_documents_collection.find(query)
        .sort("createdAt", -1)
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    return [_format_faq_document(d) for d in docs]


@router.get(
    "/{templeId}/faqs/{faqId}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get Specific Temple FAQ",
    description="Retrieve details of a single FAQ entry.",
)
async def get_faq(
    temple_id: str = Path(..., alias="templeId"),
    faq_id: str = Path(..., alias="faqId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Retrieve single FAQ by ID scoped to templeId."""
    query: Dict[str, Any] = {"templeId": temple_id, **_to_object_id_query(faq_id)}
    doc = await database_service.knowledge_documents_collection.find_one(query)
    if not doc:
        raise NotFoundException(f"FAQ '{faq_id}' not found for temple '{temple_id}'.")

    return _format_faq_document(doc)


@router.put(
    "/{templeId}/faqs/{faqId}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Update Temple FAQ",
    description="Update question, answer, or category of an existing FAQ and refresh its vector embeddings.",
)
async def update_faq(
    faq_update: FAQUpdateRequest,
    temple_id: str = Path(..., alias="templeId"),
    faq_id: str = Path(..., alias="faqId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Update FAQ and re-embed chunks into vector search."""
    query: Dict[str, Any] = {"templeId": temple_id, **_to_object_id_query(faq_id)}
    doc = await database_service.knowledge_documents_collection.find_one(query)
    if not doc:
        raise NotFoundException(f"FAQ '{faq_id}' not found for temple '{temple_id}'.")

    doc_id_str = str(doc["_id"])
    existing_meta = doc.get("metadata", {}) or {}

    new_question = faq_update.question.strip() if faq_update.question else existing_meta.get("question", doc.get("title", ""))
    new_answer = faq_update.answer.strip() if faq_update.answer else existing_meta.get("answer", doc.get("rawContent", ""))
    new_category = faq_update.category.strip() if faq_update.category else doc.get("category", "faq")

    faq_text = f"QUESTION: {new_question}\nANSWER: {new_answer}"
    cleaned = clean_text(faq_text)
    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

    # 1. Purge old chunks for this document
    await vector_search_service.delete_chunks_by_document(temple_id=temple_id, document_id=doc_id_str)

    # 2. Generate new chunk(s) and embeddings
    chunks_text = chunk_text(cleaned, chunk_size=settings.DEFAULT_CHUNK_SIZE)
    chunk_models: List[KnowledgeChunk] = []
    for idx, c_text in enumerate(chunks_text):
        chunk_models.append(
            KnowledgeChunk(
                templeId=temple_id,
                documentId=doc_id_str,
                content=c_text,
                chunkIndex=idx,
                tokenCount=count_tokens(c_text),
                title=f"FAQ: {new_question[:60]}",
                category=new_category,
                metadata={"question": new_question, "answer": new_answer, "type": "faq"},
            )
        )

    embedded_chunks = await embedding_service.embed_chunks(chunk_models)
    for chunk in embedded_chunks:
        await vector_search_service.store_chunk(chunk)

    # 3. Update document record
    now = get_utc_now()
    await database_service.knowledge_documents_collection.update_one(
        {"_id": doc["_id"]},
        {
            "$set": {
                "title": f"FAQ: {new_question[:60]}",
                "category": new_category,
                "rawContent": cleaned,
                "contentHash": content_hash,
                "chunkCount": len(embedded_chunks),
                "updatedAt": now,
                "metadata": {
                    **existing_meta,
                    "question": new_question,
                    "answer": new_answer,
                    "type": "faq",
                },
            }
        },
    )

    return {
        "id": doc_id_str,
        "templeId": temple_id,
        "question": new_question,
        "answer": new_answer,
        "category": new_category,
        "chunkCount": len(embedded_chunks),
        "updatedAt": now,
    }


@router.delete(
    "/{templeId}/faqs/{faqId}",
    status_code=status.HTTP_200_OK,
    summary="Delete Temple FAQ",
    description="Delete an FAQ document and purge its associated vector chunks.",
)
async def delete_faq(
    temple_id: str = Path(..., alias="templeId"),
    faq_id: str = Path(..., alias="faqId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Delete FAQ with vector chunks cascade."""
    return await delete_document(temple_id=temple_id, document_id=faq_id, _authorized=_authorized)


# ==============================================================================
# Raw Text Ingestion
# ==============================================================================


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
# 8. Unanswered Questions Analytics
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
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> List[Dict[str, Any]]:
    """Retrieve recent queries that returned no-context fallback answers."""
    cursor = (
        database_service.messages_collection.find(
            {
                "templeId": temple_id,
                "role": "assistant",
                "content": {"$regex": "not available in the current temple records"},
            }
        )
        .sort("createdAt", -1)
        .skip(skip)
        .limit(limit)
    )

    fallback_assistant_msgs = await cursor.to_list(length=limit)
    unanswered: List[Dict[str, Any]] = []

    for a_msg in fallback_assistant_msgs:
        conv_id = a_msg.get("conversationId")
        msg_time = a_msg.get("createdAt")

        # Find the immediately preceding user message in that conversation
        user_query: Dict[str, Any] = {
            "templeId": temple_id,
            "conversationId": conv_id,
            "role": "user",
        }
        if msg_time:
            user_query["createdAt"] = {"$lte": msg_time}

        user_msg = await database_service.messages_collection.find_one(
            user_query,
            sort=[("createdAt", -1)],
        )

        if user_msg:
            question_text = user_msg.get("content", "")
            if search and search.lower() not in question_text.lower():
                continue

            unanswered.append({
                "conversationId": conv_id,
                "question": question_text,
                "askedAt": user_msg.get("createdAt"),
                "fallbackAnswer": a_msg.get("content"),
            })

    return unanswered


# ==============================================================================
# 9. Basic Chatbot Analytics
# ==============================================================================


@router.get(
    "/{templeId}/analytics",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Temple Chatbot & Knowledge Analytics",
    description="Retrieve high-level chatbot traffic, knowledge metrics, unanswered queries count, and document distributions.",
)
async def get_temple_analytics(
    temple_id: str = Path(..., alias="templeId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Aggregate traffic, conversation stats, and knowledge base coverage for a temple."""
    # 1. Conversation & Message Metrics
    total_conversations = await database_service.conversations_collection.count_documents({"templeId": temple_id})
    active_conversations = await database_service.conversations_collection.count_documents(
        {"templeId": temple_id, "isActive": True}
    )
    total_messages = await database_service.messages_collection.count_documents({"templeId": temple_id})
    user_queries = await database_service.messages_collection.count_documents(
        {"templeId": temple_id, "role": "user"}
    )
    assistant_responses = await database_service.messages_collection.count_documents(
        {"templeId": temple_id, "role": "assistant"}
    )

    # 2. Unanswered / Fallback Queries
    unanswered_count = await database_service.messages_collection.count_documents(
        {
            "templeId": temple_id,
            "role": "assistant",
            "content": {"$regex": "not available in the current temple records"},
        }
    )
    fallback_rate = round((unanswered_count / user_queries * 100), 2) if user_queries > 0 else 0.0

    # 3. Knowledge Document & Chunk Metrics
    total_documents = await database_service.knowledge_documents_collection.count_documents({"templeId": temple_id})
    total_chunks = await database_service.knowledge_chunks_collection.count_documents({"templeId": temple_id})

    # Group documents by sourceType
    doc_types_agg = await database_service.knowledge_documents_collection.aggregate([
        {"$match": {"templeId": temple_id}},
        {"$group": {"_id": "$sourceType", "count": {"$sum": 1}}},
    ]).to_list(length=50)
    by_source_type = {item["_id"] or "other": item["count"] for item in doc_types_agg}

    # Group documents by category
    doc_cats_agg = await database_service.knowledge_documents_collection.aggregate([
        {"$match": {"templeId": temple_id}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
    ]).to_list(length=50)
    by_category = {item["_id"] or "general": item["count"] for item in doc_cats_agg}

    # 4. Crawling Activity
    total_crawls = await database_service.crawl_jobs_collection.count_documents({"templeId": temple_id})
    latest_crawl_doc = await database_service.crawl_jobs_collection.find_one(
        {"templeId": temple_id},
        sort=[("startedAt", -1)],
    )
    last_crawl_at = latest_crawl_doc.get("startedAt") if latest_crawl_doc else None

    # 5. Recent Questions Sample
    recent_msgs_cursor = (
        database_service.messages_collection.find({"templeId": temple_id, "role": "user"})
        .sort("createdAt", -1)
        .limit(5)
    )
    recent_msgs = await recent_msgs_cursor.to_list(length=5)
    recent_questions = [
        {
            "question": m.get("content"),
            "conversationId": m.get("conversationId"),
            "askedAt": m.get("createdAt"),
        }
        for m in recent_msgs
    ]

    return {
        "templeId": temple_id,
        "overview": {
            "totalConversations": total_conversations,
            "activeConversations": active_conversations,
            "totalMessages": total_messages,
            "userQueries": user_queries,
            "assistantResponses": assistant_responses,
            "unansweredQueries": unanswered_count,
            "fallbackRatePercentage": fallback_rate,
            "totalKnowledgeDocuments": total_documents,
            "totalKnowledgeChunks": total_chunks,
            "totalCrawls": total_crawls,
            "lastCrawlAt": last_crawl_at,
        },
        "documentsBySourceType": by_source_type,
        "documentsByCategory": by_category,
        "recentQuestions": recent_questions,
    }

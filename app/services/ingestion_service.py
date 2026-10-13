"""Document ingestion pipeline for extracting, cleaning, chunking, and indexing temple documents."""

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.config import settings
from app.core.database import mongodb
from app.core.errors import AppException, BadRequestException
from app.models.collections import Collections
from app.models.knowledge import (
    DocumentSourceType,
    DocumentStatus,
    IngestionResult,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.services.base import BaseService
from app.services.embedding_service import EmbeddingService, embedding_service
from app.services.vector_search_service import VectorSearchService, vector_search_service
from app.utils.helpers import get_utc_now
from app.utils.text_cleaner import clean_text
from app.utils.text_chunker import chunk_text, count_tokens
from app.utils.text_extractor import extract_text


class IngestionService(BaseService):
    """Reusable service for ingesting PDF, DOCX, and TXT documents into vector-indexed chunks."""

    def __init__(
        self,
        embed_service: Optional[EmbeddingService] = None,
        vector_service: Optional[VectorSearchService] = None,
    ) -> None:
        super().__init__()
        self._embedding_service = embed_service or embedding_service
        self._vector_service = vector_service or vector_search_service
        self._db_manager = mongodb

    @property
    def documents_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for Knowledge Documents."""
        return self._db_manager.get_collection(Collections.KNOWLEDGE_DOCUMENTS)

    @property
    def chunks_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for Knowledge Chunks."""
        return self._db_manager.get_collection(Collections.KNOWLEDGE_CHUNKS)

    async def ingest_document(
        self,
        temple_id: str,
        source: Union[bytes, Path, str],
        title: str,
        source_type: Optional[Union[DocumentSourceType, str]] = None,
        filename: Optional[str] = None,
        source_url: Optional[str] = None,
        category: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        force_reingest: bool = False,
    ) -> IngestionResult:
        """Execute the end-to-end document ingestion pipeline.

        Pipeline:
        1. Input validation
        2. Text extraction (PDF, DOCX, TXT)
        3. Text cleaning & normalization
        4. Deduplication via SHA-256 content fingerprinting
        5. Document record initialization (KnowledgeDocument)
        6. Boundary-aware chunking
        7. Dense vector embedding generation
        8. Vector chunk storage (MongoDB knowledge_chunks)
        9. Status finalization & error handling

        Args:
            temple_id: ID of the temple this document belongs to.
            source: Raw file bytes, file Path, or raw text string.
            title: Title or headline of the document.
            source_type: File format type ('pdf', 'docx', 'txt', etc.).
            filename: Original file name (used for extension detection and source attribution).
            source_url: Optional web URL if document was sourced from web.
            category: Domain category (e.g. 'history', 'rituals', 'darshan', 'timings').
            chunk_size: Max characters per chunk (default from settings).
            chunk_overlap: Overlap characters between chunks (default from settings).
            metadata: Custom key-value pairs to associate with document and its chunks.
            force_reingest: If True, re-indexes document even if identical content exists.

        Returns:
            IngestionResult: Summary report with document ID and created chunk count.
        """
        # 1. Input Validation
        if not temple_id or not temple_id.strip():
            raise BadRequestException("templeId is mandatory for document ingestion.")
        if not title or not title.strip():
            raise BadRequestException("Document title cannot be empty.")

        source_name = filename or (str(source) if isinstance(source, (Path, str)) and len(str(source)) < 255 else title)
        doc_metadata = dict(metadata or {})
        c_size = chunk_size if (chunk_size is not None and chunk_size > 0) else settings.DEFAULT_CHUNK_SIZE
        c_overlap = chunk_overlap if chunk_overlap is not None else settings.DEFAULT_CHUNK_OVERLAP

        # 2. Text Extraction
        self.logger.info("Extracting text for document '%s' (temple: %s)...", title, temple_id)
        st_val = source_type.value if hasattr(source_type, "value") else (str(source_type) if source_type else None)
        raw_text = extract_text(
            source=source,
            file_type=st_val,
            filename=filename,
        )

        if not raw_text or not raw_text.strip():
            raise BadRequestException(f"Document '{title}' contains no readable or extractable text.")

        # 3. Text Cleaning
        cleaned_text = clean_text(raw_text)
        if not cleaned_text:
            raise BadRequestException(f"Document '{title}' contains only whitespace or invalid formatting.")

        # 4. Content Hashing & Deduplication
        content_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
        existing_doc = await self.documents_collection.find_one(
            {"templeId": temple_id, "contentHash": content_hash}
        )

        if existing_doc and not force_reingest:
            existing_id = str(existing_doc["_id"])
            chunk_count = existing_doc.get("chunkCount", 0)
            self.logger.info(
                "Skipping duplicate ingestion for document '%s' (hash: %s, existingId: %s)",
                title,
                content_hash[:8],
                existing_id,
            )
            return IngestionResult(
                document_id=existing_id,
                temple_id=temple_id,
                title=existing_doc.get("title", title),
                status=DocumentStatus(existing_doc.get("status", DocumentStatus.PROCESSED)),
                chunks_created=chunk_count,
                is_duplicate=True,
                message="Document with identical content already ingested for this temple.",
                content_hash=content_hash,
            )

        # Determine resolved document source type enum
        resolved_source_type = self._resolve_source_type(source_type, filename)

        document_id: Optional[str] = None
        if existing_doc and force_reingest:
            # Reingestion of existing document: clean up old chunks first
            document_id = str(existing_doc["_id"])
            await self._vector_service.delete_chunks_by_document(temple_id, document_id)
            await self.documents_collection.update_one(
                {"_id": existing_doc["_id"]},
                {
                    "$set": {
                        "status": DocumentStatus.PROCESSING.value,
                        "title": title,
                        "source": source_name,
                        "sourceUrl": source_url,
                        "category": category,
                        "rawContent": cleaned_text[:10000],  # store reasonable preview/content
                        "updatedAt": get_utc_now(),
                    }
                },
            )
        else:
            # Create new document record in MongoDB
            doc_record = KnowledgeDocument(
                templeId=temple_id,
                title=title,
                sourceType=resolved_source_type,
                source=source_name,
                sourceUrl=source_url,
                category=category,
                contentHash=content_hash,
                rawContent=cleaned_text[:10000],
                status=DocumentStatus.PROCESSING,
                chunkCount=0,
                metadata=doc_metadata,
            )
            res = await self.documents_collection.insert_one(doc_record.to_mongo_dict())
            document_id = str(res.inserted_id)

        try:
            # 5. Text Chunking
            text_chunks = chunk_text(
                cleaned_text,
                chunk_size=c_size,
                chunk_overlap=c_overlap,
            )

            if not text_chunks:
                text_chunks = [cleaned_text]

            self.logger.info(
                "Created %d chunks for document '%s' (chunk_size: %d, overlap: %d)",
                len(text_chunks),
                title,
                c_size,
                c_overlap,
            )

            # 6. Build KnowledgeChunk models
            chunks_to_store: List[KnowledgeChunk] = []
            for idx, c_text in enumerate(text_chunks):
                chunk_meta = dict(doc_metadata)
                chunk_meta["contentLength"] = len(c_text)

                chunk = KnowledgeChunk(
                    templeId=temple_id,
                    documentId=document_id,
                    content=c_text,
                    source=source_name,
                    title=title,
                    category=category,
                    chunkIndex=idx,
                    tokenCount=count_tokens(c_text),
                    metadata=chunk_meta,
                )
                chunks_to_store.append(chunk)

            # 7. Generate Embeddings & Persist Chunks via VectorSearchService
            await self._vector_service.store_chunks(chunks_to_store)

            # 8. Finalize Document Status
            await self.documents_collection.update_one(
                self._doc_query(document_id),
                {
                    "$set": {
                        "status": DocumentStatus.PROCESSED.value,
                        "chunkCount": len(chunks_to_store),
                        "updatedAt": get_utc_now(),
                    }
                },
            )

            self.logger.info(
                "Ingestion successfully completed for document '%s' (%d chunks).",
                title,
                len(chunks_to_store),
            )

            return IngestionResult(
                document_id=document_id,
                temple_id=temple_id,
                title=title,
                status=DocumentStatus.PROCESSED,
                chunks_created=len(chunks_to_store),
                is_duplicate=False,
                message=f"Successfully ingested and indexed {len(chunks_to_store)} chunks.",
                content_hash=content_hash,
            )

        except Exception as exc:
            # 9. Clean Failure Handling & Orphaned Chunks Rollback
            self.logger.error(
                "Ingestion failed for document '%s' (id: %s): %s",
                title,
                document_id,
                str(exc),
                exc_info=True,
            )

            if document_id:
                # Always clean up any partial or orphaned chunks first
                try:
                    await self._vector_service.delete_chunks_by_document(temple_id, document_id)
                except Exception as cleanup_exc:
                    self.logger.error("Error during ingestion chunk cleanup: %s", cleanup_exc)

                # Mark document status as FAILED in database
                try:
                    await self.documents_collection.update_one(
                        self._doc_query(document_id),
                        {
                            "$set": {
                                "status": DocumentStatus.FAILED.value,
                                "metadata.error": str(exc),
                                "updatedAt": get_utc_now(),
                            }
                        },
                    )
                except Exception as update_exc:
                    self.logger.error("Error updating document failure status: %s", update_exc)

            raise AppException(
                message=f"Document ingestion failed: {str(exc)}",
                error_code="INGESTION_ERROR",
                details={"templeId": temple_id, "title": title, "documentId": document_id},
            )

    async def ingest_file(
        self,
        file_path: Union[Path, str],
        temple_id: str,
        title: Optional[str] = None,
        category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        force_reingest: bool = False,
    ) -> IngestionResult:
        """Convenience method to ingest a local PDF, DOCX, or TXT file by path.

        Args:
            file_path: Filesystem path to the file.
            temple_id: Target temple identifier.
            title: Optional title override (defaults to filename stem).
            category: Optional classification category.
            metadata: Optional extra metadata dictionary.
            force_reingest: Whether to force re-indexing if content is identical.

        Returns:
            IngestionResult: Ingestion report.
        """
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise BadRequestException(f"Specified file path does not exist: {file_path}")

        doc_title = title or path.stem.replace("_", " ").replace("-", " ").title()
        file_bytes = path.read_bytes()

        return await self.ingest_document(
            temple_id=temple_id,
            source=file_bytes,
            title=doc_title,
            filename=path.name,
            category=category,
            metadata=metadata,
            force_reingest=force_reingest,
        )

    async def ingest_text(
        self,
        text: str,
        temple_id: str,
        title: str,
        category: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        force_reingest: bool = False,
    ) -> IngestionResult:
        """Convenience method to ingest raw text directly (e.g. FAQs, manual entries).

        Args:
            text: Plain text content.
            temple_id: Target temple identifier.
            title: Document title.
            category: Optional category tag.
            source: Source descriptor (e.g. 'manual', 'faq_entry').
            metadata: Optional extra metadata dictionary.
            force_reingest: Whether to re-index identical content.

        Returns:
            IngestionResult: Ingestion report.
        """
        return await self.ingest_document(
            temple_id=temple_id,
            source=text,
            title=title,
            source_type=DocumentSourceType.TEXT,
            filename=source or f"{title}.txt",
            category=category,
            metadata=metadata,
            force_reingest=force_reingest,
        )

    def _resolve_source_type(
        self,
        source_type: Optional[Union[DocumentSourceType, str]],
        filename: Optional[str],
    ) -> DocumentSourceType:
        """Infer DocumentSourceType enum from explicit parameter or filename extension."""
        if isinstance(source_type, DocumentSourceType):
            return source_type

        st = (str(source_type) if source_type else "").lower().strip()
        if st in ("pdf",):
            return DocumentSourceType.PDF
        elif st in ("docx", "doc"):
            return DocumentSourceType.DOCX
        elif st in ("txt", "text", "md"):
            return DocumentSourceType.TEXT
        elif st in ("website", "web"):
            return DocumentSourceType.WEBSITE
        elif st in ("faq",):
            return DocumentSourceType.FAQ

        if filename:
            ext = Path(filename).suffix.lower().lstrip(".")
            if ext == "pdf":
                return DocumentSourceType.PDF
            elif ext in ("docx", "doc"):
                return DocumentSourceType.DOCX
            elif ext in ("txt", "md", "text"):
                return DocumentSourceType.TEXT

        return DocumentSourceType.MANUAL

    @staticmethod
    def _doc_query(doc_id: str) -> Dict[str, Any]:
        """Build resilient query for document id whether valid ObjectId or string."""
        if ObjectId.is_valid(doc_id):
            return {"_id": ObjectId(doc_id)}
        return {"_id": doc_id}


# Global singleton instance
ingestion_service = IngestionService()

"""Vector search service for storing embeddings and executing semantic queries with MongoDB Atlas."""

import math
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.errors import OperationFailure

from app.core.config import settings
from app.core.database import mongodb
from app.core.errors import BadRequestException
from app.models.collections import Collections
from app.models.knowledge import KnowledgeChunk, VectorSearchResult
from app.services.base import BaseService
from app.services.embedding_service import EmbeddingService, embedding_service


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculate cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


class VectorSearchService(BaseService):
    """Encapsulates vector storage, chunk embedding, and semantic similarity search in MongoDB Atlas."""

    def __init__(
        self,
        embed_service: Optional[EmbeddingService] = None,
    ) -> None:
        super().__init__()
        self._embedding_service = embed_service or embedding_service
        self._db_manager = mongodb

    @property
    def chunks_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for knowledge chunks."""
        return self._db_manager.get_collection(Collections.KNOWLEDGE_CHUNKS)

    @property
    def embedding_service(self) -> EmbeddingService:
        """Active embedding service."""
        return self._embedding_service

    # ==========================================================================
    # Chunk Storage & Embedding Generation
    # ==========================================================================

    async def store_chunk(self, chunk: KnowledgeChunk) -> KnowledgeChunk:
        """Generate embedding (if missing) and persist knowledge chunk in MongoDB.

        Args:
            chunk: KnowledgeChunk instance.

        Returns:
            KnowledgeChunk: Persisted chunk with ID and embedding populated.
        """
        if not chunk.temple_id or not chunk.temple_id.strip():
            raise BadRequestException("templeId is required to store a knowledge chunk.")
        if not chunk.content or not chunk.content.strip():
            raise BadRequestException("Chunk content cannot be empty.")

        # Ensure embedding exists
        if not chunk.embedding:
            self._embedding_service.embed_chunk(chunk)

        doc_dict = chunk.to_mongo_dict()
        res = await self.chunks_collection.insert_one(doc_dict)
        chunk.id = str(res.inserted_id)
        return chunk

    async def store_chunks(self, chunks: List[KnowledgeChunk]) -> List[KnowledgeChunk]:
        """Batch generate embeddings and persist multiple knowledge chunks.

        Args:
            chunks: List of KnowledgeChunk instances.

        Returns:
            List[KnowledgeChunk]: Persisted chunks with IDs.
        """
        if not chunks:
            return []

        # Validate all chunks
        for idx, c in enumerate(chunks):
            if not c.temple_id or not c.temple_id.strip():
                raise BadRequestException(f"Chunk at index {idx} is missing required templeId.")
            if not c.content or not c.content.strip():
                raise BadRequestException(f"Chunk at index {idx} has empty content.")

        # Batch embed any chunks that do not yet have an embedding
        unembedded = [c for c in chunks if not c.embedding]
        if unembedded:
            self._embedding_service.embed_chunks(unembedded)

        docs = [c.to_mongo_dict() for c in chunks]
        res = await self.chunks_collection.insert_many(docs)
        for chunk, inserted_id in zip(chunks, res.inserted_ids):
            chunk.id = str(inserted_id)

        self.logger.info("Persisted %d knowledge chunks to MongoDB.", len(chunks))
        return chunks

    # ==========================================================================
    # Semantic Search Filtered by Temple ID
    # ==========================================================================

    async def search(
        self,
        temple_id: str,
        query: str,
        top_k: Optional[int] = None,
        category: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> List[VectorSearchResult]:
        """Execute semantic vector search filtered strictly by templeId.

        Args:
            temple_id: Target temple identifier.
            query: User search query or question.
            top_k: Number of nearest neighbors to retrieve (default: settings.DEFAULT_TOP_K).
            category: Optional category filter (e.g. 'rituals', 'history').
            min_score: Minimum similarity score threshold (0.0 to 1.0).

        Returns:
            List[VectorSearchResult]: Ranked list of retrieved chunks with similarity scores.
        """
        # 1. Validation
        if not temple_id or not temple_id.strip():
            raise BadRequestException("templeId is mandatory for vector search.")
        if not query or not query.strip():
            raise BadRequestException("Search query cannot be empty.")

        limit = top_k if (top_k is not None and top_k > 0) else settings.DEFAULT_TOP_K
        if limit > 100:
            limit = 100  # Cap retrieval size for safety

        # 2. Generate dense query vector
        query_vector = self._embedding_service.generate_embedding(query)

        # 3. Build MongoDB Atlas $vectorSearch aggregation pipeline
        num_candidates = max(limit * settings.NUM_CANDIDATES_MULTIPLIER, limit + 10)
        filter_dict: Dict[str, Any] = {"templeId": {"$eq": temple_id}}
        if category:
            filter_dict["category"] = {"$eq": category}

        pipeline: List[Dict[str, Any]] = [
            {
                "$vectorSearch": {
                    "index": settings.VECTOR_SEARCH_INDEX_NAME,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": num_candidates,
                    "limit": limit,
                    "filter": filter_dict,
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "templeId": 1,
                    "documentId": 1,
                    "content": 1,
                    "title": 1,
                    "source": 1,
                    "category": 1,
                    "metadata": 1,
                    "chunkIndex": 1,
                    "tokenCount": 1,
                    "createdAt": 1,
                    "updatedAt": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]

        try:
            cursor = self.chunks_collection.aggregate(pipeline)
            raw_results = await cursor.to_list(length=limit)

            results: List[VectorSearchResult] = []
            for item in raw_results:
                score = float(item.get("score", 0.0))
                if min_score is not None and score < min_score:
                    continue
                item_id = str(item.pop("_id", None))
                item["id"] = item_id
                item["score"] = score
                chunk = KnowledgeChunk.model_validate(item)
                results.append(VectorSearchResult(chunk=chunk, score=score))

            return results

        except OperationFailure as exc:
            # When running on local MongoDB or when Atlas Search is not provisioned,
            # $vectorSearch will raise an OperationFailure ("Unrecognized pipeline stage name: '$vectorSearch'")
            if "$vectorSearch" in str(exc) or "Unrecognized pipeline stage" in str(exc):
                self.logger.warning(
                    "$vectorSearch stage not recognized by MongoDB deployment. Using local cosine similarity fallback for templeId='%s'.",
                    temple_id,
                )
                return await self._fallback_in_memory_search(
                    temple_id=temple_id,
                    query_vector=query_vector,
                    limit=limit,
                    category=category,
                    min_score=min_score,
                )
            raise

    async def _fallback_in_memory_search(
        self,
        temple_id: str,
        query_vector: List[float],
        limit: int,
        category: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> List[VectorSearchResult]:
        """In-memory cosine similarity fallback when running on local MongoDB without Atlas Search."""
        query_filter: Dict[str, Any] = {"templeId": temple_id}
        if category:
            query_filter["category"] = category

        cursor = self.chunks_collection.find(query_filter)
        raw_chunks = await cursor.to_list(length=1000)

        scored_results: List[VectorSearchResult] = []
        for raw in raw_chunks:
            embedding = raw.get("embedding")
            if not embedding:
                continue
            score = cosine_similarity(query_vector, embedding)
            if min_score is not None and score < min_score:
                continue

            raw_id = str(raw.pop("_id", None))
            raw["id"] = raw_id
            raw["score"] = score
            chunk = KnowledgeChunk.model_validate(raw)
            scored_results.append(VectorSearchResult(chunk=chunk, score=score))

        # Sort descending by score and limit results
        scored_results.sort(key=lambda x: x.score, reverse=True)
        return scored_results[:limit]

    # ==========================================================================
    # Chunk Management
    # ==========================================================================

    async def delete_chunks_by_document(self, temple_id: str, document_id: str) -> int:
        """Remove all chunks associated with a specific document within a temple."""
        res = await self.chunks_collection.delete_many(
            {"templeId": temple_id, "documentId": document_id}
        )
        return res.deleted_count

    async def delete_chunks_by_temple(self, temple_id: str) -> int:
        """Purge all knowledge chunks for a given temple."""
        res = await self.chunks_collection.delete_many({"templeId": temple_id})
        return res.deleted_count


# Global singleton instance
vector_search_service = VectorSearchService()

"""RAG (Retrieval-Augmented Generation) Question-Answering Service for Temple Knowledge Bases."""

import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.errors import BadRequestException
from app.models.knowledge import KnowledgeChunk, VectorSearchResult
from app.models.rag import RAGAnswerResponse, RAGQueryRequest, RAGSourceCitation
from app.services.base import BaseService
from app.services.llm_service import LLMService, llm_service
from app.services.vector_search_service import VectorSearchService, vector_search_service


SYSTEM_PROMPT_TEMPLATE = """You are the official AI Assistant for the temple. Your sacred duty is to assist devotees and visitors by answering their questions accurately, respectfully, and faithfully.

STRICT INSTRUCTIONS:
1. ONLY answer using the verified facts in the TEMPLE CONTEXT provided below.
2. Do NOT extrapolate, speculate, or invent any facts, timings, prices, rituals, or guidelines that are not explicitly stated in the context.
3. If the provided context does NOT contain enough information to answer the question with certainty, clearly respond:
   "I apologize, but this information is not available in the current temple records. Please consult the temple administration office or the official inquiry counter for assistance."
4. Maintain a warm, polite, and devotional tone appropriate for a sacred temple.
5. Keep your answers clear, concise, and well-structured. Never refer to "the context provided" or "according to the text snippet"; speak naturally as the temple assistant."""

NO_CONTEXT_FALLBACK_ANSWER = (
    "I apologize, but this information is not available in the current temple records. "
    "Please consult the temple administration office or the official inquiry counter for assistance."
)


class RAGService(BaseService):
    """Dedicated service orchestrating vector retrieval, context synthesis, and grounded LLM generation."""

    def __init__(
        self,
        vector_service: Optional[VectorSearchService] = None,
        llm_svc: Optional[LLMService] = None,
    ) -> None:
        super().__init__()
        self._vector_service = vector_service or vector_search_service
        self._llm_service = llm_svc or llm_service

    async def answer_question(
        self,
        temple_id: str,
        question: str,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        category: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> RAGAnswerResponse:
        """Execute end-to-end RAG question answering for a specific temple.

        Pipeline:
        1. Input validation (temple_id and question required).
        2. Semantic vector search strictly filtered by templeId.
        3. Relevance filtering using similarity threshold.
        4. Context assembly and citation compilation.
        5. LLM prompt synthesis with strict grounding instructions and conversation history.
        6. Completion generation and response shaping.

        Args:
            temple_id: Identifier of the temple to answer questions for.
            question: Devotee or visitor question.
            top_k: Number of candidate chunks to retrieve.
            similarity_threshold: Minimum cosine similarity score (0.0 to 1.0).
            category: Optional category filter (e.g. 'rituals', 'history').
            conversation_history: Optional list of recent dialogue messages for multi-turn context.

        Returns:
            RAGAnswerResponse: Structured answer with attribution sources and metadata.
        """
        start_time = time.time()

        # 1. Input Validation
        if not temple_id or not temple_id.strip():
            raise BadRequestException("templeId is mandatory for question answering.")
        if not question or not question.strip():
            raise BadRequestException("Question cannot be empty.")

        clean_temple_id = temple_id.strip()
        clean_question = question.strip()
        limit = top_k if (top_k is not None and top_k > 0) else settings.RAG_DEFAULT_TOP_K
        threshold = similarity_threshold if similarity_threshold is not None else settings.RAG_DEFAULT_SIMILARITY_THRESHOLD

        self.logger.info(
            "Processing RAG query for temple '%s' | Question: '%.60s...' | top_k: %d | threshold: %.2f",
            clean_temple_id,
            clean_question,
            limit,
            threshold,
        )

        # 2. Semantic Vector Search (Filtered by templeId)
        search_results: List[VectorSearchResult] = await self._vector_service.search(
            temple_id=clean_temple_id,
            query=clean_question,
            top_k=limit,
            category=category,
            min_score=threshold,
        )

        # Contextual query fallback: if short follow-up query yields 0 results, retry with prior user question
        if not search_results and conversation_history:
            last_user_query = next(
                (m["content"] for m in reversed(conversation_history) if m.get("role") == "user" and m.get("content")),
                None,
            )
            if last_user_query and last_user_query != clean_question:
                self.logger.info("Retrying semantic search with combined context: '%.50s %.50s'", last_user_query, clean_question)
                search_results = await self._vector_service.search(
                    temple_id=clean_temple_id,
                    query=f"{last_user_query} {clean_question}",
                    top_k=limit,
                    category=category,
                    min_score=threshold,
                )

        # 3. Context & Citations Construction
        context_str, citations = self.build_context_and_citations(search_results)
        has_context = len(citations) > 0
        top_score = max((c.score for c in citations), default=None)

        self.logger.info(
            "Retrieved %d relevant chunks for temple '%s' (top_score: %s)",
            len(citations),
            clean_temple_id,
            f"{top_score:.3f}" if top_score is not None else "None",
        )

        # 4. Answer Generation (Handling no-context vs grounded context)
        if not has_context:
            self.logger.info("No chunks met threshold %.2f for query. Returning standard no-context response.", threshold)
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            return RAGAnswerResponse(
                answer=NO_CONTEXT_FALLBACK_ANSWER,
                templeId=clean_temple_id,
                question=clean_question,
                sources=[],
                hasRelevantContext=False,
                topScore=None,
                latencyMs=elapsed_ms,
                metadata={
                    "chunksRetrieved": 0,
                    "thresholdUsed": threshold,
                    "model": "grounding_guardrail",
                },
            )

        # 5. Build System & User Prompts
        system_prompt = self.build_system_prompt()
        user_prompt = self.build_user_prompt(clean_question, context_str, conversation_history)

        # 6. Generate Grounded LLM Response
        llm_resp = await self._llm_service.generate_answer(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return RAGAnswerResponse(
            answer=llm_resp.content,
            templeId=clean_temple_id,
            question=clean_question,
            sources=citations,
            hasRelevantContext=True,
            topScore=top_score,
            latencyMs=elapsed_ms,
            metadata={
                "chunksRetrieved": len(citations),
                "thresholdUsed": threshold,
                "model": llm_resp.model,
                "usage": llm_resp.usage,
            },
        )

    def build_system_prompt(self) -> str:
        """Construct the strict system prompt for grounding temple responses."""
        return SYSTEM_PROMPT_TEMPLATE

    def build_user_prompt(
        self,
        question: str,
        context: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Assemble the user prompt containing context blocks, conversation history, and devotee question."""
        prompt_parts: List[str] = [
            f"TEMPLE CONTEXT:\n{context}",
        ]

        if conversation_history:
            history_lines: List[str] = []
            for msg in conversation_history:
                role = msg.get("role", "user")
                role_label = "Devotee" if role == "user" else "Assistant"
                content = (msg.get("content") or "").strip()
                if content:
                    history_lines.append(f"{role_label}: {content}")
            if history_lines:
                prompt_parts.append("RECENT CONVERSATION HISTORY:\n" + "\n".join(history_lines))

        prompt_parts.append(f"DEVOTEE QUESTION:\n{question}\n\nANSWER:")
        return "\n\n".join(prompt_parts)

    def build_context_and_citations(
        self,
        search_results: List[VectorSearchResult],
    ) -> Tuple[str, List[RAGSourceCitation]]:
        """Format retrieved search results into clean prompt context and source citations.

        Args:
            search_results: Ranked vector search results.

        Returns:
            Tuple[str, List[RAGSourceCitation]]: (assembled_context_string, list_of_citations)
        """
        if not search_results:
            return "", []

        context_blocks: List[str] = []
        citations: List[RAGSourceCitation] = []

        # Enforce max chunks cap to avoid overflowing context window
        capped_results = search_results[: settings.RAG_MAX_CONTEXT_CHUNKS]

        for idx, result in enumerate(capped_results, start=1):
            chunk = result.chunk
            score = round(result.score, 4)

            # Extract source URL if present in metadata
            source_url = None
            if chunk.metadata and isinstance(chunk.metadata, dict):
                source_url = chunk.metadata.get("url") or chunk.metadata.get("sourceUrl")

            # Create citation
            snippet = chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content
            citation = RAGSourceCitation(
                title=chunk.title or "Temple Record",
                source=chunk.source,
                sourceUrl=source_url,
                category=chunk.category,
                chunkIndex=chunk.chunk_index,
                score=score,
                contentSnippet=snippet,
                documentId=chunk.document_id,
            )
            citations.append(citation)

            # Build context block
            header_parts = [f"Source [{idx}]: {chunk.title or 'Temple Record'}"]
            if chunk.category:
                header_parts.append(f"Category: {chunk.category}")
            if chunk.source:
                header_parts.append(f"Origin: {chunk.source}")

            header_line = " | ".join(header_parts)
            block = f"--- {header_line} ---\n{chunk.content}"
            context_blocks.append(block)

        assembled_context = "\n\n".join(context_blocks)
        return assembled_context, citations


# Global singleton instance
rag_service = RAGService()

"""RAG Question Answering API endpoints."""

from fastapi import APIRouter, status

from app.models.rag import RAGAnswerResponse, RAGQueryRequest
from app.services.rag_service import rag_service

router = APIRouter(prefix="/rag", tags=["RAG Question Answering"])


@router.post(
    "/query",
    response_model=RAGAnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask Question (Temple RAG)",
    description=(
        "Ask a question to the Temple Assistant. Retrieves relevant knowledge chunks strictly "
        "filtered by templeId, checks similarity threshold, builds grounded context, and generates "
        "an accurate, faithful answer using the configured LLM."
    ),
)
async def query_temple_rag(request: RAGQueryRequest) -> RAGAnswerResponse:
    """Execute RAG question-answering for a temple with grounded citations."""
    return await rag_service.answer_question(
        temple_id=request.temple_id,
        question=request.question,
        top_k=request.top_k,
        similarity_threshold=request.similarity_threshold,
        category=request.category,
    )

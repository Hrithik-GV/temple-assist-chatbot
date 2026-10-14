"""Public Chatbot API endpoint for the Temple Chatbot Platform and embeddable widgets."""

import re
from typing import List
from fastapi import APIRouter, Depends, status

from app.core.errors import AppException, BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.core.rate_limiter import RateLimiter
from app.models.chat import ChatRequest, ChatResponse, ChatSource
from app.services.conversation_service import conversation_service
from app.services.database_service import database_service
from app.services.rag_service import rag_service

logger = get_logger(__name__)

router = APIRouter(tags=["Public Chatbot"])

# Rate limiter instance for public chat (configurable per minute)
chat_rate_limiter = RateLimiter()

# Temple ID format validator (alphanumeric, dashes, underscores)
TEMPLE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


async def validate_temple_id(temple_id: str) -> str:
    """Validate templeId format and verify active status if temple record exists."""
    clean_id = (temple_id or "").strip()
    if not clean_id:
        raise BadRequestException("templeId is required.")

    if len(clean_id) < 2 or len(clean_id) > 100 or not TEMPLE_ID_PATTERN.match(clean_id):
        raise BadRequestException(
            f"Invalid templeId '{clean_id}'. Temple ID must be alphanumeric and between 2 and 100 characters."
        )

    # If database is connected, check if temple exists and verify active status
    try:
        temple = await database_service.get_temple_by_id(clean_id)
        if not temple:
            temple = await database_service.get_temple_by_slug(clean_id)

        if temple and not temple.get("isActive", True):
            raise BadRequestException("This temple chatbot is currently inactive.")
    except (BadRequestException, NotFoundException):
        raise
    except Exception as exc:
        # Non-fatal DB lookup issue in development/testing or unseeded temple: log and proceed
        logger.debug("Temple lookup check bypassed: %s", exc)

    return clean_id


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(chat_rate_limiter)],
    summary="Public Chatbot Inquiry",
    description=(
        "Public endpoint for answering visitor and devotee questions about a temple. "
        "Intended for website chat widgets and mobile apps. Returns grounded answers "
        "backed by verified temple records without exposing internal details."
    ),
)
async def public_chat(request: ChatRequest) -> ChatResponse:
    """Execute public chatbot question answering for a specific temple."""
    # 1. Validate templeId
    temple_id = await validate_temple_id(request.temple_id)

    # 2. Validate message content
    clean_message = request.message.strip()
    if not clean_message:
        raise BadRequestException("Message cannot be empty or blank whitespace.")

    try:
        # 3. Resolve conversation session (enforces strict temple tenancy isolation)
        conv = await conversation_service.get_or_create_conversation(
            temple_id=temple_id,
            conversation_id=request.conversation_id,
            session_id=request.session_id,
        )
        active_conv_id = str(conv.get("conversationId") or conv.get("_id"))
        active_sess_id = conv.get("sessionId") or request.session_id

        # 4. Load recent conversation history if available
        history = await conversation_service.load_recent_history(
            temple_id=temple_id,
            conversation_id=active_conv_id,
        )

        # 5. Query RAG service with strict temple scoping and multi-turn context
        rag_result = await rag_service.answer_question(
            temple_id=temple_id,
            question=clean_message,
            conversation_history=history,
        )

        # 6. Map citations to clean public chat source schemas
        sources: List[ChatSource] = [
            ChatSource(
                title=cit.title,
                source=cit.source,
                url=cit.source_url,
                snippet=cit.content_snippet,
                score=cit.score,
            )
            for cit in rag_result.sources
        ]

        # 7. Persist dialogue messages with PII redaction and retention timestamps
        await conversation_service.store_user_message(
            temple_id=temple_id,
            conversation_id=active_conv_id,
            content=clean_message,
        )
        sources_dicts = [src.model_dump(by_alias=True) for src in sources]
        await conversation_service.store_assistant_message(
            temple_id=temple_id,
            conversation_id=active_conv_id,
            content=rag_result.answer,
            sources=sources_dicts,
        )

        # 8. Return sanitized public response with conversationId for multi-turn continuity
        return ChatResponse(
            answer=rag_result.answer,
            sources=sources,
            templeId=temple_id,
            conversationId=active_conv_id,
            sessionId=active_sess_id,
            hasRelevantContext=rag_result.has_relevant_context,
        )

    except AppException:
        # Re-raise known application exceptions for standardized JSON handling
        raise
    except Exception as exc:
        # Catch unexpected errors to prevent leaking raw tracebacks, DB internals or API keys
        logger.error("Unexpected error in public chat for temple '%s': %s", temple_id, exc, exc_info=True)
        raise AppException(
            message="An unexpected error occurred while processing your request. Please try again later.",
            error_code="CHAT_SERVICE_ERROR",
        )

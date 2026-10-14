"""Dedicated service for managing multi-turn chat sessions, message persistence,
PII redaction, configurable retention, and multi-tenant isolation.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import uuid

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.core.config import settings
from app.core.database import mongodb
from app.core.errors import BadRequestException, NotFoundException
from app.models.collections import Collections
from app.models.message import MessageRole
from app.services.base import BaseService
from app.utils.helpers import get_utc_now
from app.utils.pii import sanitize_session_metadata, scrub_pii


class ConversationService(BaseService):
    """Manages conversational session lifecycle, message logs, and cross-temple isolation."""

    def __init__(self) -> None:
        super().__init__()
        self._db_manager = mongodb

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """Active Motor database instance."""
        return self._db_manager.get_database()

    @property
    def conversations_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for conversations."""
        return self._db_manager.get_collection(Collections.CONVERSATIONS)

    @property
    def messages_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for dialogue messages."""
        return self._db_manager.get_collection(Collections.MESSAGES)

    # --------------------------------------------------------------------------
    # ID Generation Helpers
    # --------------------------------------------------------------------------

    @staticmethod
    def generate_conversation_id() -> str:
        """Generate a cryptographically secure, unique conversation ID."""
        return f"conv_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def generate_session_id() -> str:
        """Generate a unique client/device session ID."""
        return f"sess_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def calculate_expiry(days: Optional[int] = None) -> Optional[datetime]:
        """Calculate the UTC timestamp when conversational history expires.

        Args:
            days: Optional retention days override. If None, uses config setting.

        Returns:
            datetime if retention is positive, or None for indefinite retention.
        """
        retention_days = days if days is not None else settings.CONVERSATION_RETENTION_DAYS
        if retention_days > 0:
            return get_utc_now() + timedelta(days=retention_days)
        return None

    # --------------------------------------------------------------------------
    # Tenancy & Query Building Helpers
    # --------------------------------------------------------------------------

    @staticmethod
    def _build_conv_id_query(conversation_id: str) -> Dict[str, Any]:
        """Construct a query condition matching conversationId either by explicit string or ObjectId."""
        conditions: List[Dict[str, Any]] = [
            {"conversationId": conversation_id},
            {"_id": conversation_id},
        ]
        if ObjectId.is_valid(conversation_id):
            conditions.append({"_id": ObjectId(conversation_id)})
        return {"$or": conditions}

    # --------------------------------------------------------------------------
    # Conversation Lifecycle Operations
    # --------------------------------------------------------------------------

    async def get_or_create_conversation(
        self,
        temple_id: str,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_language: str = "en",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Retrieve an existing conversation or create a new session.

        Guarantees strict multi-temple isolation:
        - If a conversationId is supplied, it MUST belong to the specified templeId.
        - Attempting to access another temple's conversation raises a NotFoundException.

        Args:
            temple_id: Mandatory temple identifier.
            conversation_id: Optional existing conversation identifier.
            session_id: Optional client session identifier.
            user_language: Devotee's preferred UI language.
            metadata: Optional session telemetry.

        Returns:
            Dict containing the conversation document.

        Raises:
            BadRequestException: If templeId is missing.
            NotFoundException: If conversationId does not exist or belongs to another temple.
        """
        clean_temple_id = (temple_id or "").strip()
        if not clean_temple_id:
            raise BadRequestException("templeId is mandatory for conversation management.")

        clean_conv_id = (conversation_id or "").strip() if conversation_id else None
        clean_sess_id = (session_id or "").strip() if session_id else None

        # 1. If conversation_id is provided, verify it exists and belongs strictly to temple_id
        if clean_conv_id:
            conv_filter: Dict[str, Any] = {
                "templeId": clean_temple_id,
                **self._build_conv_id_query(clean_conv_id),
            }
            existing_conv = await self.conversations_collection.find_one(conv_filter)

            if not existing_conv:
                # Security Check: Check if conversation exists under ANY other temple
                cross_temple_conv = await self.conversations_collection.find_one(
                    self._build_conv_id_query(clean_conv_id)
                )
                if cross_temple_conv and cross_temple_conv.get("templeId") != clean_temple_id:
                    self.logger.warning(
                        "Cross-temple access violation attempt! Client requested conversation '%s' "
                        "with templeId '%s', but conversation belongs to '%s'. Access blocked.",
                        clean_conv_id,
                        clean_temple_id,
                        cross_temple_conv.get("templeId"),
                    )

                raise NotFoundException(
                    f"Conversation '{clean_conv_id}' not found for temple '{clean_temple_id}'."
                )

            return existing_conv

        # 2. If no conversation_id, but session_id is provided, check for active session under this temple
        if clean_sess_id:
            existing_by_session = await self.conversations_collection.find_one(
                {"templeId": clean_temple_id, "sessionId": clean_sess_id, "isActive": True}
            )
            if existing_by_session:
                return existing_by_session

        # 3. Create a brand new conversation session
        new_conv_id = self.generate_conversation_id()
        final_sess_id = clean_sess_id or self.generate_session_id()
        sanitized_meta = sanitize_session_metadata(metadata)
        expires_at = self.calculate_expiry()

        now = get_utc_now()
        new_conv: Dict[str, Any] = {
            "_id": new_conv_id,
            "conversationId": new_conv_id,
            "templeId": clean_temple_id,
            "sessionId": final_sess_id,
            "userLanguage": user_language,
            "isActive": True,
            "messageCount": 0,
            "metadata": sanitized_meta,
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": expires_at,
        }

        await self.conversations_collection.insert_one(new_conv)
        self.logger.info(
            "Created new conversation '%s' for temple '%s' (sessionId: '%s')",
            new_conv_id,
            clean_temple_id,
            final_sess_id,
        )
        return new_conv

    async def get_conversation(
        self,
        temple_id: str,
        conversation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve conversation by ID strictly scoped to temple_id."""
        clean_temple_id = (temple_id or "").strip()
        clean_conv_id = (conversation_id or "").strip()
        if not clean_temple_id or not clean_conv_id:
            return None

        query = {
            "templeId": clean_temple_id,
            **self._build_conv_id_query(clean_conv_id),
        }
        return await self.conversations_collection.find_one(query)

    # --------------------------------------------------------------------------
    # Message Storage Operations (with PII Redaction)
    # --------------------------------------------------------------------------

    async def store_user_message(
        self,
        temple_id: str,
        conversation_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a user message with PII scrubbing and automatic retention timestamp.

        Args:
            temple_id: Scoped temple ID.
            conversation_id: Associated conversation ID.
            content: Raw message text from devotee/visitor.
            metadata: Optional telemetry metadata.

        Returns:
            The created message document.
        """
        clean_temple_id = temple_id.strip()
        clean_conv_id = conversation_id.strip()

        # Scrub PII (phone numbers, emails, cards, national IDs)
        scrubbed_content = scrub_pii(content.strip())
        sanitized_meta = sanitize_session_metadata(metadata)
        expires_at = self.calculate_expiry()
        now = get_utc_now()

        message_doc: Dict[str, Any] = {
            "templeId": clean_temple_id,
            "conversationId": clean_conv_id,
            "role": MessageRole.USER.value,
            "content": scrubbed_content,
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": expires_at,
            "metadata": sanitized_meta,
        }

        res = await self.messages_collection.insert_one(message_doc)
        message_doc["_id"] = res.inserted_id

        # Update conversation message count and updatedAt
        await self.conversations_collection.update_one(
            {"templeId": clean_temple_id, **self._build_conv_id_query(clean_conv_id)},
            {"$inc": {"messageCount": 1}, "$set": {"updatedAt": now}},
        )

        return message_doc

    async def store_assistant_message(
        self,
        temple_id: str,
        conversation_id: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store an assistant response with sources and automatic retention timestamp.

        Args:
            temple_id: Scoped temple ID.
            conversation_id: Associated conversation ID.
            content: Generated assistant answer.
            sources: Attribution source citations.
            metadata: Optional generation telemetry.

        Returns:
            The created message document.
        """
        clean_temple_id = temple_id.strip()
        clean_conv_id = conversation_id.strip()
        sanitized_meta = sanitize_session_metadata(metadata)
        expires_at = self.calculate_expiry()
        now = get_utc_now()

        message_doc: Dict[str, Any] = {
            "templeId": clean_temple_id,
            "conversationId": clean_conv_id,
            "role": MessageRole.ASSISTANT.value,
            "content": content.strip(),
            "sources": sources or [],
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": expires_at,
            "metadata": sanitized_meta,
        }

        res = await self.messages_collection.insert_one(message_doc)
        message_doc["_id"] = res.inserted_id

        # Update conversation message count and updatedAt
        await self.conversations_collection.update_one(
            {"templeId": clean_temple_id, **self._build_conv_id_query(clean_conv_id)},
            {"$inc": {"messageCount": 1}, "$set": {"updatedAt": now}},
        )

        return message_doc

    # --------------------------------------------------------------------------
    # History Retrieval (Configurable Turns & Cross-Temple Isolation)
    # --------------------------------------------------------------------------

    async def load_recent_history(
        self,
        temple_id: str,
        conversation_id: str,
        max_turns: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve the recent conversation history strictly scoped to templeId.

        Retrieves the most recent (max_turns * 2) messages and returns them
        in chronological order for prompt synthesis.

        Args:
            temple_id: Identifier of the temple (mandatory for isolation).
            conversation_id: Identifier of the conversation.
            max_turns: Maximum conversation turns to load (default: MAX_CONVERSATION_HISTORY_TURNS).

        Returns:
            List of message dicts with 'role' and 'content'.
        """
        clean_temple_id = (temple_id or "").strip()
        clean_conv_id = (conversation_id or "").strip()
        if not clean_temple_id or not clean_conv_id:
            return []

        turns_limit = max_turns if (max_turns is not None and max_turns > 0) else settings.MAX_CONVERSATION_HISTORY_TURNS
        # Each turn consists of 1 user message + 1 assistant message
        message_limit = turns_limit * 2

        # Query messages strictly scoped by templeId and conversationId
        cursor = (
            self.messages_collection.find(
                {"templeId": clean_temple_id, "conversationId": clean_conv_id}
            )
            .sort("createdAt", DESCENDING)
            .limit(message_limit)
        )

        recent_messages = await cursor.to_list(length=message_limit)

        # Reverse to chronological order (oldest first among the recent window)
        chronological = list(reversed(recent_messages))

        return [
            {
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
                "sources": msg.get("sources"),
            }
            for msg in chronological
            if msg.get("content")
        ]

    # --------------------------------------------------------------------------
    # Retention Management & Expiration Cleanup
    # --------------------------------------------------------------------------

    async def cleanup_expired_history(
        self,
        temple_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Purge expired conversations and messages according to retention policy.

        Args:
            temple_id: Optional temple ID to scope cleanup. If None, cleans all expired records.

        Returns:
            Dict with deleted conversations and messages count.
        """
        now = get_utc_now()
        base_filter: Dict[str, Any] = {"expiresAt": {"$lte": now}}
        if temple_id:
            base_filter["templeId"] = temple_id.strip()

        conv_res = await self.conversations_collection.delete_many(base_filter)
        msg_res = await self.messages_collection.delete_many(base_filter)

        self.logger.info(
            "Cleaned up expired chat history (temple: %s) | Conversations purged: %d | Messages purged: %d",
            temple_id or "all",
            conv_res.deleted_count,
            msg_res.deleted_count,
        )

        return {
            "conversationsPurged": conv_res.deleted_count,
            "messagesPurged": msg_res.deleted_count,
        }

    async def ensure_indexes(self) -> None:
        """Create necessary compound and TTL indexes for conversations and messages."""
        try:
            # Conversations indexes
            await self.conversations_collection.create_index(
                [("templeId", ASCENDING), ("conversationId", ASCENDING)],
                unique=False,
            )
            await self.conversations_collection.create_index(
                [("templeId", ASCENDING), ("sessionId", ASCENDING)],
                unique=False,
            )
            await self.conversations_collection.create_index(
                [("expiresAt", ASCENDING)],
                expireAfterSeconds=0,  # MongoDB native TTL deletion
            )

            # Messages indexes
            await self.messages_collection.create_index(
                [("templeId", ASCENDING), ("conversationId", ASCENDING), ("createdAt", ASCENDING)],
                unique=False,
            )
            await self.messages_collection.create_index(
                [("expiresAt", ASCENDING)],
                expireAfterSeconds=0,  # MongoDB native TTL deletion
            )
            self.logger.info("Conversation and message indexes verified successfully.")
        except Exception as exc:
            self.logger.warning("Could not ensure conversation indexes: %s", exc)


# Global singleton service instance
conversation_service = ConversationService()

"""Reusable Database Service for high-level repository queries and multi-temple data operations."""

from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from app.core.database import mongodb
from app.models.collections import Collections
from app.services.base import BaseService


class DatabaseService(BaseService):
    """Encapsulates collection access and common multi-temple database queries."""

    def __init__(self) -> None:
        super().__init__()
        self._db_manager = mongodb

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """Active Motor database instance."""
        return self._db_manager.get_database()

    # Collection Accessors
    @property
    def temples_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for temples."""
        return self._db_manager.get_collection(Collections.TEMPLES)

    @property
    def knowledge_documents_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for knowledge documents."""
        return self._db_manager.get_collection(Collections.KNOWLEDGE_DOCUMENTS)

    @property
    def knowledge_chunks_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for knowledge chunks."""
        return self._db_manager.get_collection(Collections.KNOWLEDGE_CHUNKS)

    @property
    def admins_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for administrators."""
        return self._db_manager.get_collection(Collections.ADMINS)

    @property
    def conversations_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for chat conversations."""
        return self._db_manager.get_collection(Collections.CONVERSATIONS)

    @property
    def messages_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for dialogue messages."""
        return self._db_manager.get_collection(Collections.MESSAGES)

    # Multi-Temple Repository Operations
    async def get_temple_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Retrieve a temple by its unique slug."""
        return await self.temples_collection.find_one({"slug": slug})

    async def get_temple_by_id(self, temple_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a temple by its identifier string or ObjectId."""
        from bson import ObjectId

        query: Dict[str, Any] = {"$or": [{"_id": temple_id}]}
        if ObjectId.is_valid(temple_id):
            query["$or"].append({"_id": ObjectId(temple_id)})

        return await self.temples_collection.find_one(query)

    async def list_active_temples(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List active temples."""
        cursor = self.temples_collection.find({"isActive": True}).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_knowledge_documents_by_temple(
        self,
        temple_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve all knowledge documents belonging to a specific temple."""
        cursor = (
            self.knowledge_documents_collection.find({"templeId": temple_id})
            .sort("createdAt", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    async def get_knowledge_chunks_by_temple(
        self,
        temple_id: str,
        document_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Retrieve knowledge chunks scoped to a specific temple."""
        query: Dict[str, Any] = {"templeId": temple_id}
        if document_id:
            query["documentId"] = document_id

        cursor = self.knowledge_chunks_collection.find(query).sort("chunkIndex", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_or_create_conversation(
        self,
        temple_id: str,
        session_id: str,
        user_language: str = "en",
    ) -> Dict[str, Any]:
        """Find an existing conversation or initialize a new one for a temple session."""
        from app.utils.helpers import get_utc_now

        conv = await self.conversations_collection.find_one(
            {"templeId": temple_id, "sessionId": session_id}
        )
        if conv:
            return conv

        new_conv: Dict[str, Any] = {
            "templeId": temple_id,
            "sessionId": session_id,
            "userLanguage": user_language,
            "isActive": True,
            "metadata": {},
            "createdAt": get_utc_now(),
            "updatedAt": get_utc_now(),
        }
        res = await self.conversations_collection.insert_one(new_conv)
        new_conv["_id"] = res.inserted_id
        return new_conv

    async def get_messages_by_conversation(
        self,
        temple_id: str,
        conversation_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve conversation messages ensuring temple tenancy scoping."""
        cursor = (
            self.messages_collection.find(
                {"templeId": temple_id, "conversationId": conversation_id}
            )
            .sort("createdAt", 1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)


database_service = DatabaseService()

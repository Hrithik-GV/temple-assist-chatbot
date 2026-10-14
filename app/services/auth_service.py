"""Authentication and administrator service for multi-temple management."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING

from app.core.database import mongodb
from app.core.errors import BadRequestException, ConflictException, NotFoundException, UnauthorizedException
from app.core.security import hash_password, verify_password
from app.models.admin import AdminRole
from app.models.auth import AdminCreateRequest
from app.models.collections import Collections
from app.services.base import BaseService
from app.utils.helpers import get_utc_now


class AuthService(BaseService):
    """Encapsulates admin account creation, authentication, and password management."""

    def __init__(self) -> None:
        super().__init__()
        self._db_manager = mongodb

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """Active Motor database instance."""
        return self._db_manager.get_database()

    @property
    def admins_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for administrators."""
        return self._db_manager.get_collection(Collections.ADMINS)

    @property
    def temples_collection(self) -> AsyncIOMotorCollection:
        """Collection handle for temples."""
        return self._db_manager.get_collection(Collections.TEMPLES)

    # --------------------------------------------------------------------------
    # Account Lookup Operations
    # --------------------------------------------------------------------------

    async def get_admin_by_id(self, admin_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve admin account by string ID or ObjectId."""
        clean_id = (admin_id or "").strip()
        if not clean_id:
            return None

        query: Dict[str, Any] = {"$or": [{"_id": clean_id}, {"id": clean_id}]}
        if ObjectId.is_valid(clean_id):
            query["$or"].append({"_id": ObjectId(clean_id)})

        return await self.admins_collection.find_one(query)

    async def get_admin_by_username_or_email(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Retrieve admin account by username or email (case-insensitive)."""
        clean_ident = (identifier or "").strip().lower()
        if not clean_ident:
            return None

        return await self.admins_collection.find_one({
            "$or": [
                {"email": clean_ident},
                {"username": clean_ident},
            ]
        })

    # --------------------------------------------------------------------------
    # Authentication Operations
    # --------------------------------------------------------------------------

    async def authenticate_admin(
        self,
        identifier: str,
        password: str,
    ) -> Dict[str, Any]:
        """Authenticate an administrator with username/email and password.

        Args:
            identifier: Username or email.
            password: Plaintext password.

        Returns:
            Admin document if authentication succeeds.

        Raises:
            UnauthorizedException: If user not found, password incorrect, or account disabled.
        """
        admin = await self.get_admin_by_username_or_email(identifier)
        if not admin:
            raise UnauthorizedException("Invalid username, email, or password.")

        if not admin.get("isActive", True):
            raise UnauthorizedException("This administrator account has been deactivated.")

        password_hash = admin.get("passwordHash")
        if not password_hash or not verify_password(password, password_hash):
            raise UnauthorizedException("Invalid username, email, or password.")

        return admin

    # --------------------------------------------------------------------------
    # Admin Lifecycle Operations
    # --------------------------------------------------------------------------

    async def create_admin(
        self,
        request: AdminCreateRequest,
        creator_admin: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new administrator account with salted bcrypt password hash.

        Enforces multi-tenancy rules:
        - If creator is a temple_admin, they can only create admins for their OWN temple.
        - Non-superadmins MUST have a templeId assigned.
        - Emails and usernames must be globally unique.

        Args:
            request: Registration payload.
            creator_admin: Admin making the request (None if initial setup).

        Returns:
            Created admin document.

        Raises:
            ConflictException: If email or username already exists.
            BadRequestException: If templeId is invalid or missing for temple-scoped role.
        """
        clean_email = request.email.strip().lower()
        clean_username = request.username.strip().lower()

        # 1. Check uniqueness of email and username
        existing_email = await self.admins_collection.find_one({"email": clean_email})
        if existing_email:
            raise ConflictException(f"An administrator with email '{clean_email}' already exists.")

        existing_user = await self.admins_collection.find_one({"username": clean_username})
        if existing_user:
            raise ConflictException(f"An administrator with username '{clean_username}' already exists.")

        # 2. Validate Temple Assignment
        temple_id = request.temple_id.strip() if request.temple_id else None

        if request.role != AdminRole.SUPERADMIN and not temple_id:
            raise BadRequestException("templeId is required for temple administrators and editors.")

        if temple_id:
            # Check temple exists
            temple_query: Dict[str, Any] = {"$or": [{"_id": temple_id}, {"slug": temple_id}]}
            if ObjectId.is_valid(temple_id):
                temple_query["$or"].append({"_id": ObjectId(temple_id)})
            temple = await self.temples_collection.find_one(temple_query)
            if not temple:
                raise NotFoundException(f"Temple '{temple_id}' does not exist.")

        # 3. Hash password with bcrypt
        hashed = hash_password(request.password)
        now = get_utc_now()
        admin_id = f"admin_{uuid.uuid4().hex[:16]}"

        new_admin: Dict[str, Any] = {
            "_id": admin_id,
            "id": admin_id,
            "email": clean_email,
            "username": clean_username,
            "fullName": request.full_name.strip() if request.full_name else None,
            "templeId": temple_id,
            "role": request.role.value,
            "isActive": True,
            "passwordHash": hashed,
            "createdAt": now,
            "updatedAt": now,
        }

        await self.admins_collection.insert_one(new_admin)
        self.logger.info(
            "Created admin account '%s' (role: %s, temple: %s)",
            clean_username,
            request.role.value,
            temple_id or "superadmin",
        )
        return new_admin

    async def list_admins(self, temple_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List administrators, optionally filtered by templeId."""
        query: Dict[str, Any] = {}
        if temple_id:
            query["templeId"] = temple_id.strip()

        cursor = self.admins_collection.find(query).sort("createdAt", -1)
        return await cursor.to_list(length=100)

    async def ensure_indexes(self) -> None:
        """Ensure unique indexes on username and email for administrators."""
        try:
            await self.admins_collection.create_index([("email", ASCENDING)], unique=True)
            await self.admins_collection.create_index([("username", ASCENDING)], unique=True)
            await self.admins_collection.create_index([("templeId", ASCENDING)], unique=False)
            self.logger.info("Admin collection indexes ensured successfully.")
        except Exception as exc:
            self.logger.warning("Could not ensure admin indexes: %s", exc)


# Global singleton service instance
auth_service = AuthService()

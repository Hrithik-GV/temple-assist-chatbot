"""Admin user model for multi-temple management platform."""

from enum import Enum
from typing import Optional
from pydantic import EmailStr, Field
from app.models.base import MongoBaseModel


class AdminRole(str, Enum):
    """Authorization role for administrative users."""

    SUPERADMIN = "superadmin"
    TEMPLE_ADMIN = "temple_admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class Admin(MongoBaseModel):
    """Admin account model supporting platform-wide or temple-scoped access."""

    email: str = Field(..., description="Unique email address for administrator")
    username: str = Field(..., description="Unique username identifier")
    full_name: Optional[str] = Field(default=None, alias="fullName", description="Administrator display name")
    temple_id: Optional[str] = Field(
        default=None,
        alias="templeId",
        serialization_alias="templeId",
        description="Assigned temple ID (None indicates system-wide superadmin)",
    )
    role: AdminRole = Field(
        default=AdminRole.TEMPLE_ADMIN,
        description="Role privileges level",
    )
    is_active: bool = Field(default=True, alias="isActive", description="Whether account is active")
    password_hash: Optional[str] = Field(
        default=None,
        alias="passwordHash",
        description="Hashed password placeholder (for future authentication)",
    )

    @property
    def templeId(self) -> Optional[str]:
        """Convenience property for camelCase templeId access."""
        return self.temple_id

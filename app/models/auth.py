"""Pydantic schemas for authentication, admin management, and protected operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.admin import AdminRole


class AdminLoginRequest(BaseModel):
    """Admin login credential payload."""

    model_config = ConfigDict(populate_by_name=True)

    username: str = Field(..., min_length=2, max_length=100, description="Username or email address")
    password: str = Field(..., min_length=6, max_length=128, description="Plaintext password")


class AdminProfileResponse(BaseModel):
    """Public administrator profile representation."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="Admin identifier")
    email: str = Field(..., description="Administrator email")
    username: str = Field(..., description="Administrator username")
    full_name: Optional[str] = Field(default=None, alias="fullName", description="Full name")
    temple_id: Optional[str] = Field(
        default=None,
        alias="templeId",
        description="Assigned temple ID (null for superadmin)",
    )
    role: AdminRole = Field(..., description="Assigned role privileges")
    is_active: bool = Field(default=True, alias="isActive", description="Whether account is active")
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")


class TokenResponse(BaseModel):
    """JWT bearer token response on successful authentication."""

    model_config = ConfigDict(populate_by_name=True)

    access_token: str = Field(..., alias="accessToken", description="Signed JWT Bearer access token")
    token_type: str = Field(default="bearer", alias="tokenType", description="Token authorization type")
    expires_in: int = Field(..., alias="expiresIn", description="Validity duration in seconds")
    admin: AdminProfileResponse = Field(..., description="Authenticated administrator details")


class AdminCreateRequest(BaseModel):
    """Payload for registering a new administrator."""

    model_config = ConfigDict(populate_by_name=True)

    email: str = Field(
        ...,
        pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        description="Administrator email address",
    )
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-]+$", description="Unique username")
    password: str = Field(..., min_length=8, max_length=128, description="Strong password (min 8 characters)")
    full_name: Optional[str] = Field(default=None, alias="fullName", max_length=100)
    temple_id: Optional[str] = Field(
        default=None,
        alias="templeId",
        description="Mandatory temple assignment (only superadmin may be unassigned)",
    )
    role: AdminRole = Field(default=AdminRole.TEMPLE_ADMIN, description="Role privileges")


class AdminPasswordChangeRequest(BaseModel):
    """Payload for changing admin password."""

    model_config = ConfigDict(populate_by_name=True)

    current_password: str = Field(..., alias="currentPassword", description="Current password")
    new_password: str = Field(..., alias="newPassword", min_length=8, description="New strong password")


# ==============================================================================
# Protected Admin Knowledge & Temple Action Schemas
# ==============================================================================


class FAQCreateRequest(BaseModel):
    """Admin payload to add verified FAQ knowledge for a temple."""

    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(..., min_length=3, max_length=500, description="Devotee question")
    answer: str = Field(..., min_length=3, max_length=2000, description="Authoritative verified temple answer")
    category: Optional[str] = Field(default="faq", description="Knowledge category (e.g. rituals, timings, pooja)")


class KnowledgeTextCreateRequest(BaseModel):
    """Admin payload to directly ingest text knowledge for a temple."""

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(..., min_length=3, max_length=200, description="Document title")
    content: str = Field(..., min_length=10, description="Full knowledge text content")
    category: Optional[str] = Field(default="general", description="Knowledge category")


class CrawlTriggerRequest(BaseModel):
    """Payload to trigger website ingestion for a temple."""

    model_config = ConfigDict(populate_by_name=True)

    start_url: str = Field(..., alias="startUrl", description="Starting URL to crawl")
    max_pages: Optional[int] = Field(default=10, alias="maxPages", ge=1, le=50)
    max_depth: Optional[int] = Field(default=2, alias="maxDepth", ge=1, le=5)
    category: Optional[str] = Field(default="website", description="Category for discovered pages")


class FAQUpdateRequest(BaseModel):
    """Admin payload to update an existing FAQ."""

    model_config = ConfigDict(populate_by_name=True)

    question: Optional[str] = Field(default=None, min_length=3, max_length=500, description="Updated question")
    answer: Optional[str] = Field(default=None, min_length=3, max_length=2000, description="Updated answer")
    category: Optional[str] = Field(default=None, description="Updated category")


class FAQResponse(BaseModel):
    """Representation of an FAQ entry."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="FAQ document identifier")
    temple_id: str = Field(..., alias="templeId", description="Associated temple ID")
    question: str = Field(..., description="Devotee question")
    answer: str = Field(..., description="Verified temple answer")
    category: Optional[str] = Field(default="faq", description="Category")
    chunk_count: int = Field(default=1, alias="chunkCount", description="Number of vector chunks")
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")

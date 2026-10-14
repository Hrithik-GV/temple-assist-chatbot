"""Protected Admin API for temple management with multi-tenant isolation."""

from typing import Any, Dict, List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import RequireTempleAccess, get_current_admin, require_superadmin
from app.core.errors import ConflictException, NotFoundException
from app.core.logging import get_logger
from app.models.admin import AdminRole
from app.models.temple import Temple, TempleContact, TempleLocation, TempleTimings
from app.services.database_service import database_service
from app.utils.helpers import get_utc_now

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/temples", tags=["Admin Temples"])


class TempleCreateRequest(BaseModel):
    """Payload to register a new temple on the platform."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=2, max_length=150, description="Temple official name")
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9_\-]+$", description="URL slug")
    deity: Optional[str] = Field(default=None, description="Primary deity consecrated")
    description: Optional[str] = Field(default=None, description="Temple overview")
    location: Optional[TempleLocation] = None
    timings: Optional[TempleTimings] = None
    contact: Optional[TempleContact] = None
    languages: List[str] = Field(default_factory=lambda: ["en", "te", "hi"])


class TempleUpdateRequest(BaseModel):
    """Payload to update an existing temple."""

    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    deity: Optional[str] = None
    description: Optional[str] = None
    location: Optional[TempleLocation] = None
    timings: Optional[TempleTimings] = None
    contact: Optional[TempleContact] = None
    languages: Optional[List[str]] = None
    is_active: Optional[bool] = Field(default=None, alias="isActive")


@router.post(
    "",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_superadmin)],
    summary="Create Temple (Superadmin Only)",
    description="Register a new temple entity on the platform. Requires Superadmin role.",
)
async def create_temple(
    request: TempleCreateRequest,
) -> Dict[str, Any]:
    """Register a new temple entity."""
    clean_slug = request.slug.strip().lower()

    # Check slug uniqueness
    existing = await database_service.get_temple_by_slug(clean_slug)
    if existing:
        raise ConflictException(f"A temple with slug '{clean_slug}' already exists.")

    temple_doc = Temple(
        name=request.name.strip(),
        slug=clean_slug,
        deity=request.deity.strip() if request.deity else None,
        description=request.description.strip() if request.description else None,
        location=request.location,
        timings=request.timings,
        contact=request.contact,
        languages=request.languages,
        isActive=True,
    ).to_mongo_dict()

    res = await database_service.temples_collection.insert_one(temple_doc)
    temple_doc["_id"] = str(res.inserted_id)

    logger.info("Superadmin created new temple: '%s' (slug: %s)", request.name, clean_slug)
    return temple_doc


@router.get(
    "",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List Temples",
    description="List temples. Superadmins see all temples; temple admins see only their assigned temple.",
)
async def list_temples(
    current_admin: Dict[str, Any] = Depends(get_current_admin),
) -> List[Dict[str, Any]]:
    """List temples with multi-tenant tenancy scoping."""
    admin_role = current_admin.get("role")
    admin_temple = current_admin.get("templeId")

    if admin_role == AdminRole.SUPERADMIN.value:
        cursor = database_service.temples_collection.find({}).sort("name", 1)
        temples = await cursor.to_list(length=100)
    else:
        # Strict isolation: only return the assigned temple
        if not admin_temple:
            return []
        temple = await database_service.get_temple_by_id(admin_temple)
        if not temple:
            temple = await database_service.get_temple_by_slug(admin_temple)
        temples = [temple] if temple else []

    # Format ObjectIds to strings
    for t in temples:
        t["_id"] = str(t.get("_id"))
    return temples


@router.get(
    "/{templeId}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get Temple Details",
    description="Retrieve temple details. Strictly enforced: admins cannot view another temple's record.",
)
async def get_temple_details(
    temple_id: str = Path(..., alias="templeId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Retrieve details for a specific temple."""
    temple = await database_service.get_temple_by_id(temple_id)
    if not temple:
        temple = await database_service.get_temple_by_slug(temple_id)

    if not temple:
        raise NotFoundException(f"Temple '{temple_id}' not found.")

    temple["_id"] = str(temple.get("_id"))
    return temple


@router.put(
    "/{templeId}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Update Temple Details",
    description="Update temple metadata, timings, or location. Enforces temple-level authorization.",
)
async def update_temple_details(
    update_data: TempleUpdateRequest,
    temple_id: str = Path(..., alias="templeId"),
    _authorized: Dict[str, Any] = Depends(RequireTempleAccess()),
) -> Dict[str, Any]:
    """Update temple details."""
    temple = await database_service.get_temple_by_id(temple_id)
    if not temple:
        temple = await database_service.get_temple_by_slug(temple_id)

    if not temple:
        raise NotFoundException(f"Temple '{temple_id}' not found.")

    actual_id = temple["_id"]
    update_fields: Dict[str, Any] = {"updatedAt": get_utc_now()}

    data = update_data.model_dump(by_alias=True, exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            update_fields[k] = v

    await database_service.temples_collection.update_one(
        {"_id": actual_id},
        {"$set": update_fields},
    )

    updated = await database_service.temples_collection.find_one({"_id": actual_id})
    if updated:
        updated["_id"] = str(updated["_id"])
    return updated or {}


@router.delete(
    "/{templeId}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_superadmin)],
    summary="Deactivate Temple (Superadmin Only)",
    description="Deactivate a temple chatbot platform account. Superadmin only.",
)
async def deactivate_temple(
    temple_id: str = Path(..., alias="templeId"),
) -> Dict[str, Any]:
    """Deactivate a temple."""
    temple = await database_service.get_temple_by_id(temple_id)
    if not temple:
        temple = await database_service.get_temple_by_slug(temple_id)

    if not temple:
        raise NotFoundException(f"Temple '{temple_id}' not found.")

    actual_id = temple["_id"]
    await database_service.temples_collection.update_one(
        {"_id": actual_id},
        {"$set": {"isActive": False, "updatedAt": get_utc_now()}},
    )

    logger.info("Superadmin deactivated temple '%s'", temple_id)
    return {"success": True, "message": f"Temple '{temple_id}' has been deactivated."}

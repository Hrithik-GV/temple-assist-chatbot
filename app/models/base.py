"""Base Pydantic model for MongoDB documents."""

from datetime import datetime
from typing import Any, Optional
from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field
from app.utils.helpers import get_utc_now


class MongoBaseModel(BaseModel):
    """Base model for MongoDB documents supporting ObjectId and camelCase serialization."""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )

    id: Optional[str] = Field(default=None, alias="_id", description="MongoDB ObjectId")
    created_at: datetime = Field(
        default_factory=get_utc_now,
        alias="createdAt",
        description="UTC creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=get_utc_now,
        alias="updatedAt",
        description="UTC last updated timestamp",
    )

    def to_mongo_dict(self) -> dict[str, Any]:
        """Convert model to dictionary suitable for MongoDB inserts/updates.

        Uses alias names (like _id, templeId) and excludes unset _id so MongoDB can auto-generate it.
        """
        data = self.model_dump(by_alias=True, exclude_none=True)
        if "_id" in data and data["_id"] is None:
            data.pop("_id")
        return data

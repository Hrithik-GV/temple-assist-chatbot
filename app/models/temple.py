"""Temple model and sub-schemas for multi-temple management."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.base import MongoBaseModel


class TempleLocation(BaseModel):
    """Geographic and address details for a temple."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    address: Optional[str] = None
    city: str = Field(..., description="City or town where temple is located")
    state: str = Field(..., description="State or province")
    country: str = Field(default="India", description="Country")
    postal_code: Optional[str] = Field(default=None, alias="postalCode")
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class TempleTimings(BaseModel):
    """Temple schedule and darshan timings."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    morning_hours: Optional[str] = Field(default=None, alias="morningHours")
    evening_hours: Optional[str] = Field(default=None, alias="eveningHours")
    darshan_timings: Optional[str] = Field(default=None, alias="darshanTimings")
    special_pooja_timings: Optional[str] = Field(default=None, alias="specialPoojaTimings")
    notes: Optional[str] = None


class TempleContact(BaseModel):
    """Temple administration contact information."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    phone: Optional[str] = None
    email: Optional[str] = None
    website_url: Optional[str] = Field(default=None, alias="websiteUrl")


class Temple(MongoBaseModel):
    """Temple document model representing a distinct temple entity in the platform."""

    name: str = Field(..., description="Official temple name")
    slug: str = Field(..., description="URL-friendly unique identifier slug")
    description: Optional[str] = Field(default=None, description="Overview or history of the temple")
    deity: Optional[str] = Field(default=None, description="Primary consecrated deity")
    location: Optional[TempleLocation] = None
    timings: Optional[TempleTimings] = None
    contact: Optional[TempleContact] = None
    languages: List[str] = Field(
        default_factory=lambda: ["en", "te", "hi"],
        description="Supported languages for chatbot interaction",
    )
    is_active: bool = Field(default=True, alias="isActive", description="Whether temple chatbot is active")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary custom attributes")

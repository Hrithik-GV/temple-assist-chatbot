"""Common schemas for standard API responses and pagination/errors."""

from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class ErrorDetail(BaseModel):
    """Detailed error object representation."""

    code: str = Field(..., description="Unique machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: Optional[Any] = Field(default=None, description="Optional extra error details")


class StandardResponse(BaseModel, Generic[DataT]):
    """Standard generic API response envelope."""

    success: bool = Field(default=True, description="Indicates if the operation succeeded")
    data: Optional[DataT] = Field(default=None, description="Response payload")
    error: Optional[ErrorDetail] = Field(default=None, description="Error details if failure occurred")

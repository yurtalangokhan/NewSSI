"""Common response primitives and envelopes for agent-service."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class SuccessResponse(BaseModel):
    """Standard success/failure action response."""

    success: bool = Field(default=True, description="Indicates if the operation succeeded.")
    message: str | None = Field(default=None, description="Optional informational or success message.")
    error: str | None = Field(default=None, description="Optional error message if operation failed.")


class StatusResponse(BaseModel):
    """Standard status confirmation response."""

    status: str = Field(default="ok", description="Status code or string indicator, e.g. 'ok', 'deleted'.")
    id: str | int | None = Field(default=None, description="Identifier of the affected resource if applicable.")
    message: str | None = Field(default=None, description="Additional status details.")


class DeleteResponse(BaseModel):
    """Standard resource deletion response."""

    status: str = Field(default="deleted", description="Status indicator.")
    id: str | int | None = Field(default=None, description="Deleted resource identifier.")
    success: bool = Field(default=True, description="Whether deletion was successful.")


class IdResponse(BaseModel):
    """Simple ID response."""

    id: str | int = Field(description="Unique identifier.")


class CountResponse(BaseModel):
    """Simple count/metrics response."""

    count: int = Field(default=0, description="Total count.")


class GenericPaginatedResponse(BaseModel, Generic[T]):
    """Generic pagination wrapper for collection endpoints."""

    items: list[T] = Field(default_factory=list, description="Paginated items.")
    total: int = Field(default=0, description="Total number of items across all pages.")
    page: int = Field(default=1, description="Current page number (1-indexed).")
    page_size: int = Field(default=50, description="Number of items per page.")
    total_pages: int = Field(default=1, description="Total number of available pages.")


class HealthCheckResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str = "healthy"


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str = "ready"

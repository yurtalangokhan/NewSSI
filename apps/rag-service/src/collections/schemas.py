from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, Field

# =====================
# Collection TypedDicts
# =====================


class CollectionDetails(TypedDict):
    """TypedDict for collection details."""

    uuid: str
    name: str
    metadata: dict[str, Any]
    # Internal vector-store collection name used by legacy and Milvus flows.
    table_id: NotRequired[str]


# =====================
# Collection Schemas
# =====================


class CollectionCreate(BaseModel):
    """Schema for creating a new collection."""

    name: str = Field(..., description="The unique name of the collection.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata for the collection.")


class CollectionUpdate(BaseModel):
    """Schema for updating an existing collection."""

    name: str | None = Field(None, description="New name for the collection.")
    metadata: dict[str, Any] | None = Field(None, description="Updated metadata for the collection.")


class CollectionResponse(BaseModel):
    """Schema for representing a vector collection."""

    # Collection metadata is stored in Postgres; chunks/embeddings live in Milvus.
    uuid: str = Field(..., description="The unique identifier of the vector collection.")
    name: str = Field(..., description="The name of the collection.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata associated with the collection.")

    class Config:
        # Allows creating model from dict like
        # {'uuid': '...', 'name': '...', 'metadata': {...}}
        from_attributes = True

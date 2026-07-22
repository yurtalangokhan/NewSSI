from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from langconnect.auth import AuthenticatedUser, require_permission
from langconnect.database.collections import CollectionsManager
from langconnect.models import CollectionCreate, CollectionResponse, CollectionUpdate
from langconnect.services.build_lock import (
    ensure_collection_mutable,
    ensure_not_connector_managed_collection,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post(
    "",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def collections_create(
    collection_data: CollectionCreate,
    user: Annotated[
        AuthenticatedUser, Depends(require_permission("collection:create"))
    ],
):
    """Creates a new vector collection by name with optional metadata."""
    collection_info = await CollectionsManager(user.identity).create(
        collection_data.name, collection_data.metadata
    )
    if not collection_info:
        raise HTTPException(status_code=500, detail="Failed to create collection")
    return CollectionResponse(**collection_info)


@router.get("", response_model=list[CollectionResponse])
async def collections_list(
    user: Annotated[AuthenticatedUser, Depends(require_permission("collection:list"))],
):
    """Lists all available vector collections (name and UUID)."""
    return [
        CollectionResponse(**c) for c in await CollectionsManager(user.identity).list()
    ]


@router.get("/{collection_id}", response_model=CollectionResponse)
async def collections_get(
    user: Annotated[AuthenticatedUser, Depends(require_permission("collection:read"))],
    collection_id: UUID,
):
    """Retrieves details (name and UUID) of a specific vector collection."""
    collection = await CollectionsManager(user.identity).get(str(collection_id))
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection '{collection_id}' not found",
        )
    return CollectionResponse(**collection)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def collections_delete(
    user: Annotated[
        AuthenticatedUser, Depends(require_permission("collection:delete"))
    ],
    collection_id: UUID,
):
    """Deletes a specific vector collection by name."""
    await ensure_not_connector_managed_collection(str(collection_id))
    ensure_collection_mutable(str(collection_id))
    await CollectionsManager(user.identity).delete(str(collection_id))
    return "Collection deleted successfully."


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def collections_update(
    user: Annotated[
        AuthenticatedUser, Depends(require_permission("collection:update"))
    ],
    collection_id: UUID,
    collection_data: CollectionUpdate,
):
    """Updates a specific vector collection's name and/or metadata."""
    await ensure_not_connector_managed_collection(str(collection_id))
    ensure_collection_mutable(str(collection_id))
    updated_collection = await CollectionsManager(user.identity).update(
        str(collection_id),
        name=collection_data.name,
        metadata=collection_data.metadata,
    )

    if not updated_collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to update collection '{collection_id}'",
        )

    return CollectionResponse(**updated_collection)

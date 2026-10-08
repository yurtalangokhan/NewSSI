# Copyright (c) 2026 Agentic AI Platform
"""Collection orchestration; typed service failures propagate to routes."""

from src.collections.schemas import (
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
)
from src.collections.service import CollectionsManager


async def create(user_id: str, body: CollectionCreate) -> CollectionResponse:
    """Delegate create to the owning domain service."""
    data = await CollectionsManager(user_id).create_required(body.name, body.metadata)
    return CollectionResponse(**data)


async def list_collections(user_id: str) -> list[CollectionResponse]:
    """Delegate list collections to the owning domain service."""
    return [CollectionResponse(**item) for item in await CollectionsManager(user_id).list()]


async def get(user_id: str, collection_id: str) -> CollectionResponse:
    """Delegate get to the owning domain service."""
    return CollectionResponse(**await CollectionsManager(user_id).get_required(collection_id))


async def delete(user_id: str, collection_id: str, *, force: bool = False) -> None:
    """Delegate delete to the owning domain service."""
    await CollectionsManager(user_id).delete_mutable(collection_id, force=force)


async def update(user_id: str, collection_id: str, body: CollectionUpdate) -> CollectionResponse:
    """Delegate update to the owning domain service."""
    data = await CollectionsManager(user_id).update_mutable(collection_id, name=body.name, metadata=body.metadata)
    return CollectionResponse(**data)

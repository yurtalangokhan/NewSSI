"""Thread API routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import extract_user_id_from_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["threads"])


@router.post("/threads")
async def create_thread(
    thread_id: str | None = None,
    metadata: dict | None = None,
    user_id: str = Depends(extract_user_id_from_token),
) -> dict[str, Any]:
    """Create a new thread."""
    from domain.threads.service import ThreadService

    service = ThreadService()
    return await service.create_thread(thread_id=thread_id, metadata=metadata)


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    user_id: str = Depends(extract_user_id_from_token),
) -> dict[str, Any] | None:
    """Get a thread by ID."""
    from domain.threads.service import ThreadService

    service = ThreadService()
    return await service.get_thread(thread_id)


@router.get("/threads")
async def list_threads(
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(extract_user_id_from_token),
) -> list[dict[str, Any]]:
    """List threads."""
    from domain.threads.service import ThreadService

    service = ThreadService()
    return await service.list_threads(limit=limit, offset=offset, user_id=user_id)


@router.patch("/threads/{thread_id}")
async def update_thread(
    thread_id: str,
    metadata: dict,
    user_id: str = Depends(extract_user_id_from_token),
) -> dict[str, Any] | None:
    """Update thread metadata."""
    from domain.threads.service import ThreadService

    service = ThreadService()
    return await service.update_thread(thread_id, metadata)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user_id: str = Depends(extract_user_id_from_token),
) -> bool:
    """Delete a thread."""
    from domain.threads.service import ThreadService

    service = ThreadService()
    return await service.delete_thread(thread_id)

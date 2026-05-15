"""
User Memory REST API.

Endpoints: /api/user/memories
CRUD for the user_memory domain (long-term memory facts).
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from api.dependencies import verify_api_key
from domain.user_memory.schemas import (
    DeleteAllResponse,
    MemoryCreate,
    MemoryListResponse,
    MemoryRead,
    MemoryUpdate,
)
from domain.user_memory.service import get_user_memory_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["user-memory"])


# ---------------------------------------------------------------------------
# GET /api/user/memories  — list (paginated)
# ---------------------------------------------------------------------------


@router.get("/api/user/memories", response_model=MemoryListResponse)
async def list_memories(
    user_id: Annotated[str | None, Depends(verify_api_key)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> MemoryListResponse:
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    svc = get_user_memory_service()
    result = await svc.list_for_ui(user_id, page=page, page_size=page_size)
    items = [MemoryRead.model_validate(r) for r in result["items"]]
    return MemoryListResponse(items=items, total=result["total"])


# ---------------------------------------------------------------------------
# POST /api/user/memories  — create
# ---------------------------------------------------------------------------


@router.post(
    "/api/user/memories",
    response_model=MemoryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_memory(
    body: MemoryCreate,
    user_id: Annotated[str | None, Depends(verify_api_key)],
) -> MemoryRead:
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    svc = get_user_memory_service()
    try:
        row = await svc.create(user_id, body.content)
    except Exception as exc:
        logger.warning(f"[UserMemoryRoute] create failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Memory with this content already exists.",
        ) from exc
    return MemoryRead.model_validate(row)


# ---------------------------------------------------------------------------
# PATCH /api/user/memories/{id}  — update
# ---------------------------------------------------------------------------


@router.patch("/api/user/memories/{memory_id}", response_model=MemoryRead)
async def update_memory(
    memory_id: UUID,
    body: MemoryUpdate,
    user_id: Annotated[str | None, Depends(verify_api_key)],
) -> MemoryRead:
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    svc = get_user_memory_service()
    row = await svc.update(str(memory_id), user_id, body.content)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return MemoryRead.model_validate(row)


# ---------------------------------------------------------------------------
# DELETE /api/user/memories/{id}  — delete single
# ---------------------------------------------------------------------------


@router.delete("/api/user/memories/{memory_id}")
async def delete_memory(
    memory_id: UUID,
    user_id: Annotated[str | None, Depends(verify_api_key)],
) -> Response:
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    svc = get_user_memory_service()
    deleted = await svc.delete(str(memory_id), user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# DELETE /api/user/memories  — delete all
# ---------------------------------------------------------------------------


@router.delete("/api/user/memories", response_model=DeleteAllResponse)
async def delete_all_memories(
    user_id: Annotated[str | None, Depends(verify_api_key)],
) -> DeleteAllResponse:
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    svc = get_user_memory_service()
    count = await svc.delete_all(user_id)
    return DeleteAllResponse(deleted=count)

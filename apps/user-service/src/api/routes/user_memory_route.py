import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from i18n import t

from src.api.dependencies import require_auth_or_internal_service_token, require_permission
from src.controller import get_user_memory_controller
from src.controller.user_controller import get_user_controller

router = APIRouter(prefix="/users/me/memories", tags=["user-memory"])
internal_router = APIRouter(prefix="/internal/users", tags=["user-memory"])


# ---------------------------------------------------------------------------
# User-facing endpoints
# ---------------------------------------------------------------------------


@router.get("/")
async def list_memories(
    user_id: Annotated[str, Depends(require_permission("memory:read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return await get_user_memory_controller().list_memories(
        uuid.UUID(user_id), page=page, page_size=page_size
    )


@router.post("/", status_code=201)
async def create_memory(
    body: Annotated[dict[str, Any], Body()],
    user_id: Annotated[str, Depends(require_permission("memory:create"))],
):
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail=t("memory.content_required"))
    return await get_user_memory_controller().create_memory(uuid.UUID(user_id), content)


@router.get("/{memory_id}")
async def get_memory(
    memory_id: uuid.UUID,
    user_id: Annotated[str, Depends(require_permission("memory:read"))],
):
    return await get_user_memory_controller().get_memory(uuid.UUID(user_id), memory_id)


@router.patch("/{memory_id}")
async def update_memory(
    memory_id: uuid.UUID,
    body: Annotated[dict[str, Any], Body()],
    user_id: Annotated[str, Depends(require_permission("memory:update"))],
):
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail=t("memory.content_required"))
    return await get_user_memory_controller().update_memory(uuid.UUID(user_id), memory_id, content)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: uuid.UUID,
    user_id: Annotated[str, Depends(require_permission("memory:delete"))],
):
    return await get_user_memory_controller().delete_memory(uuid.UUID(user_id), memory_id)


@router.delete("/")
async def delete_all_memories(
    user_id: Annotated[str, Depends(require_permission("memory:delete"))],
):
    return await get_user_memory_controller().delete_all_memories(uuid.UUID(user_id))


# ---------------------------------------------------------------------------
# Internal service-to-service endpoints
# ---------------------------------------------------------------------------


@internal_router.get("/{target_id}/memories")
async def list_memories_internal(
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    return await get_user_memory_controller().list_memories(
        resolved_user_id, page=page, page_size=page_size
    )


@internal_router.get("/{target_id}/memories/recall")
async def list_memories_for_recall_internal(
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    return await get_user_memory_controller().list_for_recall(resolved_user_id)


@internal_router.post("/{target_id}/memories")
async def create_memory_internal(
    target_id: str,
    body: Annotated[dict[str, Any], Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail=t("memory.content_required"))
    return await get_user_memory_controller().create_memory(resolved_user_id, content)


@internal_router.post("/{target_id}/memories/bulk")
async def add_facts_internal(
    target_id: str,
    body: Annotated[dict[str, Any], Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    contents = body.get("contents", [])
    source = body.get("source", "auto_extracted")
    return await get_user_memory_controller().add_facts(resolved_user_id, contents, source=source)


@internal_router.get("/{target_id}/memories/{memory_id}")
async def get_memory_internal(
    target_id: str,
    memory_id: uuid.UUID,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    return await get_user_memory_controller().get_memory(resolved_user_id, memory_id)


@internal_router.patch("/{target_id}/memories/{memory_id}")
async def update_memory_internal(
    target_id: str,
    memory_id: uuid.UUID,
    body: Annotated[dict[str, Any], Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail=t("memory.content_required"))
    return await get_user_memory_controller().update_memory(resolved_user_id, memory_id, content)


@internal_router.delete("/{target_id}/memories/{memory_id}", status_code=204)
async def delete_memory_internal(
    target_id: str,
    memory_id: uuid.UUID,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    return await get_user_memory_controller().delete_memory(resolved_user_id, memory_id)


@internal_router.delete("/{target_id}/memories")
async def delete_all_memories_internal(
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    return await get_user_memory_controller().delete_all_memories(resolved_user_id)

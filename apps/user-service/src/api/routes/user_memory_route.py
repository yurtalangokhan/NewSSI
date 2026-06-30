import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import require_auth_or_internal_service_token, require_permission
from src.controller import get_user_memory_controller
from src.repository import UserRepository

router = APIRouter(prefix="/users/me/memories", tags=["user-memory"])
internal_router = APIRouter(prefix="/internal/users", tags=["user-memory"])


async def _resolve_target_user_id(target_id: str) -> uuid.UUID:
    user_repo = UserRepository()
    try:
        parsed = uuid.UUID(target_id)
    except ValueError:
        parsed = None
    if parsed is not None:
        by_local_id = await user_repo.get_by_id(parsed)
        if by_local_id:
            return by_local_id.id
    by_keycloak_id = await user_repo.get_by_keycloak_id(target_id)
    if by_keycloak_id:
        return by_keycloak_id.id
    raise HTTPException(status_code=404, detail="Target user not found")


async def _authorize_target_user_id(target_id: str, authenticated_user_id: str) -> uuid.UUID:
    from src.repository import CompositeRoleRepository

    resolved_user_id = await _resolve_target_user_id(target_id)
    if authenticated_user_id == "internal-service":
        return resolved_user_id
    try:
        authenticated_uuid = uuid.UUID(authenticated_user_id)
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden") from None
    if resolved_user_id == authenticated_uuid:
        return resolved_user_id
    user = await UserRepository().get_by_id(authenticated_uuid)
    if user:
        if user.is_superuser:
            return resolved_user_id
        role = await CompositeRoleRepository().get_by_name(user.role)
        if role and role.is_admin:
            return resolved_user_id
    raise HTTPException(status_code=403, detail="Forbidden")


# ---------------------------------------------------------------------------
# User-facing endpoints
# ---------------------------------------------------------------------------


@router.get("/")
async def list_memories(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: str = Depends(require_permission("memory:read")),
):
    return await get_user_memory_controller().list_memories(
        uuid.UUID(user_id), page=page, page_size=page_size
    )


@router.post("/", status_code=201)
async def create_memory(
    body: dict,
    user_id: str = Depends(require_permission("memory:create")),
):
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    return await get_user_memory_controller().create_memory(uuid.UUID(user_id), content)


@router.get("/{memory_id}")
async def get_memory(
    memory_id: uuid.UUID,
    user_id: str = Depends(require_permission("memory:read")),
):
    return await get_user_memory_controller().get_memory(uuid.UUID(user_id), memory_id)


@router.patch("/{memory_id}")
async def update_memory(
    memory_id: uuid.UUID,
    body: dict,
    user_id: str = Depends(require_permission("memory:update")),
):
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    return await get_user_memory_controller().update_memory(uuid.UUID(user_id), memory_id, content)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: uuid.UUID,
    user_id: str = Depends(require_permission("memory:delete")),
):
    return await get_user_memory_controller().delete_memory(uuid.UUID(user_id), memory_id)


@router.delete("/")
async def delete_all_memories(
    user_id: str = Depends(require_permission("memory:delete")),
):
    return await get_user_memory_controller().delete_all_memories(uuid.UUID(user_id))


# ---------------------------------------------------------------------------
# Internal service-to-service endpoints
# ---------------------------------------------------------------------------


@internal_router.get("/{target_id}/memories")
@router.get("/internal/users/{target_id}/memories")
async def list_memories_internal(
    target_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    authenticated_user_id: str = Depends(require_auth_or_internal_service_token),
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_user_memory_controller().list_memories(
        resolved_user_id, page=page, page_size=page_size
    )


@internal_router.get("/{target_id}/memories/recall")
@router.get("/internal/users/{target_id}/memories/recall")
async def list_memories_for_recall_internal(
    target_id: str,
    authenticated_user_id: str = Depends(require_auth_or_internal_service_token),
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_user_memory_controller().list_for_recall(resolved_user_id)


@internal_router.post("/{target_id}/memories")
@router.post("/internal/users/{target_id}/memories")
async def create_memory_internal(
    target_id: str,
    body: dict,
    authenticated_user_id: str = Depends(require_auth_or_internal_service_token),
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    return await get_user_memory_controller().create_memory(resolved_user_id, content)


@internal_router.post("/{target_id}/memories/bulk")
@router.post("/internal/users/{target_id}/memories/bulk")
async def add_facts_internal(
    target_id: str,
    body: dict,
    authenticated_user_id: str = Depends(require_auth_or_internal_service_token),
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    contents = body.get("contents", [])
    source = body.get("source", "auto_extracted")
    return await get_user_memory_controller().add_facts(resolved_user_id, contents, source=source)


@internal_router.get("/{target_id}/memories/{memory_id}")
@router.get("/internal/users/{target_id}/memories/{memory_id}")
async def get_memory_internal(
    target_id: str,
    memory_id: uuid.UUID,
    authenticated_user_id: str = Depends(require_auth_or_internal_service_token),
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_user_memory_controller().get_memory(resolved_user_id, memory_id)


@internal_router.patch("/{target_id}/memories/{memory_id}")
@router.patch("/internal/users/{target_id}/memories/{memory_id}")
async def update_memory_internal(
    target_id: str,
    memory_id: uuid.UUID,
    body: dict,
    authenticated_user_id: str = Depends(require_auth_or_internal_service_token),
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    return await get_user_memory_controller().update_memory(resolved_user_id, memory_id, content)


@internal_router.delete("/{target_id}/memories/{memory_id}", status_code=204)
@router.delete("/internal/users/{target_id}/memories/{memory_id}", status_code=204)
async def delete_memory_internal(
    target_id: str,
    memory_id: uuid.UUID,
    authenticated_user_id: str = Depends(require_auth_or_internal_service_token),
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_user_memory_controller().delete_memory(resolved_user_id, memory_id)


@internal_router.delete("/{target_id}/memories")
@router.delete("/internal/users/{target_id}/memories")
async def delete_all_memories_internal(
    target_id: str,
    authenticated_user_id: str = Depends(require_auth_or_internal_service_token),
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_user_memory_controller().delete_all_memories(resolved_user_id)

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from src.api.dependencies import require_auth
from src.controller import get_settings_controller
from src.repository import UserRepository

router = APIRouter(prefix="/users/me/settings", tags=["settings"])


async def _resolve_target_user_id(target_id: str) -> uuid.UUID:
    """Resolve either local user UUID or Keycloak subject to the local user UUID."""
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
    from src.core.database.models.user_model import is_admin_role

    resolved_user_id = await _resolve_target_user_id(target_id)
    authenticated_uuid = uuid.UUID(authenticated_user_id)
    if resolved_user_id == authenticated_uuid:
        return resolved_user_id

    user = await UserRepository().get_by_id(authenticated_uuid)
    if user and (is_admin_role(user.role) or user.is_superuser):
        return resolved_user_id

    raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/")
async def get_settings(user_id: Annotated[str, Depends(require_auth)]):
    return await get_settings_controller().get_settings(uuid.UUID(user_id))


@router.patch("/")
async def update_settings(
    updates: Annotated[dict[str, Any], Body(...)],
    user_id: str = Depends(require_auth),
):
    return await get_settings_controller().update_settings(uuid.UUID(user_id), **updates)


@router.post("/prompt-shortcuts")
async def create_prompt_shortcut(
    shortcut: Annotated[dict[str, Any], Body(...)],
    user_id: str = Depends(require_auth),
):
    return await get_settings_controller().create_prompt_shortcut(uuid.UUID(user_id), shortcut)


@router.patch("/prompt-shortcuts/{shortcut_id}")
async def update_prompt_shortcut(
    shortcut_id: int,
    updates: Annotated[dict[str, Any], Body(...)],
    user_id: str = Depends(require_auth),
):
    return await get_settings_controller().update_prompt_shortcut(
        uuid.UUID(user_id), shortcut_id, **updates
    )


@router.delete("/prompt-shortcuts/{shortcut_id}")
async def delete_prompt_shortcut(shortcut_id: int, user_id: Annotated[str, Depends(require_auth)]):
    return await get_settings_controller().delete_prompt_shortcut(uuid.UUID(user_id), shortcut_id)


@router.get("/internal/users/{target_id}/settings")
async def get_settings_internal(
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth)],
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_settings_controller().get_settings(resolved_user_id)


@router.patch("/internal/users/{target_id}/settings")
async def update_settings_internal(
    target_id: str,
    updates: Annotated[dict[str, Any], Body(...)],
    authenticated_user_id: Annotated[str, Depends(require_auth)],
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_settings_controller().update_settings(resolved_user_id, **updates)


@router.post("/internal/users/{target_id}/settings/prompt-shortcuts")
async def create_prompt_shortcut_internal(
    target_id: str,
    shortcut: Annotated[dict[str, Any], Body(...)],
    authenticated_user_id: Annotated[str, Depends(require_auth)],
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_settings_controller().create_prompt_shortcut(resolved_user_id, shortcut)


@router.patch("/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}")
async def update_prompt_shortcut_internal(
    target_id: str,
    shortcut_id: int,
    updates: Annotated[dict[str, Any], Body(...)],
    authenticated_user_id: Annotated[str, Depends(require_auth)],
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_settings_controller().update_prompt_shortcut(
        resolved_user_id, shortcut_id, **updates
    )


@router.delete("/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}")
async def delete_prompt_shortcut_internal(
    target_id: str,
    shortcut_id: int,
    authenticated_user_id: Annotated[str, Depends(require_auth)],
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_settings_controller().delete_prompt_shortcut(resolved_user_id, shortcut_id)

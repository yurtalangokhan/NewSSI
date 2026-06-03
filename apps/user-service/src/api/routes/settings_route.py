import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from src.api.dependencies import require_auth, verify_internal_service_token
from src.controller import get_settings_controller
from src.repository import UserRepository

router = APIRouter(prefix="/users/me/settings", tags=["settings"])


async def require_internal_token(
    is_internal: Annotated[bool, Depends(verify_internal_service_token)],
) -> None:
    if not is_internal:
        raise HTTPException(status_code=403, detail="Internal service token required")


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
    _: Annotated[None, Depends(require_internal_token)],
):
    resolved_user_id = await _resolve_target_user_id(target_id)
    return await get_settings_controller().get_settings(resolved_user_id)


@router.patch("/internal/users/{target_id}/settings")
async def update_settings_internal(
    target_id: str,
    updates: Annotated[dict[str, Any], Body(...)],
    _: str = Depends(require_internal_token),
):
    resolved_user_id = await _resolve_target_user_id(target_id)
    return await get_settings_controller().update_settings(resolved_user_id, **updates)


@router.post("/internal/users/{target_id}/settings/prompt-shortcuts")
async def create_prompt_shortcut_internal(
    target_id: str,
    shortcut: Annotated[dict[str, Any], Body(...)],
    _: str = Depends(require_internal_token),
):
    resolved_user_id = await _resolve_target_user_id(target_id)
    return await get_settings_controller().create_prompt_shortcut(resolved_user_id, shortcut)


@router.patch("/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}")
async def update_prompt_shortcut_internal(
    target_id: str,
    shortcut_id: int,
    updates: Annotated[dict[str, Any], Body(...)],
    _: str = Depends(require_internal_token),
):
    resolved_user_id = await _resolve_target_user_id(target_id)
    return await get_settings_controller().update_prompt_shortcut(
        resolved_user_id, shortcut_id, **updates
    )


@router.delete("/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}")
async def delete_prompt_shortcut_internal(
    target_id: str,
    shortcut_id: int,
    _: Annotated[None, Depends(require_internal_token)],
):
    resolved_user_id = await _resolve_target_user_id(target_id)
    return await get_settings_controller().delete_prompt_shortcut(resolved_user_id, shortcut_id)

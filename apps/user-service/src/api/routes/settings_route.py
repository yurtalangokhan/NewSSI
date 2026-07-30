import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from src.api.dependencies import require_auth_or_internal_service_token, require_permission
from src.controller import get_settings_controller
from src.controller.user_controller import get_user_controller

router = APIRouter(prefix="/users/me/settings", tags=["settings"])
internal_router = APIRouter(prefix="/internal/users", tags=["settings"])


@router.get("/")
async def get_settings(user_id: Annotated[str, Depends(require_permission("settings:read"))]):
    return await get_settings_controller().get_settings(uuid.UUID(user_id))


@router.patch("/")
async def update_settings(
    updates: Annotated[dict[str, Any], Body()],
    user_id: Annotated[str, Depends(require_permission("settings:update"))],
):
    return await get_settings_controller().update_settings(uuid.UUID(user_id), **updates)


@router.post("/prompt-shortcuts")
async def create_prompt_shortcut(
    shortcut: Annotated[dict[str, Any], Body()],
    user_id: Annotated[str, Depends(require_permission("settings:update"))],
):
    return await get_settings_controller().create_prompt_shortcut(uuid.UUID(user_id), shortcut)


@router.patch("/prompt-shortcuts/{shortcut_id}")
async def update_prompt_shortcut(
    shortcut_id: int,
    updates: Annotated[dict[str, Any], Body()],
    user_id: Annotated[str, Depends(require_permission("settings:update"))],
):
    return await get_settings_controller().update_prompt_shortcut(
        uuid.UUID(user_id), shortcut_id, **updates
    )


@router.delete("/prompt-shortcuts/{shortcut_id}")
async def delete_prompt_shortcut(
    shortcut_id: int,
    user_id: Annotated[str, Depends(require_permission("settings:update"))],
):
    return await get_settings_controller().delete_prompt_shortcut(uuid.UUID(user_id), shortcut_id)


@internal_router.get("/{target_id}/settings")
async def get_settings_internal(
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    return await get_settings_controller().get_settings(resolved_user_id)


@internal_router.patch("/{target_id}/settings")
async def update_settings_internal(
    target_id: str,
    updates: Annotated[dict[str, Any], Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    return await get_settings_controller().update_settings(resolved_user_id, **updates)


@internal_router.post("/{target_id}/settings/prompt-shortcuts")
async def create_prompt_shortcut_internal(
    target_id: str,
    shortcut: Annotated[dict[str, Any], Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    return await get_settings_controller().create_prompt_shortcut(resolved_user_id, shortcut)


@internal_router.patch("/{target_id}/settings/prompt-shortcuts/{shortcut_id}")
async def update_prompt_shortcut_internal(
    target_id: str,
    shortcut_id: int,
    updates: Annotated[dict[str, Any], Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    return await get_settings_controller().update_prompt_shortcut(
        resolved_user_id, shortcut_id, **updates
    )


@internal_router.delete("/{target_id}/settings/prompt-shortcuts/{shortcut_id}")
async def delete_prompt_shortcut_internal(
    target_id: str,
    shortcut_id: int,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await get_user_controller().authorize_target_user_id(
        target_id,
        authenticated_user_id,
    )
    return await get_settings_controller().delete_prompt_shortcut(resolved_user_id, shortcut_id)

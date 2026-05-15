import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import require_auth
from src.controller import get_settings_controller

router = APIRouter(prefix="/users/me/settings", tags=["settings"])


@router.get("/")
async def get_settings(user_id: Annotated[str, Depends(require_auth)]):
    return await get_settings_controller().get_settings(uuid.UUID(user_id))


@router.patch("/")
async def update_settings(user_id: Annotated[str, Depends(require_auth)], **updates):
    return await get_settings_controller().update_settings(uuid.UUID(user_id), **updates)


@router.post("/prompt-shortcuts")
async def create_prompt_shortcut(user_id: Annotated[str, Depends(require_auth)], shortcut: dict):
    return await get_settings_controller().create_prompt_shortcut(uuid.UUID(user_id), shortcut)


@router.patch("/prompt-shortcuts/{shortcut_id}")
async def update_prompt_shortcut(
    shortcut_id: int,
    user_id: Annotated[str, Depends(require_auth)],
    **updates,
):
    return await get_settings_controller().update_prompt_shortcut(uuid.UUID(user_id), shortcut_id, **updates)


@router.delete("/prompt-shortcuts/{shortcut_id}")
async def delete_prompt_shortcut(shortcut_id: int, user_id: Annotated[str, Depends(require_auth)]):
    return await get_settings_controller().delete_prompt_shortcut(uuid.UUID(user_id), shortcut_id)

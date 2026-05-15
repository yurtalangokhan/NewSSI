import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import require_auth
from src.controller import get_api_key_controller

router = APIRouter(prefix="/users/me/api-keys", tags=["api-keys"])


@router.post("/")
async def create_key(name: str, user_id: Annotated[str, Depends(require_auth)]):
    return await get_api_key_controller().create_key(uuid.UUID(user_id), name)


@router.get("/")
async def list_keys(user_id: Annotated[str, Depends(require_auth)]):
    return await get_api_key_controller().list_keys(uuid.UUID(user_id))


@router.delete("/{key_id}")
async def delete_key(key_id: str, user_id: Annotated[str, Depends(require_auth)]):
    return await get_api_key_controller().delete_key(uuid.UUID(key_id))

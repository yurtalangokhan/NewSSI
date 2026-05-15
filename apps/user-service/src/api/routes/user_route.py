import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import require_admin, require_auth
from src.controller import get_user_controller

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_me(user_id: Annotated[str, Depends(require_auth)]):
    return await get_user_controller().get_me(uuid.UUID(user_id))


@router.patch("/me")
async def update_me(user_id: Annotated[str, Depends(require_auth)], **updates):
    return await get_user_controller().update_me(uuid.UUID(user_id), **updates)


@router.get("/")
async def list_users(
    skip: int = 0,
    limit: int = 20,
    query: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    invited: bool | None = None,
    user_id: str = Depends(require_admin),
):
    return await get_user_controller().list_users(skip, limit, query, role, is_active, invited)


@router.post("/")
async def create_user(user_id: str = Depends(require_admin), **payload):
    return await get_user_controller().create_user(**payload)


@router.get("/invited")
async def get_invited_users(user_id: str = Depends(require_admin)):
    from src.service import get_user_service
    return await get_user_service().get_invited_users()


@router.get("/{target_id}")
async def get_user(target_id: str, user_id: str = Depends(require_admin)):
    return await get_user_controller().get_user(uuid.UUID(target_id))


@router.patch("/{target_id}")
async def update_user(target_id: str, user_id: str = Depends(require_admin), **updates):
    return await get_user_controller().update_user(uuid.UUID(target_id), **updates)


@router.delete("/{target_id}")
async def delete_user(target_id: str, user_id: str = Depends(require_admin)):
    return await get_user_controller().delete_user(uuid.UUID(target_id))


@router.post("/invite")
async def invite_users(
    emails: list[str],
    user_id: str = Depends(require_admin),
):
    return await get_user_controller().invite_users(emails)


@router.post("/{target_id}/role")
async def set_user_role(target_id: str, role: str, user_id: str = Depends(require_admin)):
    return await get_user_controller().set_user_role(uuid.UUID(target_id), role)


@router.post("/{target_id}/reset-password")
async def reset_user_password(target_id: str, user_id: str = Depends(require_admin)):
    return await get_user_controller().reset_password(uuid.UUID(target_id))


@router.patch("/{target_id}/active")
async def set_user_active(target_id: str, is_active: bool = True, user_id: str = Depends(require_admin)):
    return await get_user_controller().set_user_active(uuid.UUID(target_id), is_active)


@router.post("/{target_id}/password")
async def set_user_password(target_id: str, password: str, user_id: str = Depends(require_admin)):
    return await get_user_controller().set_password(uuid.UUID(target_id), password)


@router.get("/download/csv")
async def download_csv(query: str | None = None, user_id: str = Depends(require_admin)):
    csv = await get_user_controller().download_users_csv(query)
    import io

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        io.StringIO(csv),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )

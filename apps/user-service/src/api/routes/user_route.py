import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.dependencies import require_admin, require_auth, verify_internal_service_token
from src.controller import get_user_controller

router = APIRouter(prefix="/users", tags=["users"])


class UserCreateRequest(BaseModel):
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str = "enduser"
    password: str | None = None
    invited: bool = False
    keycloak_id: str | None = None


class UserUpdateRequest(BaseModel):
    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    team_name: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    role: str | None = None


class UserInviteRequest(BaseModel):
    emails: list[str]


class UserRoleRequest(BaseModel):
    role: str


class UserActiveRequest(BaseModel):
    is_active: bool


class UserPasswordRequest(BaseModel):
    password: str


class KeycloakUpsertRequest(BaseModel):
    keycloak_id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


async def require_internal_token(
    is_internal: Annotated[bool, Depends(verify_internal_service_token)],
) -> None:
    if not is_internal:
        raise HTTPException(status_code=403, detail="Internal service token required")


@router.get("/me")
async def get_me(user_id: Annotated[str, Depends(require_auth)]):
    return await get_user_controller().get_me(uuid.UUID(user_id))


@router.patch("/me")
async def update_me(
    updates: Annotated[UserUpdateRequest, Body(...)],
    user_id: str = Depends(require_auth),
):
    return await get_user_controller().update_me(
        uuid.UUID(user_id),
        **updates.model_dump(exclude_unset=True),
    )


@router.get("/")
async def list_users(
    skip: int = 0,
    limit: int = 20,
    page_num: int | None = None,
    page_size: int | None = None,
    query: str | None = None,
    q: str | None = None,
    role: str | None = None,
    roles: Annotated[list[str] | None, Query()] = None,
    is_active: bool | None = None,
    invited: bool | None = None,
    user_id: str = Depends(require_admin),  # noqa: ARG001
):
    resolved_limit = page_size or limit
    resolved_skip = page_num * resolved_limit if page_num is not None else skip
    result = await get_user_controller().list_users(
        resolved_skip,
        resolved_limit,
        q or query,
        role,
        roles,
        is_active,
        invited,
    )
    return {
        **result,
        "items": result["users"],
        "total_items": result["total"],
    }


@router.post("/")
async def create_user(
    payload: Annotated[UserCreateRequest, Body(...)],
    user_id: str = Depends(require_admin),  # noqa: ARG001
):
    return await get_user_controller().create_user(**payload.model_dump(exclude_unset=True))


@router.get("/invited")
async def get_invited_users(user_id: str = Depends(require_admin)):  # noqa: ARG001
    from src.service import get_user_service

    return await get_user_service().get_invited_users()


@router.get("/download/csv")
async def download_csv(query: str | None = None, user_id: str = Depends(require_admin)):  # noqa: ARG001
    csv = await get_user_controller().download_users_csv(query)
    import io

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        io.StringIO(csv),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )


# Internal endpoint for agent-service to sync users from Keycloak
@router.post("/internal/upsert-from-keycloak")
async def upsert_user_from_keycloak(
    payload: Annotated[KeycloakUpsertRequest, Body(...)],
    _: Annotated[None, Depends(require_internal_token)],
):
    """Internal endpoint for agent-service to create/update users from Keycloak OIDC.

    This is called from agent-service during OIDC callback to ensure user exists in user-service.
    """
    return await get_user_controller().upsert_user_from_keycloak(
        **payload.model_dump(exclude_unset=True)
    )


# Internal endpoint for agent-service to fetch user by Keycloak ID
@router.get("/internal/by-keycloak-id/{keycloak_id}")
async def get_user_by_keycloak_id(
    keycloak_id: str,
    _: Annotated[None, Depends(require_internal_token)],
):
    """Internal endpoint for agent-service to fetch user by Keycloak ID (subject).

    Used in /api/me endpoint to get complete user data from user-service.
    """
    return await get_user_controller().get_user_by_keycloak_id(keycloak_id)


@router.post("/invite")
async def invite_users(
    payload: Annotated[UserInviteRequest, Body(...)],
    user_id: str = Depends(require_admin),  # noqa: ARG001
):
    return await get_user_controller().invite_users(payload.emails)


@router.post("/{target_id}/role")
async def set_user_role(
    target_id: str,
    payload: Annotated[UserRoleRequest, Body(...)],
    user_id: str = Depends(require_admin),  # noqa: ARG001
):
    return await get_user_controller().set_user_role(uuid.UUID(target_id), payload.role)


@router.post("/{target_id}/reset-password")
async def reset_user_password(target_id: str, user_id: str = Depends(require_admin)):  # noqa: ARG001
    return await get_user_controller().reset_password(uuid.UUID(target_id))


@router.patch("/{target_id}/active")
async def set_user_active(
    target_id: str,
    payload: Annotated[UserActiveRequest, Body(...)],
    user_id: str = Depends(require_admin),  # noqa: ARG001
):
    return await get_user_controller().set_user_active(uuid.UUID(target_id), payload.is_active)


@router.post("/{target_id}/password")
async def set_user_password(
    target_id: str,
    payload: Annotated[UserPasswordRequest, Body(...)],
    user_id: str = Depends(require_admin),  # noqa: ARG001
):
    return await get_user_controller().set_password(uuid.UUID(target_id), payload.password)


@router.get("/{target_id}")
async def get_user(target_id: str, user_id: str = Depends(require_admin)):  # noqa: ARG001
    return await get_user_controller().get_user(uuid.UUID(target_id))


@router.patch("/{target_id}")
async def update_user(
    target_id: str,
    updates: Annotated[UserUpdateRequest, Body(...)],
    user_id: str = Depends(require_admin),  # noqa: ARG001
):
    return await get_user_controller().update_user(
        uuid.UUID(target_id),
        **updates.model_dump(exclude_unset=True),
    )


@router.delete("/{target_id}")
async def delete_user(target_id: str, user_id: str = Depends(require_admin)):  # noqa: ARG001
    return await get_user_controller().delete_user(uuid.UUID(target_id))

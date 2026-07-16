import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from src.api.dependencies import (
    require_auth,
    require_auth_or_internal_service_token,
    require_permission,
)
from src.controller import get_user_controller
from src.models.users import (
    InternalAuthorizeRequest,
    InternalUserUpdateRequest,
    KeycloakUpsertRequest,
    UserActiveRequest,
    UserChangePasswordRequest,
    UserCreateRequest,
    UserInviteRequest,
    UserPasswordRequest,
    UserRoleRequest,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["users"])


async def _resolve_target_user_id(target_id: str) -> uuid.UUID:
    from src.repository import UserRepository

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
    from src.repository import CompositeRoleRepository, UserRepository

    resolved_user_id = await _resolve_target_user_id(target_id)

    # Internal service token has full access (machine-only flows)
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


@router.get("/me")
async def get_me(user_id: Annotated[str, Depends(require_auth)]):
    return await get_user_controller().get_me(uuid.UUID(user_id))


@router.get("/me/permissions")
async def get_me_permissions(user_id: Annotated[str, Depends(require_auth)]):
    return await get_user_controller().get_user_permissions(uuid.UUID(user_id))


@router.patch("/me")
async def update_me(
    updates: Annotated[UserUpdateRequest, Body(...)],
    user_id: str = Depends(require_auth),
):
    return await get_user_controller().update_me(
        uuid.UUID(user_id),
        **updates.model_dump(exclude_unset=True),
    )


@router.post("/me/password")
async def change_me_password(
    payload: Annotated[UserChangePasswordRequest, Body(...)],
    user_id: str = Depends(require_auth),
):
    return await get_user_controller().change_password(
        uuid.UUID(user_id),
        payload.old_password,
        payload.new_password,
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
    user_id: str = Depends(require_permission("user:list")),  # noqa: ARG001
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
    user_id: str = Depends(require_permission("user:create")),  # noqa: ARG001
):
    return await get_user_controller().create_user(**payload.model_dump(exclude_unset=True))


@router.get("/invited")
async def get_invited_users(
    user_id: str = Depends(require_permission("user:list")),  # noqa: ARG001
):
    from src.service import get_user_service

    return await get_user_service().get_invited_users()


@router.get("/download/csv")
async def download_csv(
    query: str | None = None,
    user_id: str = Depends(require_permission("user:list")),  # noqa: ARG001
):
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
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    """Internal endpoint for agent-service to create/update users from Keycloak OIDC.

    This is called from agent-service during OIDC callback to ensure user exists in user-service.
    Accepts X-Internal-Service-Token for machine-only flows (no user context).
    """
    await _authorize_target_user_id(payload.keycloak_id, authenticated_user_id)
    return await get_user_controller().upsert_user_from_keycloak(
        **payload.model_dump(exclude_unset=True)
    )


# Internal endpoint for agent-service to fetch user by Keycloak ID
@router.get("/internal/by-keycloak-id/{keycloak_id}")
async def get_user_by_keycloak_id(
    keycloak_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    """Internal endpoint for agent-service to fetch user by Keycloak ID (subject).

    Used in /api/me endpoint to get complete user data from user-service.
    Accepts X-Internal-Service-Token for machine-only flows.
    """
    await _authorize_target_user_id(keycloak_id, authenticated_user_id)
    return await get_user_controller().get_user_by_keycloak_id(keycloak_id)


@router.patch("/internal/users/{target_id}")
async def update_user_internal(
    target_id: str,
    updates: Annotated[InternalUserUpdateRequest, Body(...)],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_user_controller().update_user(
        resolved_user_id,
        **updates.model_dump(exclude_unset=True),
    )


@router.get("/internal/{target_id}/permissions")
async def get_user_permissions_internal(
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await _authorize_target_user_id(target_id, authenticated_user_id)
    return await get_user_controller().get_user_permissions(resolved_user_id)


@router.post("/internal/authorize")
async def authorize_user_permission_internal(
    payload: Annotated[InternalAuthorizeRequest, Body(...)],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    resolved_user_id = await _authorize_target_user_id(payload.target_id, authenticated_user_id)
    return await get_user_controller().authorize_user_permission(
        resolved_user_id,
        payload.permission,
    )


@router.post("/invite")
async def invite_users(
    payload: Annotated[UserInviteRequest, Body(...)],
    user_id: str = Depends(require_permission("user:create")),  # noqa: ARG001
):
    return await get_user_controller().invite_users(payload.emails)


@router.post("/{target_id}/role")
async def set_user_role(
    target_id: str,
    payload: Annotated[UserRoleRequest, Body(...)],
    user_id: str = Depends(require_permission("user:update")),  # noqa: ARG001
):
    return await get_user_controller().set_user_role(uuid.UUID(target_id), payload.role)


@router.post("/{target_id}/reset-password")
async def reset_user_password(
    target_id: str,
    user_id: str = Depends(require_permission("user:update")),  # noqa: ARG001
):
    return await get_user_controller().reset_password(uuid.UUID(target_id))


@router.patch("/{target_id}/active")
async def set_user_active(
    target_id: str,
    payload: Annotated[UserActiveRequest, Body(...)],
    user_id: str = Depends(require_permission("user:update")),  # noqa: ARG001
):
    return await get_user_controller().set_user_active(uuid.UUID(target_id), payload.is_active)


@router.post("/{target_id}/password")
async def set_user_password(
    target_id: str,
    payload: Annotated[UserPasswordRequest, Body(...)],
    user_id: str = Depends(require_permission("user:update")),  # noqa: ARG001
):
    return await get_user_controller().set_password(uuid.UUID(target_id), payload.password)


@router.get("/{target_id}")
async def get_user(
    target_id: str,
    user_id: str = Depends(require_permission("user:read")),  # noqa: ARG001
):
    return await get_user_controller().get_user(uuid.UUID(target_id))


@router.patch("/{target_id}")
async def update_user(
    target_id: str,
    updates: Annotated[UserUpdateRequest, Body(...)],
    user_id: str = Depends(require_permission("user:update")),  # noqa: ARG001
):
    return await get_user_controller().update_user(
        uuid.UUID(target_id),
        **updates.model_dump(exclude_unset=True),
    )


@router.delete("/{target_id}")
async def delete_user(
    target_id: str,
    user_id: str = Depends(require_permission("user:delete")),  # noqa: ARG001
):
    return await get_user_controller().delete_user(uuid.UUID(target_id))

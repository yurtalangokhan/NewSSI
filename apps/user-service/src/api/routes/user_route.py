from typing import Annotated, Any
import uuid

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Body, Depends, Query, Request, Response

from src.api.dependencies import (
    require_auth,
    require_auth_or_internal_service_token,
    require_permission,
)
from src.controller import get_user_controller
from src.controller.base import BaseController
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.users import (
    InternalAuthorizeRequest,
    InternalUserBatchRequest,
    InternalUserUpdateRequest,
    KeycloakUpsertRequest,
    RoleDistributionResponse,
    UserActiveRequest,
    UserChangePasswordRequest,
    UserCreateRequest,
    UserInviteRequest,
    UserPasswordRequest,
    UserRoleRequest,
    UserRolesAssignRequest,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["users"])
internal_router = APIRouter(prefix="/internal/users", tags=["users"])

# Spec T4: limit/page_size were plain, unbounded ints -- ?limit=1000000 was
# accepted and forwarded straight to the repository's SQL LIMIT.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


@router.get("/me")
async def get_me(
    request: Request, response: Response, user_id: Annotated[str, Depends(require_auth)]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().get_me(BaseController.parse_user_id(user_id)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/me/permissions")
async def get_me_permissions(
    request: Request, response: Response, user_id: Annotated[str, Depends(require_auth)]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().get_user_permissions(BaseController.parse_user_id(user_id)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/me/roles")
async def get_me_roles(
    request: Request, response: Response, user_id: Annotated[str, Depends(require_auth)]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().list_user_roles(BaseController.parse_user_id(user_id)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/me")
async def update_me(
    request: Request,
    response: Response,
    updates: Annotated[UserUpdateRequest, Body()],
    user_id: Annotated[str, Depends(require_auth)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().update_me(
                BaseController.parse_user_id(user_id),
                **updates.model_dump(exclude_unset=True),
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/me/password")
async def change_me_password(
    request: Request,
    response: Response,
    payload: Annotated[UserChangePasswordRequest, Body()],
    user_id: Annotated[str, Depends(require_auth)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().change_password(
                BaseController.parse_user_id(user_id),
                payload.old_password,
                payload.new_password,
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/")
async def list_users(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("user:list"))],  # noqa: ARG001
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    page_num: Annotated[int | None, Query(ge=0)] = None,
    page_size: Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)] = None,
    query: str | None = None,
    q: str | None = None,
    role: str | None = None,
    roles: Annotated[list[str] | None, Query()] = None,
    is_active: bool | None = None,
    invited: bool | None = None,
) -> ResponseModel[Any]:
    try:
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
        return ResponseModel(
            statusCode=200,
            data={
                **result,
                "items": result["users"],
                "total_items": result["total"],
                # A filtered page reports how far it read, not how many exist: the
                # caller must not present that lower bound as a count.
                "total_items_exact": result["total_exact"],
            },
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/")
async def create_user(
    request: Request,
    response: Response,
    payload: Annotated[UserCreateRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("user:create"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().create_user(**payload.model_dump(exclude_unset=True)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/invited")
async def get_invited_users(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("user:list"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_user_controller().get_invited_users())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/role-distribution")
async def get_role_distribution(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("user:list"))],  # noqa: ARG001
) -> ResponseModel[RoleDistributionResponse]:
    try:
        return ResponseModel(statusCode=200, data=await get_user_controller().get_role_distribution())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/download/csv")
async def download_csv(
    user_id: Annotated[str, Depends(require_permission("user:list"))],  # noqa: ARG001
    query: str | None = None,
):
    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        get_user_controller().stream_users_csv(query),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )


@internal_router.post("/batch")
async def get_users_by_ids_internal(
    request: Request,
    response: Response,
    payload: Annotated[InternalUserBatchRequest, Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_user_controller().get_users_by_ids(payload.user_ids))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


# Internal endpoint for agent-service to sync users from Keycloak
@internal_router.post("/upsert-from-keycloak")
@router.post("/internal/upsert-from-keycloak")
async def upsert_user_from_keycloak(
    request: Request,
    response: Response,
    payload: Annotated[KeycloakUpsertRequest, Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    """Internal endpoint for agent-service to create/update users from Keycloak OIDC.

    This is called from agent-service during OIDC callback to ensure user exists in user-service.
    Accepts X-Internal-Service-Token for machine-only flows (no user context).
    """
    try:
        await get_user_controller().authorize_target_user_id(payload.keycloak_id, authenticated_user_id)
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().upsert_user_from_keycloak(**payload.model_dump(exclude_unset=True)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


# Internal endpoint for agent-service to fetch user by Keycloak ID
@internal_router.get("/by-keycloak-id/{keycloak_id}")
async def get_user_by_keycloak_id(
    request: Request,
    response: Response,
    keycloak_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    """Internal endpoint for agent-service to fetch user by Keycloak ID (subject).

    Used in /api/me endpoint to get complete user data from user-service.
    Accepts X-Internal-Service-Token for machine-only flows.
    """
    try:
        await get_user_controller().authorize_target_user_id(keycloak_id, authenticated_user_id)
        return ResponseModel(statusCode=200, data=await get_user_controller().get_user_by_keycloak_id(keycloak_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.patch("/{target_id}")
async def update_user_internal(
    request: Request,
    response: Response,
    target_id: str,
    updates: Annotated[InternalUserUpdateRequest, Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().update_user(
                resolved_user_id,
                **updates.model_dump(exclude_unset=True),
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.get("/{target_id}/permissions")
async def get_user_permissions_internal(
    request: Request,
    response: Response,
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        return ResponseModel(statusCode=200, data=await get_user_controller().get_user_permissions(resolved_user_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.get("/{target_id}/effective-permissions")
async def get_user_effective_permissions_internal(
    request: Request,
    response: Response,
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        return ResponseModel(statusCode=200, data=await get_user_controller().get_user_permissions(resolved_user_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.get("/{target_id}/roles")
async def get_user_roles_internal(
    request: Request,
    response: Response,
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        return ResponseModel(statusCode=200, data=await get_user_controller().list_user_roles(resolved_user_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.post("/authorize")
async def authorize_user_permission_internal(
    request: Request,
    response: Response,
    payload: Annotated[InternalAuthorizeRequest, Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            payload.target_id,
            authenticated_user_id,
        )
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().authorize_user_permission(
                resolved_user_id,
                payload.permission,
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/invite")
async def invite_users(
    request: Request,
    response: Response,
    payload: Annotated[UserInviteRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("user:create"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_user_controller().invite_users(payload.emails))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/{target_id}/role")
async def replace_user_role(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    payload: Annotated[UserRoleRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("user:update"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().replace_role(target_id, payload.role_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{target_id}/roles")
async def list_user_roles(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    user_id: Annotated[str, Depends(require_permission("user:read"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_user_controller().list_user_roles(target_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/{target_id}/roles")
async def assign_user_roles(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    payload: Annotated[UserRolesAssignRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("user:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().assign_roles(
                target_id,
                payload.role_ids,
                payload.primary_role_id,
                actor_user_id=user_id,
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/{target_id}/roles/{role_id}")
async def remove_user_role(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    role_id: str,
    user_id: Annotated[str, Depends(require_permission("user:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().remove_role(
                target_id,
                role_id,
                actor_user_id=user_id,
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/{target_id}/roles/{role_id}/primary")
async def set_primary_user_role(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    role_id: str,
    user_id: Annotated[str, Depends(require_permission("user:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().set_primary_role(
                target_id,
                role_id,
                actor_user_id=user_id,
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/{target_id}/reset-password")
async def reset_user_password(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    user_id: Annotated[str, Depends(require_permission("user:update"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_user_controller().reset_password(target_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/{target_id}/active")
async def set_user_active(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    payload: Annotated[UserActiveRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("user:update"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().set_user_active(target_id, payload.is_active),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/{target_id}/password")
async def set_user_password(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    payload: Annotated[UserPasswordRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("user:update"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().set_password(target_id, payload.password),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{target_id}")
async def get_user(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    user_id: Annotated[str, Depends(require_permission("user:read"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_user_controller().get_user(target_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/{target_id}")
async def update_user(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    updates: Annotated[UserUpdateRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("user:update"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_controller().update_user(
                target_id,
                **updates.model_dump(exclude_unset=True),
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/{target_id}")
async def delete_user(
    request: Request,
    response: Response,
    target_id: uuid.UUID,
    user_id: Annotated[str, Depends(require_permission("user:delete"))],  # noqa: ARG001
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_user_controller().delete_user(target_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )

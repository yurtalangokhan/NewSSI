"""Platform roles (Keycloak realm roles), addressed by their Keycloak role ID."""

from typing import Annotated

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Body, Depends, Path, Request, Response

from src.api.dependencies import require_permission
from src.controller.role_controller import get_composite_role_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.roles import (
    CompositeRoleBundlesResponse,
    CompositeRoleBundlesUpdateResponse,
    CompositeRoleCreateRequest,
    CompositeRoleListResponse,
    CompositeRolePermissionsResponse,
    CompositeRoleResponse,
    CompositeRoleUpdateRequest,
    MessageResponse,
    RoleBundlesRequest,
    RolePermissionsRequest,
)

router = APIRouter(prefix="/roles", tags=["roles"])

RoleId = Annotated[str, Path(description="Keycloak realm-role ID.")]


@router.get("/")
async def list_roles(
    request: Request, response: Response, _user_id: Annotated[str, Depends(require_permission("role:list"))]
) -> ResponseModel[CompositeRoleListResponse]:
    try:
        return ResponseModel(statusCode=200, data=await get_composite_role_controller().list_roles())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/", status_code=201)
async def create_role(
    request: Request,
    response: Response,
    payload: Annotated[CompositeRoleCreateRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
) -> ResponseModel[CompositeRoleResponse]:
    try:
        return ResponseModel(
            statusCode=201,
            data=await get_composite_role_controller().create_role(
                name=payload.name,
                description=payload.description,
                permissions=payload.permissions,
                role_ids=payload.role_ids,
                user_id=user_id,
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


@router.get("/{role_id}")
async def get_role(
    request: Request,
    response: Response,
    role_id: RoleId,
    _user_id: Annotated[str, Depends(require_permission("role:read"))],
) -> ResponseModel[CompositeRoleResponse]:
    try:
        return ResponseModel(statusCode=200, data=await get_composite_role_controller().get_role(role_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/{role_id}")
async def update_role(
    request: Request,
    response: Response,
    role_id: RoleId,
    payload: Annotated[CompositeRoleUpdateRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
) -> ResponseModel[CompositeRoleResponse]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_composite_role_controller().update_role(
                role_id,
                description=payload.description,
                permissions=payload.permissions,
                role_ids=payload.role_ids,
                user_id=user_id,
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


@router.delete("/{role_id}")
async def delete_role(
    request: Request,
    response: Response,
    role_id: RoleId,
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
) -> ResponseModel[MessageResponse]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_composite_role_controller().delete_role(role_id, user_id=user_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{role_id}/permissions")
async def get_role_permissions(
    request: Request,
    response: Response,
    role_id: RoleId,
    _user_id: Annotated[str, Depends(require_permission("role:read"))],
) -> ResponseModel[CompositeRolePermissionsResponse]:
    try:
        return ResponseModel(statusCode=200, data=await get_composite_role_controller().get_role_permissions(role_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.put("/{role_id}/permissions")
async def set_role_permissions(
    request: Request,
    response: Response,
    role_id: RoleId,
    payload: Annotated[RolePermissionsRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
) -> ResponseModel[CompositeRolePermissionsResponse]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_composite_role_controller().set_role_permissions(
                role_id, payload.permissions, user_id=user_id
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


@router.get("/{role_id}/role-ids")
async def get_role_bundles(
    request: Request,
    response: Response,
    role_id: RoleId,
    _user_id: Annotated[str, Depends(require_permission("role:read"))],
) -> ResponseModel[CompositeRoleBundlesResponse]:
    try:
        return ResponseModel(statusCode=200, data=await get_composite_role_controller().get_role_bundles(role_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.put("/{role_id}/role-ids")
async def set_role_bundles(
    request: Request,
    response: Response,
    role_id: RoleId,
    payload: Annotated[RoleBundlesRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
) -> ResponseModel[CompositeRoleBundlesUpdateResponse]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_composite_role_controller().set_role_bundles(role_id, payload.role_ids, user_id=user_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )

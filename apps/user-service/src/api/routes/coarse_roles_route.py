"""Feature bundles (Keycloak client roles), addressed by their Keycloak role ID."""

from typing import Annotated

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Body, Depends, Path, Query, Request, Response

from src.api.dependencies import require_permission
from src.controller.coarse_role_controller import get_role_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.roles import (
    AggregatedPermissionsResponse,
    CoarseRoleCreateRequest,
    CoarseRoleListResponse,
    CoarseRolePermissionsResponse,
    CoarseRoleResponse,
    CoarseRoleUpdateRequest,
    MessageResponse,
    RolePermissionsRequest,
    ServiceClientListResponse,
)

router = APIRouter(prefix="/coarse-roles", tags=["coarse-roles"])

RoleId = Annotated[str, Path(description="Keycloak client-role ID.")]


@router.get("/")
async def list_coarse_roles(
    request: Request,
    response: Response,
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
    service_client: Annotated[str | None, Query()] = None,
) -> ResponseModel[CoarseRoleListResponse]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_role_controller().list_roles(service_client=service_client),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/", status_code=201)
async def create_coarse_role(
    request: Request,
    response: Response,
    payload: Annotated[CoarseRoleCreateRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
) -> ResponseModel[CoarseRoleResponse]:
    try:
        return ResponseModel(
            statusCode=201,
            data=await get_role_controller().create_role(
                name=payload.name,
                service_client=payload.service_client,
                description=payload.description,
                permissions=payload.permissions,
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


@router.get("/aggregated/")
async def get_aggregated_permissions(
    request: Request,
    response: Response,
    ids: Annotated[str, Query(description="Comma-separated Keycloak feature-role IDs")],
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
) -> ResponseModel[AggregatedPermissionsResponse]:
    try:
        role_ids = [role_id.strip() for role_id in ids.split(",") if role_id.strip()]
        return ResponseModel(statusCode=200, data=await get_role_controller().get_aggregated_permissions(role_ids))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/service-clients/list")
async def list_service_clients(
    request: Request,
    response: Response,
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
) -> ResponseModel[ServiceClientListResponse]:
    try:
        return ResponseModel(statusCode=200, data=await get_role_controller().list_service_clients())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{role_id}")
async def get_coarse_role(
    request: Request,
    response: Response,
    role_id: RoleId,
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
) -> ResponseModel[CoarseRoleResponse]:
    try:
        return ResponseModel(statusCode=200, data=await get_role_controller().get_role(role_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/{role_id}")
async def update_coarse_role(
    request: Request,
    response: Response,
    role_id: RoleId,
    payload: Annotated[CoarseRoleUpdateRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
) -> ResponseModel[CoarseRoleResponse]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_role_controller().update_role(role_id, description=payload.description, user_id=user_id),
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
async def delete_coarse_role(
    request: Request,
    response: Response,
    role_id: RoleId,
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
) -> ResponseModel[MessageResponse]:
    try:
        return ResponseModel(statusCode=200, data=await get_role_controller().delete_role(role_id, user_id=user_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{role_id}/permissions")
async def get_coarse_role_permissions(
    request: Request,
    response: Response,
    role_id: RoleId,
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
) -> ResponseModel[CoarseRolePermissionsResponse]:
    try:
        return ResponseModel(statusCode=200, data=await get_role_controller().get_role_permissions(role_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.put("/{role_id}/permissions")
async def set_coarse_role_permissions(
    request: Request,
    response: Response,
    role_id: RoleId,
    payload: Annotated[RolePermissionsRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
) -> ResponseModel[CoarseRolePermissionsResponse]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_role_controller().set_role_permissions(role_id, payload.permissions, user_id=user_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )

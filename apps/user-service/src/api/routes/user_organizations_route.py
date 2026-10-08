"""User-organization relationship API routes."""

from typing import Annotated, Any
import uuid

from error_contract import ApplicationError, BadRequestError, render_error_message
from fastapi import APIRouter, Depends, Query, Request, Response

from src.api.dependencies import keycloak_request_scope, require_auth, require_permission
from src.controller import get_user_organization_controller
from src.controller.base import BaseController
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.organizations import (
    AssignableOrganizationUsersResponse,
    BulkUserAssignRequest,
    UserOrganizationAssignRequest,
    UserOrganizationUpdateRequest,
)


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise BadRequestError() from error


router = APIRouter(
    prefix="",
    tags=["user-organizations"],
    dependencies=[Depends(keycloak_request_scope)],
)


# Organization perspective
@router.get(
    "/organizations/{org_id}/assignable-users",
)
async def get_assignable_users(
    request: Request,
    response: Response,
    org_id: uuid.UUID,
    user_id: Annotated[str, Depends(require_auth)],
    query: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ResponseModel[AssignableOrganizationUsersResponse]:
    """Search users the actor may add to this organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().get_assignable_users(
                org_id, BaseController.parse_user_id(user_id), query, limit
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


@router.get("/organizations/{org_id}/users")
async def get_organization_users(
    request: Request,
    response: Response,
    org_id: str,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
    role_in_org: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    include_inactive: bool = False,
) -> ResponseModel[dict[str, Any]]:
    """Get users in organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().get_organization_users(
                _parse_uuid(org_id),
                role_in_org,
                include_inactive,
                actor_id=BaseController.parse_user_id(user_id),
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


@router.post("/organizations/{org_id}/users")
async def assign_user_to_organization(
    request: Request,
    response: Response,
    org_id: str,
    payload: UserOrganizationAssignRequest,
    user_id: Annotated[str, Depends(require_auth)],
) -> ResponseModel[dict[str, Any]]:
    """Assign user to organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().assign_user_to_organization(
                organization_id=_parse_uuid(org_id),
                user_id=payload.user_id,
                role_in_org=payload.role_in_org,
                is_primary=payload.is_primary,
                assigned_by=BaseController.parse_user_id(user_id),
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


@router.post("/organizations/{org_id}/users/bulk")
async def bulk_assign_users_to_organization(
    request: Request,
    response: Response,
    org_id: str,
    payload: BulkUserAssignRequest,
    user_id: Annotated[str, Depends(require_auth)],
) -> ResponseModel[dict[str, Any]]:
    """Bulk assign users to organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().bulk_assign_users(
                organization_id=_parse_uuid(org_id),
                user_ids=payload.user_ids,
                role_in_org=payload.role_in_org,
                assigned_by=BaseController.parse_user_id(user_id),
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


@router.patch("/organizations/{org_id}/users/{target_user_id}")
async def update_user_organization(
    request: Request,
    response: Response,
    org_id: str,
    target_user_id: str,
    payload: UserOrganizationUpdateRequest,
    user_id: Annotated[str, Depends(require_auth)],
) -> ResponseModel[dict[str, Any]]:
    """Update user's role in organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().update_user_organization(
                organization_id=_parse_uuid(org_id),
                target_user_id=_parse_uuid(target_user_id),
                new_role=payload.role_in_org,
                actor_id=BaseController.parse_user_id(user_id),
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


@router.delete("/organizations/{org_id}/users/{target_user_id}")
async def remove_user_from_organization(
    request: Request,
    response: Response,
    org_id: str,
    target_user_id: str,
    user_id: Annotated[str, Depends(require_auth)],
) -> ResponseModel[dict[str, Any]]:
    """Remove user from organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().remove_user_from_organization(
                organization_id=_parse_uuid(org_id),
                target_user_id=_parse_uuid(target_user_id),
                actor_id=BaseController.parse_user_id(user_id),
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


# User perspective
@router.get("/users/{target_user_id}/organizations")
async def get_user_organizations(
    request: Request,
    response: Response,
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:read"))],
    include_inactive: bool = False,
) -> ResponseModel[dict[str, Any]]:
    """Get organizations user belongs to."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().get_user_organizations(
                _parse_uuid(target_user_id), include_inactive
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


@router.get("/users/me/organizations")
async def get_my_organizations(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("user:read"))],
    include_inactive: bool = False,
) -> ResponseModel[dict[str, Any]]:
    """Get current user's organizations."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().get_my_organizations(
                BaseController.parse_user_id(user_id), include_inactive
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


@router.post(
    "/users/{target_user_id}/organizations/{org_id}/set-primary",
)
async def set_primary_organization(
    request: Request,
    response: Response,
    target_user_id: str,
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:update"))],
) -> ResponseModel[dict[str, Any]]:
    """Set organization as primary for user."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().set_primary_organization(
                _parse_uuid(target_user_id), _parse_uuid(org_id)
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


@router.get("/users/{target_user_id}/organizations/primary")
async def get_primary_organization(
    request: Request,
    response: Response,
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:read"))],
) -> ResponseModel[dict[str, Any]]:
    """Get user's primary organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().get_primary_organization(_parse_uuid(target_user_id)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/users/{target_user_id}/organizations/managed")
async def get_managed_organizations(
    request: Request,
    response: Response,
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:read"))],
) -> ResponseModel[dict[str, Any]]:
    """Get organizations where user is unit_manager."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_organization_controller().get_managed_organizations(_parse_uuid(target_user_id)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )

"""Resource permission API routes."""

from typing import Annotated, Any, Literal
import uuid

from error_contract import (
    ApplicationError,
    BadRequestError,
    UnauthorizedError,
    render_error_message,
)
from fastapi import APIRouter, Depends, Query, Request, Response

from src.api.dependencies import (
    require_auth,
    require_auth_or_internal_service_token,
    require_permission,
)
from src.controller import get_resource_permission_controller
from src.controller.base import BaseController
from src.controller.organization_workspace_controller import get_organization_workspace_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.organizations import (
    BulkPermissionGrantRequest,
    OrganizationWorkspaceResponse,
    PermissionCheckRequest,
    ResourcePermissionGrantRequest,
    ScopedResourcePermissionsResponse,
    ScopedResourcePermissionSyncRequest,
)


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise BadRequestError() from error


router = APIRouter(prefix="/permissions", tags=["resource-permissions"])


@router.get(
    "/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}/workspace",
)
async def get_organization_workspace(
    response: Response,
    org_id: uuid.UUID,
    target_type: Literal["organization", "user"],
    target_id: uuid.UUID,
    resource_type: Literal["agent", "rag_collection"],
    request: Request,
    user_id: Annotated[str, Depends(require_auth)],
) -> ResponseModel[OrganizationWorkspaceResponse]:
    """Authorize the organization scope and compose caller-visible resources."""
    try:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        access_token = token.strip() if scheme.lower() == "bearer" else request.cookies.get("access_token")
        if not access_token:
            raise UnauthorizedError()
        return ResponseModel(
            statusCode=200,
            data=await get_organization_workspace_controller().get_workspace(
                actor_id=BaseController.parse_user_id(user_id),
                organization_id=org_id,
                target_type=target_type,
                target_id=target_id,
                resource_type=resource_type,
                access_token=access_token,
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


@router.get(
    "/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}",
)
async def get_scoped_direct_permissions(
    request: Request,
    response: Response,
    org_id: str,
    target_type: Literal["organization", "user"],
    target_id: str,
    resource_type: Literal["agent", "rag_collection"],
    user_id: Annotated[str, Depends(require_auth)],
) -> ResponseModel[ScopedResourcePermissionsResponse]:
    """Return direct permissions for one organization-scoped target."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().get_scoped_direct_permissions(
                actor_id=BaseController.parse_user_id(user_id),
                organization_id=_parse_uuid(org_id),
                target_type=target_type,
                target_id=_parse_uuid(target_id),
                resource_type=resource_type,
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


@router.put(
    "/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}",
)
async def sync_scoped_direct_permissions(
    request: Request,
    response: Response,
    org_id: str,
    target_type: Literal["organization", "user"],
    target_id: str,
    resource_type: Literal["agent", "rag_collection"],
    payload: ScopedResourcePermissionSyncRequest,
    user_id: Annotated[str, Depends(require_auth)],
) -> ResponseModel[ScopedResourcePermissionsResponse]:
    """Synchronize direct permissions for one organization-scoped target."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().sync_scoped_direct_permissions(
                actor_id=BaseController.parse_user_id(user_id),
                organization_id=_parse_uuid(org_id),
                target_type=target_type,
                target_id=_parse_uuid(target_id),
                resource_type=resource_type,
                desired_permissions=[permission.model_dump() for permission in payload.permissions],
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


# Permission checking (used by other services)
@router.post("/check")
async def check_permission(
    request: Request,
    response: Response,
    payload: PermissionCheckRequest,
    _authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[dict[str, Any]]:
    """
    Check if user has permission to access resource.

    Used by agent-service, rag-service, tools-service.
    """
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().check_permission(
                user_id=payload.user_id,
                resource_type=payload.resource_type,
                resource_id=payload.resource_id,
                required_permission=payload.required_permission,
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


# Grant/Revoke permissions - Organization level
@router.post("/organizations/{org_id}/resources")
async def grant_organization_permission(
    request: Request,
    response: Response,
    org_id: str,
    payload: ResourcePermissionGrantRequest,
    user_id: Annotated[str, Depends(require_permission("org:manage-resources"))],
) -> ResponseModel[dict[str, Any]]:
    """Grant resource permission to organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().grant_organization_permission(
                org_id=_parse_uuid(org_id),
                resource_type=payload.resource_type,
                resource_id=payload.resource_id,
                resource_name=payload.resource_name,
                permission_level=payload.permission_level,
                granted_by=BaseController.parse_user_id(user_id),
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


@router.get("/organizations/{org_id}/resources")
async def get_organization_permissions(
    request: Request,
    response: Response,
    org_id: str,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
    resource_type: Annotated[str | None, Query(pattern="^(agent|agent_group|rag_collection|connector)$")] = None,
) -> ResponseModel[dict[str, Any]]:
    """Get all permissions for an organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().get_organization_permissions(
                _parse_uuid(org_id), resource_type, actor_id=BaseController.parse_user_id(user_id)
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


# Grant/Revoke permissions - User level
@router.post("/users/{target_user_id}/resources")
async def grant_user_permission(
    request: Request,
    response: Response,
    target_user_id: str,
    payload: ResourcePermissionGrantRequest,
    user_id: Annotated[str, Depends(require_permission("permission:grant"))],
) -> ResponseModel[dict[str, Any]]:
    """Grant resource permission to individual user."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().grant_user_permission(
                target_user_id=_parse_uuid(target_user_id),
                resource_type=payload.resource_type,
                resource_id=payload.resource_id,
                resource_name=payload.resource_name,
                permission_level=payload.permission_level,
                granted_by=BaseController.parse_user_id(user_id),
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


@router.get("/users/{target_user_id}/resources")
async def get_user_permissions(
    request: Request,
    response: Response,
    target_user_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:read"))],
    resource_type: Annotated[str | None, Query(pattern="^(agent|agent_group|rag_collection|connector)$")] = None,
) -> ResponseModel[dict[str, Any]]:
    """Get direct permissions for a user."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().get_user_permissions_listing(
                _parse_uuid(target_user_id),
                resource_type,
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


# User's accessible resources (combines org + user perms)
@router.get("/users/{target_user_id}/accessible-resources")
async def get_user_accessible_resources(
    request: Request,
    response: Response,
    target_user_id: str,
    _authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
    resource_type: Annotated[str | None, Query(pattern="^(agent|agent_group|rag_collection|connector)$")] = None,
    required_permission: Literal["owner", "admin", "write", "read", "execute"] | None = None,
) -> ResponseModel[dict[str, Any]]:
    """
    Get all resources user can access.

    Combines direct user permissions and direct organization permissions.
    """
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().get_user_accessible_resources(
                target_user_id, resource_type, required_permission
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


@router.get("/users/me/resources")
async def get_my_accessible_resources(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("permission:read"))],
    resource_type: Annotated[str | None, Query(pattern="^(agent|agent_group|rag_collection|connector)$")] = None,
) -> ResponseModel[dict[str, Any]]:
    """Get resources current user can access."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().get_user_accessible_resources(
                BaseController.parse_user_id(user_id), resource_type
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


# Resource perspective
@router.get("/resources/{resource_type}/{resource_id}")
async def get_resource_permissions(
    request: Request,
    response: Response,
    resource_type: str,
    resource_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:read"))],
) -> ResponseModel[dict[str, Any]]:
    """Get all permissions for a resource (organizations + users)."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().get_resource_permissions(
                resource_type, resource_id, actor_id=BaseController.parse_user_id(user_id)
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


# Update/Delete individual permission
@router.patch("/permissions/{permission_id}")
async def update_permission(
    request: Request,
    response: Response,
    permission_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:manage"))],
    permission_level: Annotated[str, Query(pattern="^(owner|admin|write|read|execute)$")],
) -> ResponseModel[dict[str, Any]]:
    """Update permission level."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().update_permission(
                _parse_uuid(permission_id), permission_level, BaseController.parse_user_id(user_id)
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


@router.delete("/permissions/{permission_id}")
async def revoke_permission(
    request: Request,
    response: Response,
    permission_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:manage"))],
) -> ResponseModel[dict[str, Any]]:
    """Revoke permission."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().revoke_permission(
                _parse_uuid(permission_id), BaseController.parse_user_id(user_id)
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


# Bulk operations
@router.post(
    "/resources/{resource_type}/{resource_id}/bulk-grant",
)
async def bulk_grant_permissions(
    request: Request,
    response: Response,
    resource_type: str,
    resource_id: str,
    payload: BulkPermissionGrantRequest,
    user_id: Annotated[str, Depends(require_permission("permission:manage"))],
) -> ResponseModel[dict[str, Any]]:
    """Bulk grant permissions to multiple organizations/users."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().bulk_grant_permissions(
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=payload.resource_name,
                grants=payload.grants,
                granted_by=BaseController.parse_user_id(user_id),
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


# Audit logs
@router.get("/audit/resources/{resource_type}/{resource_id}")
async def get_resource_audit_logs(
    request: Request,
    response: Response,
    resource_type: str,
    resource_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:read"))],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ResponseModel[dict[str, Any]]:
    """Get audit logs for a resource."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().get_resource_audit_logs(
                resource_type,
                resource_id,
                skip,
                limit,
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


@router.get("/audit/organizations/{org_id}")
async def get_organization_audit_logs(
    request: Request,
    response: Response,
    org_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:read"))],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ResponseModel[dict[str, Any]]:
    """Get audit logs for an organization."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().get_organization_audit_logs(
                _parse_uuid(org_id), skip, limit, actor_id=BaseController.parse_user_id(user_id)
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


@router.get("/audit/users/{target_user_id}")
async def get_user_audit_logs(
    request: Request,
    response: Response,
    target_user_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:read"))],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ResponseModel[dict[str, Any]]:
    """Get audit logs for a user."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().get_user_audit_logs(
                _parse_uuid(target_user_id),
                skip,
                limit,
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


@router.get("/audit/recent")
async def get_recent_audit_logs(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("permission:read"))],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ResponseModel[dict[str, Any]]:
    """Get recent audit logs across all permissions."""
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_resource_permission_controller().get_recent_audit_logs(
                limit, actor_id=BaseController.parse_user_id(user_id)
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

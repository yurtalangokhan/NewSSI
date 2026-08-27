"""Resource permission API routes."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import (
    require_auth,
    require_auth_or_internal_service_token,
    require_permission,
)
from src.controller import get_resource_permission_controller
from src.schema.organizations import (
    BulkPermissionGrantRequest,
    PermissionCheckRequest,
    ResourcePermissionGrantRequest,
    ScopedResourcePermissionsResponse,
    ScopedResourcePermissionSyncRequest,
)

router = APIRouter(prefix="/permissions", tags=["resource-permissions"])


@router.get(
    "/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}",
    response_model=ScopedResourcePermissionsResponse,
)
async def get_scoped_direct_permissions(
    org_id: str,
    target_type: Literal["organization", "user"],
    target_id: str,
    resource_type: Literal["agent", "rag_collection"],
    user_id: Annotated[str, Depends(require_auth)],
):
    """Return direct permissions for one organization-scoped target."""
    return await get_resource_permission_controller().get_scoped_direct_permissions(
        actor_id=uuid.UUID(user_id),
        organization_id=uuid.UUID(org_id),
        target_type=target_type,
        target_id=uuid.UUID(target_id),
        resource_type=resource_type,
    )


@router.put(
    "/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}",
    response_model=ScopedResourcePermissionsResponse,
)
async def sync_scoped_direct_permissions(
    org_id: str,
    target_type: Literal["organization", "user"],
    target_id: str,
    resource_type: Literal["agent", "rag_collection"],
    payload: ScopedResourcePermissionSyncRequest,
    user_id: Annotated[str, Depends(require_auth)],
):
    """Synchronize direct permissions for one organization-scoped target."""
    return await get_resource_permission_controller().sync_scoped_direct_permissions(
        actor_id=uuid.UUID(user_id),
        organization_id=uuid.UUID(org_id),
        target_type=target_type,
        target_id=uuid.UUID(target_id),
        resource_type=resource_type,
        desired_permissions=[permission.model_dump() for permission in payload.permissions],
    )


# Permission checking (used by other services)
@router.post("/check")
async def check_permission(
    payload: PermissionCheckRequest,
    _authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
):
    """
    Check if user has permission to access resource.

    Used by agent-service, rag-service, tools-service.
    """
    return await get_resource_permission_controller().check_permission(
        user_id=uuid.UUID(payload.user_id),
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        required_permission=payload.required_permission,
    )


# Grant/Revoke permissions - Organization level
@router.post("/organizations/{org_id}/resources")
async def grant_organization_permission(
    org_id: str,
    payload: ResourcePermissionGrantRequest,
    user_id: Annotated[str, Depends(require_permission("org:manage-resources"))],
):
    """Grant resource permission to organization."""
    return await get_resource_permission_controller().grant_organization_permission(
        org_id=uuid.UUID(org_id),
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        resource_name=payload.resource_name,
        permission_level=payload.permission_level,
        granted_by=uuid.UUID(user_id),
    )


@router.get("/organizations/{org_id}/resources")
async def get_organization_permissions(
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("org:read"))],
    resource_type: str | None = Query(
        None, pattern="^(agent|agent_group|rag_collection|connector)$"
    ),
):
    """Get all permissions for an organization."""
    return await get_resource_permission_controller().get_organization_permissions(
        uuid.UUID(org_id), resource_type
    )


# Grant/Revoke permissions - User level
@router.post("/users/{target_user_id}/resources")
async def grant_user_permission(
    target_user_id: str,
    payload: ResourcePermissionGrantRequest,
    user_id: Annotated[str, Depends(require_permission("permission:grant"))],
):
    """Grant resource permission to individual user."""
    return await get_resource_permission_controller().grant_user_permission(
        target_user_id=uuid.UUID(target_user_id),
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        resource_name=payload.resource_name,
        permission_level=payload.permission_level,
        granted_by=uuid.UUID(user_id),
    )


@router.get("/users/{target_user_id}/resources")
async def get_user_permissions(
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
    resource_type: str | None = Query(
        None, pattern="^(agent|agent_group|rag_collection|connector)$"
    ),
):
    """Get direct permissions for a user."""
    return await get_resource_permission_controller().get_user_permissions_listing(
        uuid.UUID(target_user_id), resource_type
    )


# User's accessible resources (combines org + user perms)
@router.get("/users/{target_user_id}/accessible-resources")
async def get_user_accessible_resources(
    target_user_id: str,
    _authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
    resource_type: str | None = Query(
        None, pattern="^(agent|agent_group|rag_collection|connector)$"
    ),
):
    """
    Get all resources user can access.

    Combines direct user permissions and direct organization permissions.
    """
    return await get_resource_permission_controller().get_user_accessible_resources(
        uuid.UUID(target_user_id), resource_type
    )


@router.get("/users/me/resources")
async def get_my_accessible_resources(
    user_id: Annotated[str, Depends(require_permission("permission:read"))],
    resource_type: str | None = Query(
        None, pattern="^(agent|agent_group|rag_collection|connector)$"
    ),
):
    """Get resources current user can access."""
    return await get_resource_permission_controller().get_user_accessible_resources(
        uuid.UUID(user_id), resource_type
    )


# Resource perspective
@router.get("/resources/{resource_type}/{resource_id}")
async def get_resource_permissions(
    resource_type: str,
    resource_id: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
):
    """Get all permissions for a resource (organizations + users)."""
    return await get_resource_permission_controller().get_resource_permissions(
        resource_type, resource_id
    )


# Update/Delete individual permission
@router.patch("/permissions/{permission_id}")
async def update_permission(
    permission_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:manage"))],
    permission_level: str = Query(..., pattern="^(owner|admin|write|read|execute)$"),
):
    """Update permission level."""
    return await get_resource_permission_controller().update_permission(
        uuid.UUID(permission_id), permission_level, uuid.UUID(user_id)
    )


@router.delete("/permissions/{permission_id}")
async def revoke_permission(
    permission_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:manage"))],
):
    """Revoke permission."""
    return await get_resource_permission_controller().revoke_permission(
        uuid.UUID(permission_id), uuid.UUID(user_id)
    )


# Bulk operations
@router.post("/resources/{resource_type}/{resource_id}/bulk-grant")
async def bulk_grant_permissions(
    resource_type: str,
    resource_id: str,
    payload: BulkPermissionGrantRequest,
    user_id: Annotated[str, Depends(require_permission("permission:manage"))],
):
    """Bulk grant permissions to multiple organizations/users."""
    return await get_resource_permission_controller().bulk_grant_permissions(
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=payload.resource_name,
        grants=payload.grants,
        granted_by=uuid.UUID(user_id),
    )


# Audit logs
@router.get("/audit/resources/{resource_type}/{resource_id}")
async def get_resource_audit_logs(
    resource_type: str,
    resource_id: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Get audit logs for a resource."""
    return await get_resource_permission_controller().get_resource_audit_logs(
        resource_type, resource_id, skip, limit
    )


@router.get("/audit/organizations/{org_id}")
async def get_organization_audit_logs(
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Get audit logs for an organization."""
    return await get_resource_permission_controller().get_organization_audit_logs(
        uuid.UUID(org_id), skip, limit
    )


@router.get("/audit/users/{target_user_id}")
async def get_user_audit_logs(
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Get audit logs for a user."""
    return await get_resource_permission_controller().get_user_audit_logs(
        uuid.UUID(target_user_id), skip, limit
    )


@router.get("/audit/recent")
async def get_recent_audit_logs(
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
    limit: int = Query(100, ge=1, le=500),
):
    """Get recent audit logs across all permissions."""
    return await get_resource_permission_controller().get_recent_audit_logs(limit)

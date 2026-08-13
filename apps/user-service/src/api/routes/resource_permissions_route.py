"""Resource permission API routes."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import (
    require_auth,
    require_auth_or_internal_service_token,
    require_permission,
)
from src.core.exceptions import ForbiddenError, NotFoundError
from src.schema.organizations import (
    BulkPermissionGrantRequest,
    PermissionCheckRequest,
    ResourcePermissionGrantRequest,
    ScopedResourcePermissionsResponse,
    ScopedResourcePermissionSyncRequest,
)
from src.service import (
    get_permission_audit_service,
    get_resource_permission_service,
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
    service = get_resource_permission_service()
    try:
        permissions = await service.get_scoped_direct_permissions(
            actor_id=uuid.UUID(user_id),
            organization_id=uuid.UUID(org_id),
            target_type=target_type,
            target_id=uuid.UUID(target_id),
            resource_type=resource_type,
        )
        return {"permissions": permissions, "count": len(permissions)}
    except ForbiddenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


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
    service = get_resource_permission_service()
    try:
        permissions = await service.sync_scoped_direct_permissions(
            actor_id=uuid.UUID(user_id),
            organization_id=uuid.UUID(org_id),
            target_type=target_type,
            target_id=uuid.UUID(target_id),
            resource_type=resource_type,
            desired_permissions=[permission.model_dump() for permission in payload.permissions],
        )
        return {"permissions": permissions, "count": len(permissions)}
    except ForbiddenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


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
    service = get_resource_permission_service()
    return await service.check_resource_access(
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
    service = get_resource_permission_service()
    try:
        return await service.grant_permission(
            resource_type=payload.resource_type,
            resource_id=payload.resource_id,
            resource_name=payload.resource_name,
            organization_id=uuid.UUID(org_id),
            permission_level=payload.permission_level,
            granted_by=uuid.UUID(user_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/organizations/{org_id}/resources")
async def get_organization_permissions(
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("org:read"))],
    resource_type: str | None = Query(
        None, pattern="^(agent|agent_group|rag_collection|connector)$"
    ),
):
    """Get all permissions for an organization."""
    service = get_resource_permission_service()
    perms = await service.perm_repo.get_organization_permissions(uuid.UUID(org_id), resource_type)
    return {"permissions": perms, "count": len(perms)}


# Grant/Revoke permissions - User level
@router.post("/users/{target_user_id}/resources")
async def grant_user_permission(
    target_user_id: str,
    payload: ResourcePermissionGrantRequest,
    user_id: Annotated[str, Depends(require_permission("permission:grant"))],
):
    """Grant resource permission to individual user."""
    service = get_resource_permission_service()
    try:
        return await service.grant_permission(
            resource_type=payload.resource_type,
            resource_id=payload.resource_id,
            resource_name=payload.resource_name,
            user_id=uuid.UUID(target_user_id),
            permission_level=payload.permission_level,
            granted_by=uuid.UUID(user_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/users/{target_user_id}/resources")
async def get_user_permissions(
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
    resource_type: str | None = Query(
        None, pattern="^(agent|agent_group|rag_collection|connector)$"
    ),
):
    """Get direct permissions for a user."""
    service = get_resource_permission_service()
    perms = await service.perm_repo.get_user_permissions(uuid.UUID(target_user_id), resource_type)
    return {"permissions": perms, "count": len(perms)}


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
    service = get_resource_permission_service()
    resources = await service.get_user_accessible_resources(
        uuid.UUID(target_user_id), resource_type
    )
    return {"resources": resources, "count": len(resources)}


@router.get("/users/me/resources")
async def get_my_accessible_resources(
    user_id: Annotated[str, Depends(require_permission("permission:read"))],
    resource_type: str | None = Query(
        None, pattern="^(agent|agent_group|rag_collection|connector)$"
    ),
):
    """Get resources current user can access."""
    service = get_resource_permission_service()
    resources = await service.get_user_accessible_resources(uuid.UUID(user_id), resource_type)
    return {"resources": resources, "count": len(resources)}


# Resource perspective
@router.get("/resources/{resource_type}/{resource_id}")
async def get_resource_permissions(
    resource_type: str,
    resource_id: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
):
    """Get all permissions for a resource (organizations + users)."""
    service = get_resource_permission_service()
    perms = await service.get_resource_permissions(resource_type, resource_id)
    return {"permissions": perms, "count": len(perms)}


# Update/Delete individual permission
@router.patch("/permissions/{permission_id}")
async def update_permission(
    permission_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:manage"))],
    permission_level: str = Query(..., pattern="^(owner|admin|write|read|execute)$"),
):
    """Update permission level."""
    service = get_resource_permission_service()
    try:
        return await service.update_permission(
            uuid.UUID(permission_id), permission_level, uuid.UUID(user_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/permissions/{permission_id}")
async def revoke_permission(
    permission_id: str,
    user_id: Annotated[str, Depends(require_permission("permission:manage"))],
):
    """Revoke permission."""
    service = get_resource_permission_service()
    try:
        deleted = await service.revoke_permission(uuid.UUID(permission_id), uuid.UUID(user_id))
        if not deleted:
            raise HTTPException(status_code=404, detail="Permission not found")
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# Bulk operations
@router.post("/resources/{resource_type}/{resource_id}/bulk-grant")
async def bulk_grant_permissions(
    resource_type: str,
    resource_id: str,
    payload: BulkPermissionGrantRequest,
    user_id: Annotated[str, Depends(require_permission("permission:manage"))],
):
    """Bulk grant permissions to multiple organizations/users."""
    service = get_resource_permission_service()
    result = await service.bulk_grant_permissions(
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=payload.resource_name,
        grants=payload.grants,
        granted_by=uuid.UUID(user_id),
    )
    return result


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
    service = get_permission_audit_service()
    logs, total = await service.get_resource_audit_logs(resource_type, resource_id, skip, limit)
    return {"logs": logs, "total": total, "skip": skip, "limit": limit}


@router.get("/audit/organizations/{org_id}")
async def get_organization_audit_logs(
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Get audit logs for an organization."""
    service = get_permission_audit_service()
    logs, total = await service.get_target_audit_logs(
        "organization", uuid.UUID(org_id), skip, limit
    )
    return {"logs": logs, "total": total, "skip": skip, "limit": limit}


@router.get("/audit/users/{target_user_id}")
async def get_user_audit_logs(
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Get audit logs for a user."""
    service = get_permission_audit_service()
    logs, total = await service.get_target_audit_logs(
        "user", uuid.UUID(target_user_id), skip, limit
    )
    return {"logs": logs, "total": total, "skip": skip, "limit": limit}


@router.get("/audit/recent")
async def get_recent_audit_logs(
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
    limit: int = Query(100, ge=1, le=500),
):
    """Get recent audit logs across all permissions."""
    service = get_permission_audit_service()
    logs = await service.get_recent_audit_logs(limit)
    return {"logs": logs, "count": len(logs)}

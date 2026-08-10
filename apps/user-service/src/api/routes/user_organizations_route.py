"""User-organization relationship API routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import require_auth, require_permission
from src.core.exceptions import ForbiddenError
from src.schema.organizations import (
    BulkUserAssignRequest,
    UserOrganizationAssignRequest,
    UserOrganizationUpdateRequest,
)
from src.service import get_user_organization_service

router = APIRouter(prefix="", tags=["user-organizations"])


# Organization perspective
@router.get("/organizations/{org_id}/users")
async def get_organization_users(
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("org:read"))],
    role_in_org: str | None = Query(None, pattern="^(unit_manager|member|viewer)$"),
    include_inactive: bool = False,
):
    """Get users in organization."""
    service = get_user_organization_service()
    users = await service.get_organization_users(uuid.UUID(org_id), role_in_org, include_inactive)
    return {"users": users, "count": len(users)}


@router.post("/organizations/{org_id}/users")
async def assign_user_to_organization(
    org_id: str,
    payload: UserOrganizationAssignRequest,
    user_id: Annotated[str, Depends(require_auth)],
):
    """Assign user to organization."""
    service = get_user_organization_service()
    try:
        return await service.assign_user_to_organization(
            user_id=payload.user_id,
            organization_id=uuid.UUID(org_id),
            role_in_org=payload.role_in_org,
            is_primary=payload.is_primary,
            assigned_by=uuid.UUID(user_id),
        )
    except ForbiddenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/organizations/{org_id}/users/bulk")
async def bulk_assign_users_to_organization(
    org_id: str,
    payload: BulkUserAssignRequest,
    user_id: Annotated[str, Depends(require_auth)],
):
    """Bulk assign users to organization."""
    service = get_user_organization_service()
    try:
        result = await service.bulk_assign_users(
            user_ids=payload.user_ids,
            organization_id=uuid.UUID(org_id),
            role_in_org=payload.role_in_org,
            assigned_by=uuid.UUID(user_id),
        )
        return result
    except ForbiddenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.patch("/organizations/{org_id}/users/{target_user_id}")
async def update_user_organization(
    org_id: str,
    target_user_id: str,
    payload: UserOrganizationUpdateRequest,
    user_id: Annotated[str, Depends(require_auth)],
):
    """Update user's role in organization."""
    service = get_user_organization_service()
    try:
        if payload.role_in_org:
            return await service.update_user_organization_role(
                user_id=uuid.UUID(target_user_id),
                organization_id=uuid.UUID(org_id),
                new_role=payload.role_in_org,
                actor_id=uuid.UUID(user_id),
            )
        else:
            raise HTTPException(status_code=400, detail="No updates provided")
    except ForbiddenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/organizations/{org_id}/users/{target_user_id}")
async def remove_user_from_organization(
    org_id: str,
    target_user_id: str,
    user_id: Annotated[str, Depends(require_auth)],
):
    """Remove user from organization."""
    service = get_user_organization_service()
    try:
        deleted = await service.remove_user_from_organization(
            uuid.UUID(target_user_id), uuid.UUID(org_id), actor_id=uuid.UUID(user_id)
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="User-organization relationship not found")
        return {"success": True}
    except ForbiddenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


# User perspective
@router.get("/users/{target_user_id}/organizations")
async def get_user_organizations(
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:read"))],
    include_inactive: bool = False,
):
    """Get organizations user belongs to."""
    service = get_user_organization_service()
    orgs = await service.get_user_organizations(uuid.UUID(target_user_id), include_inactive)
    return {"organizations": orgs, "count": len(orgs)}


@router.get("/users/me/organizations")
async def get_my_organizations(
    user_id: Annotated[str, Depends(require_permission("user:read"))],
    include_inactive: bool = False,
):
    """Get current user's organizations."""
    service = get_user_organization_service()
    orgs = await service.get_user_organizations(uuid.UUID(user_id), include_inactive)
    return {"organizations": orgs, "count": len(orgs)}


@router.post("/users/{target_user_id}/organizations/{org_id}/set-primary")
async def set_primary_organization(
    target_user_id: str,
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:update"))],
):
    """Set organization as primary for user."""
    service = get_user_organization_service()
    try:
        return await service.set_primary_organization(uuid.UUID(target_user_id), uuid.UUID(org_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/users/{target_user_id}/organizations/primary")
async def get_primary_organization(
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:read"))],
):
    """Get user's primary organization."""
    service = get_user_organization_service()
    org = await service.get_user_primary_organization(uuid.UUID(target_user_id))
    if not org:
        raise HTTPException(status_code=404, detail="No primary organization set")
    return org


@router.get("/users/{target_user_id}/organizations/managed")
async def get_managed_organizations(
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:read"))],
):
    """Get organizations where user is unit_manager."""
    service = get_user_organization_service()
    orgs = await service.get_user_managed_organizations(uuid.UUID(target_user_id))
    return {"organizations": orgs, "count": len(orgs)}

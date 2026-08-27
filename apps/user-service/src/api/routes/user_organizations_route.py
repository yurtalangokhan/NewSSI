"""User-organization relationship API routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import require_auth, require_permission
from src.controller import get_user_organization_controller
from src.schema.organizations import (
    BulkUserAssignRequest,
    UserOrganizationAssignRequest,
    UserOrganizationUpdateRequest,
)

router = APIRouter(prefix="", tags=["user-organizations"])


# Organization perspective
@router.get("/organizations/{org_id}/users")
async def get_organization_users(
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("org:read"))],
    role_in_org: str | None = Query(None, min_length=1, max_length=100),
    include_inactive: bool = False,
):
    """Get users in organization."""
    return await get_user_organization_controller().get_organization_users(
        uuid.UUID(org_id), role_in_org, include_inactive
    )


@router.post("/organizations/{org_id}/users")
async def assign_user_to_organization(
    org_id: str,
    payload: UserOrganizationAssignRequest,
    user_id: Annotated[str, Depends(require_auth)],
):
    """Assign user to organization."""
    return await get_user_organization_controller().assign_user_to_organization(
        organization_id=uuid.UUID(org_id),
        user_id=payload.user_id,
        role_in_org=payload.role_in_org,
        is_primary=payload.is_primary,
        assigned_by=uuid.UUID(user_id),
    )


@router.post("/organizations/{org_id}/users/bulk")
async def bulk_assign_users_to_organization(
    org_id: str,
    payload: BulkUserAssignRequest,
    user_id: Annotated[str, Depends(require_auth)],
):
    """Bulk assign users to organization."""
    return await get_user_organization_controller().bulk_assign_users(
        organization_id=uuid.UUID(org_id),
        user_ids=payload.user_ids,
        role_in_org=payload.role_in_org,
        assigned_by=uuid.UUID(user_id),
    )


@router.patch("/organizations/{org_id}/users/{target_user_id}")
async def update_user_organization(
    org_id: str,
    target_user_id: str,
    payload: UserOrganizationUpdateRequest,
    user_id: Annotated[str, Depends(require_auth)],
):
    """Update user's role in organization."""
    return await get_user_organization_controller().update_user_organization(
        organization_id=uuid.UUID(org_id),
        target_user_id=uuid.UUID(target_user_id),
        new_role=payload.role_in_org,
        actor_id=uuid.UUID(user_id),
    )


@router.delete("/organizations/{org_id}/users/{target_user_id}")
async def remove_user_from_organization(
    org_id: str,
    target_user_id: str,
    user_id: Annotated[str, Depends(require_auth)],
):
    """Remove user from organization."""
    return await get_user_organization_controller().remove_user_from_organization(
        organization_id=uuid.UUID(org_id),
        target_user_id=uuid.UUID(target_user_id),
        actor_id=uuid.UUID(user_id),
    )


# User perspective
@router.get("/users/{target_user_id}/organizations")
async def get_user_organizations(
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:read"))],
    include_inactive: bool = False,
):
    """Get organizations user belongs to."""
    return await get_user_organization_controller().get_user_organizations(
        uuid.UUID(target_user_id), include_inactive
    )


@router.get("/users/me/organizations")
async def get_my_organizations(
    user_id: Annotated[str, Depends(require_permission("user:read"))],
    include_inactive: bool = False,
):
    """Get current user's organizations."""
    return await get_user_organization_controller().get_my_organizations(
        uuid.UUID(user_id), include_inactive
    )


@router.post("/users/{target_user_id}/organizations/{org_id}/set-primary")
async def set_primary_organization(
    target_user_id: str,
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:update"))],
):
    """Set organization as primary for user."""
    return await get_user_organization_controller().set_primary_organization(
        uuid.UUID(target_user_id), uuid.UUID(org_id)
    )


@router.get("/users/{target_user_id}/organizations/primary")
async def get_primary_organization(
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:read"))],
):
    """Get user's primary organization."""
    return await get_user_organization_controller().get_primary_organization(
        uuid.UUID(target_user_id)
    )


@router.get("/users/{target_user_id}/organizations/managed")
async def get_managed_organizations(
    target_user_id: str,
    _user_id: Annotated[str, Depends(require_permission("user:read"))],
):
    """Get organizations where user is unit_manager."""
    return await get_user_organization_controller().get_managed_organizations(
        uuid.UUID(target_user_id)
    )

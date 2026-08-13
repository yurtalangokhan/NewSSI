"""Pydantic schemas for organization management."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class OrganizationCreateRequest(BaseModel):
    """Request to create new organization."""

    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)
    parent_id: uuid.UUID | None = None
    metadata: dict | None = None


class OrganizationUpdateRequest(BaseModel):
    """Request to update organization."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    is_active: bool | None = None
    order_index: int | None = None
    metadata: dict | None = None


class OrganizationMoveRequest(BaseModel):
    """Request to move organization to new parent."""

    new_parent_id: uuid.UUID | None = None


class OrganizationLayoutPosition(BaseModel):
    """One canvas coordinate for an organization."""

    organization_id: uuid.UUID
    x: float = Field(ge=-100_000_000, le=100_000_000, allow_inf_nan=False)
    y: float = Field(ge=-100_000_000, le=100_000_000, allow_inf_nan=False)


class OrganizationLayoutUpdateRequest(BaseModel):
    """Shared organization positions to create or update atomically."""

    positions: list[OrganizationLayoutPosition] = Field(max_length=100_000)


class OrganizationLayoutReadResponse(BaseModel):
    """Shared positions and the organizations that the actor may move."""

    positions: list[OrganizationLayoutPosition]
    writable_organization_ids: list[uuid.UUID]


class OrganizationLayoutUpdateResponse(BaseModel):
    """Positions saved by a shared-layout update."""

    positions: list[OrganizationLayoutPosition]
    count: int


class OrganizationMemberIdentity(BaseModel):
    """Public identity fields for a directly assigned organization member."""

    id: uuid.UUID
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


class OrganizationDirectMember(BaseModel):
    """One active direct organization membership."""

    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role_in_org: str
    is_active: bool
    user: OrganizationMemberIdentity


class OrganizationMembersByUnitResponse(BaseModel):
    """Active direct memberships grouped by organization ID."""

    members_by_organization: dict[str, list[OrganizationDirectMember]]
    count: int


class UserOrganizationAssignRequest(BaseModel):
    """Request to assign user to organization."""

    user_id: uuid.UUID
    role_in_org: str = Field(..., min_length=1, max_length=100)
    is_primary: bool = False


class UserOrganizationUpdateRequest(BaseModel):
    """Request to update user-organization relationship."""

    role_in_org: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None


class ResourcePermissionGrantRequest(BaseModel):
    """Request to grant permission."""

    resource_type: str = Field(..., pattern="^(agent|agent_group|rag_collection|connector)$")
    resource_id: str = Field(..., min_length=1, max_length=255)
    resource_name: str = Field(..., min_length=1, max_length=255)
    permission_level: str = Field(..., pattern="^(owner|admin|write|read|execute)$")
    organization_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


class PermissionCheckRequest(BaseModel):
    """Request to check permission."""

    user_id: str
    resource_type: str
    resource_id: str
    required_permission: str = "read"


class BulkPermissionGrantRequest(BaseModel):
    """Request for bulk permission grant."""

    resource_type: str
    resource_id: str
    resource_name: str
    grants: list[dict] = Field(..., min_length=1)
    # Each grant: {"organization_id": uuid, "permission_level": str} or {"user_id": uuid, "permission_level": str}


class ResourcePermissionSyncItem(BaseModel):
    """One desired direct permission in a scoped synchronization request."""

    resource_id: str = Field(..., min_length=1, max_length=255)
    resource_name: str = Field(..., min_length=1, max_length=255)
    permission_level: str = Field(..., pattern="^(owner|admin|write|read|execute)$")


class ScopedResourcePermissionSyncRequest(BaseModel):
    """Desired direct permissions for one organization-scoped target and resource type."""

    permissions: list[ResourcePermissionSyncItem] = Field(default_factory=list, max_length=200)


class ScopedResourcePermissionsResponse(BaseModel):
    """Direct permissions returned by a scoped read or synchronization request."""

    permissions: list[dict[str, Any]]
    count: int


class BulkUserAssignRequest(BaseModel):
    """Request for bulk user assignment."""

    user_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)
    role_in_org: str = Field(default="member", min_length=1, max_length=100)

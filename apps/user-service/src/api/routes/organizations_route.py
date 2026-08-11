"""Organization management API routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from src.api.dependencies import require_permission
from src.controller import get_organization_layout_controller
from src.core.exceptions import ConflictError
from src.schema.organizations import (
    OrganizationCreateRequest,
    OrganizationLayoutReadResponse,
    OrganizationLayoutUpdateRequest,
    OrganizationLayoutUpdateResponse,
    OrganizationMoveRequest,
    OrganizationUpdateRequest,
)
from src.service import get_organization_service, get_user_organization_service

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("")
async def list_organizations(
    _user_id: Annotated[str, Depends(require_permission("org:list"))],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_active: bool | None = None,
    parent_id: str | None = None,
):
    """List organizations with pagination."""
    service = get_organization_service()
    parent_uuid = uuid.UUID(parent_id) if parent_id else None
    orgs, total = await service.list_organizations(skip, limit, is_active, parent_uuid)
    return {"items": orgs, "total": total, "skip": skip, "limit": limit}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreateRequest,
    user_id: Annotated[str, Depends(require_permission("org:create"))],
):
    """Create new organization."""
    service = get_organization_service()
    try:
        return await service.create_organization(
            name=payload.name,
            code=payload.code,
            parent_id=payload.parent_id,
            description=payload.description,
            created_by=uuid.UUID(user_id),
            metadata=payload.metadata,
        )
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/tree")
async def get_organization_tree(
    _user_id: Annotated[str, Depends(require_permission("org:read"))],
    root_id: str | None = None,
    max_depth: int | None = Query(None, ge=1, le=10),
):
    """Get hierarchical organization tree."""
    service = get_organization_service()
    root_uuid = uuid.UUID(root_id) if root_id else None
    try:
        return await service.get_organization_tree(root_uuid, max_depth)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/stats")
async def get_organization_stats(
    _user_id: Annotated[str, Depends(require_permission("org:read"))],
):
    """Get organization statistics."""
    service = get_organization_service()
    try:
        return await service.get_organization_stats()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/search")
async def search_organizations(
    _user_id: Annotated[str, Depends(require_permission("org:read"))],
    q: str = Query(..., min_length=2),
    max_results: int = Query(20, ge=1, le=100),
):
    """Search organizations by name, code, or description."""
    service = get_organization_service()
    try:
        results = await service.search_organizations(q, max_results)
        return {"results": results, "query": q}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/layout", response_model=OrganizationLayoutReadResponse)
async def get_organization_layout(
    user_id: Annotated[str, Depends(require_permission("org:read"))],
) -> OrganizationLayoutReadResponse:
    """Return the shared canvas positions and organizations the actor may move."""
    result = await get_organization_layout_controller().get_layout(uuid.UUID(user_id))
    return OrganizationLayoutReadResponse.model_validate(result)


@router.put("/layout", response_model=OrganizationLayoutUpdateResponse)
async def save_organization_layout(
    payload: OrganizationLayoutUpdateRequest,
    user_id: Annotated[str, Depends(require_permission("org:update"))],
) -> OrganizationLayoutUpdateResponse:
    """Atomically create or update shared canvas positions."""
    positions = [position.model_dump() for position in payload.positions]
    result = await get_organization_layout_controller().save_layout(
        uuid.UUID(user_id), positions
    )
    return OrganizationLayoutUpdateResponse.model_validate(result)


@router.get("/{org_id}")
async def get_organization(
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("org:read"))],
):
    """Get organization details."""
    service = get_organization_service()
    org = await service.get_organization(uuid.UUID(org_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.get("/{org_id}/management-capability")
async def get_management_capability(
    org_id: str,
    user_id: Annotated[str, Depends(require_permission("org:read"))],
):
    """Return whether the authenticated actor may manage the organization."""
    organization_id = uuid.UUID(org_id)
    organization = await get_organization_service().get_organization(organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    editable = await get_user_organization_service().can_manage_organization(
        uuid.UUID(user_id), organization_id
    )
    return {"editable": editable}


@router.patch("/{org_id}")
async def update_organization(
    org_id: str,
    payload: OrganizationUpdateRequest,
    user_id: Annotated[str, Depends(require_permission("org:update"))],
):
    """Update organization."""
    service = get_organization_service()
    try:
        updates = payload.model_dump(exclude_unset=True)
        org = await service.update_organization(uuid.UUID(org_id), **updates)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        return org
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: str,
    user_id: Annotated[str, Depends(require_permission("org:delete"))],
    cascade: bool = Query(False),
):
    """Delete organization (optionally with descendants)."""
    service = get_organization_service()
    try:
        deleted = await service.delete_organization(uuid.UUID(org_id), cascade=cascade)
        if not deleted:
            raise HTTPException(status_code=404, detail="Organization not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{org_id}/move")
async def move_organization(
    org_id: str,
    payload: OrganizationMoveRequest,
    user_id: Annotated[str, Depends(require_permission("org:move"))],
):
    """Move organization to new parent."""
    service = get_organization_service()
    try:
        org = await service.move_organization(uuid.UUID(org_id), payload.new_parent_id)
        return org
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{org_id}/children")
async def get_organization_children(
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("org:read"))],
    direct_only: bool = Query(True),
):
    """Get child organizations."""
    service = get_organization_service()
    children = await service.get_organization_children(uuid.UUID(org_id), direct_only)
    return {"children": children, "count": len(children)}


@router.get("/{org_id}/ancestors")
async def get_organization_ancestors(
    org_id: str,
    _user_id: Annotated[str, Depends(require_permission("org:read"))],
):
    """Get ancestor organizations (path to root)."""
    service = get_organization_service()
    ancestors = await service.get_organization_ancestors(uuid.UUID(org_id))
    return {"ancestors": ancestors, "count": len(ancestors)}

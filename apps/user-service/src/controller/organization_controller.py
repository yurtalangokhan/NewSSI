"""HTTP error translation for organization management operations."""

import uuid
from typing import Any

from src.core.exceptions import ConflictError
from src.service import get_organization_service, get_user_organization_service

from .base import BaseController


class OrganizationController(BaseController):
    """Coordinate organization requests and translate domain errors for HTTP."""

    def __init__(self) -> None:
        self.org_service = get_organization_service()
        self.user_org_service = get_user_organization_service()

    async def list_organizations(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        orgs, total = await self.org_service.list_organizations(skip, limit, is_active, parent_id)
        return {"items": orgs, "total": total, "skip": skip, "limit": limit}

    async def create_organization(
        self,
        name: str,
        code: str,
        parent_id: uuid.UUID | None = None,
        description: str | None = None,
        created_by: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.org_service.create_organization(
                name=name,
                code=code,
                parent_id=parent_id,
                description=description,
                created_by=created_by,
                metadata=metadata,
            )
        except ConflictError as e:
            self._raise_conflict(str(e))
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def get_organization_tree(
        self,
        root_id: uuid.UUID | None = None,
        max_depth: int | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.org_service.get_organization_tree(root_id, max_depth)
        except ValueError as e:
            self._raise_not_found(str(e))

    async def get_organization_stats(self) -> dict[str, Any]:
        try:
            return await self.org_service.get_organization_stats()
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def search_organizations(self, q: str, max_results: int = 20) -> dict[str, Any]:
        try:
            results = await self.org_service.search_organizations(q, max_results)
            return {"results": results, "query": q}
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def get_organization(self, org_id: uuid.UUID) -> dict[str, Any]:
        org = await self.org_service.get_organization(org_id)
        if not org:
            self._raise_not_found("organization.not_found")
        return org

    async def get_management_capability(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[str, Any]:
        organization = await self.org_service.get_organization(org_id)
        if not organization:
            self._raise_not_found("organization.not_found")
        editable = await self.user_org_service.can_manage_organization(user_id, org_id)
        return {"editable": editable}

    async def update_organization(self, org_id: uuid.UUID, **updates: Any) -> dict[str, Any]:
        try:
            org = await self.org_service.update_organization(org_id, **updates)
            if not org:
                self._raise_not_found("organization.not_found")
            return org
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def delete_organization(
        self, org_id: uuid.UUID, cascade: bool = False
    ) -> dict[str, Any] | None:
        try:
            deleted = await self.org_service.delete_organization(org_id, cascade=cascade)
            if not deleted:
                self._raise_not_found("organization.not_found")
            return None
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def move_organization(
        self, org_id: uuid.UUID, new_parent_id: uuid.UUID | None
    ) -> dict[str, Any]:
        try:
            return await self.org_service.move_organization(org_id, new_parent_id)
        except ConflictError as e:
            self._raise_conflict(str(e))
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def get_organization_children(
        self, parent_id: uuid.UUID, direct_only: bool = True
    ) -> dict[str, Any]:
        children = await self.org_service.get_organization_children(parent_id, direct_only)
        return {"children": children, "count": len(children)}

    async def get_organization_ancestors(self, org_id: uuid.UUID) -> dict[str, Any]:
        ancestors = await self.org_service.get_organization_ancestors(org_id)
        return {"ancestors": ancestors, "count": len(ancestors)}


_organization_controller_instance: OrganizationController | None = None


def get_organization_controller() -> OrganizationController:
    """Get the organization controller singleton."""
    global _organization_controller_instance
    if _organization_controller_instance is None:
        _organization_controller_instance = OrganizationController()
    return _organization_controller_instance

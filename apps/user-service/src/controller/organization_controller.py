"""HTTP error translation for organization management operations."""

from typing import Any
import uuid

from error_contract.identity import ConflictError

from src.service import get_organization_service, get_user_organization_service
from src.service.organization_scope_service import OrganizationScopeService
from src.service.scoped_organization_service import ScopedOrganizationService

from .base import BaseController, translate_domain_errors


class OrganizationController(BaseController):
    """Coordinate organization requests and translate domain errors for HTTP."""

    def __init__(self) -> None:
        self.org_service = get_organization_service()
        self.user_org_service = get_user_organization_service()

    def _service(self, actor_id):
        return ScopedOrganizationService(actor_id, self.org_service) if actor_id else self.org_service

    @translate_domain_errors
    async def get_scope(self, actor_id: uuid.UUID) -> dict[str, Any]:
        scope = await OrganizationScopeService().resolve(actor_id)
        return {"global_access": scope.global_access, "root_ids": scope.root_ids}

    @translate_domain_errors
    async def list_organizations(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
        parent_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        orgs, total = await self._service(actor_id).list_organizations(skip, limit, is_active, parent_id)
        return {"items": orgs, "total": total, "skip": skip, "limit": limit}

    @translate_domain_errors
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
            return await self._service(created_by).create_organization(
                name=name,
                code=code,
                parent_id=parent_id,
                description=description,
                created_by=created_by,
                metadata=metadata,
            )
        except ConflictError:
            raise

    @translate_domain_errors
    async def get_organization_tree(
        self,
        root_id: uuid.UUID | None = None,
        max_depth: int | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        return await self._service(actor_id).get_organization_tree(root_id, max_depth)

    @translate_domain_errors
    async def get_organization_stats(self, actor_id: uuid.UUID | None = None) -> dict[str, Any]:
        return await self._service(actor_id).get_organization_stats()

    @translate_domain_errors
    async def search_organizations(
        self, q: str, max_results: int = 20, actor_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        results = await self._service(actor_id).search_organizations(q, max_results)
        return {"results": results, "query": q}

    @translate_domain_errors
    async def get_organization(self, org_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> dict[str, Any]:
        org = await self._service(actor_id).get_organization(org_id)
        if not org:
            self._raise_not_found("organization.not_found")
        return org

    @translate_domain_errors
    async def get_management_capability(self, org_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
        organization = await self._service(user_id).get_organization(org_id)
        if not organization:
            self._raise_not_found("organization.not_found")
        editable = await self.user_org_service.can_manage_organization(user_id, org_id)
        scope = await OrganizationScopeService().resolve(user_id)
        return {
            "editable": editable,
            "can_move": editable and (scope.global_access or org_id not in scope.root_ids),
            "can_delete": editable and (scope.global_access or org_id not in scope.root_ids),
        }

    @translate_domain_errors
    async def update_organization(
        self, org_id: uuid.UUID, actor_id: uuid.UUID | None = None, **updates: Any
    ) -> dict[str, Any]:
        org = await self._service(actor_id).update_organization(org_id, **updates)
        if not org:
            self._raise_not_found("organization.not_found")
        return org

    @translate_domain_errors
    async def delete_organization(
        self, org_id: uuid.UUID, cascade: bool = False, actor_id: uuid.UUID | None = None
    ) -> dict[str, Any] | None:
        deleted = await self._service(actor_id).delete_organization(org_id, cascade=cascade)
        if not deleted:
            self._raise_not_found("organization.not_found")
        return None

    @translate_domain_errors
    async def move_organization(
        self, org_id: uuid.UUID, new_parent_id: uuid.UUID | None, actor_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        try:
            return await self._service(actor_id).move_organization(org_id, new_parent_id)
        except ConflictError:
            raise

    @translate_domain_errors
    async def get_organization_children(
        self, parent_id: uuid.UUID, direct_only: bool = True, actor_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        children = await self._service(actor_id).get_organization_children(parent_id, direct_only)
        return {"children": children, "count": len(children)}

    @translate_domain_errors
    async def get_organization_ancestors(self, org_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> dict[str, Any]:
        ancestors = await self._service(actor_id).get_organization_ancestors(org_id)
        return {"ancestors": ancestors, "count": len(ancestors)}


_organization_controller_instance: OrganizationController | None = None


def get_organization_controller() -> OrganizationController:
    """Get the organization controller singleton."""
    global _organization_controller_instance
    if _organization_controller_instance is None:
        _organization_controller_instance = OrganizationController()
    return _organization_controller_instance

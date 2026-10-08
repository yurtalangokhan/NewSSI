"""Apply an actor's scope to organization use cases."""

from typing import Any
import uuid

from error_contract.identity import ForbiddenError

from src.repository import OrganizationRepository, UserOrganizationRepository
from src.service.organization_scope_service import OrganizationScopeService
from src.service.organization_service import OrganizationService


class ScopedOrganizationService:
    def __init__(self, actor_id: uuid.UUID, service: OrganizationService) -> None:
        self.actor_id = actor_id
        self.service = service
        self.scope_service = OrganizationScopeService()
        self.repo = OrganizationRepository()
        self.members_repo = UserOrganizationRepository()

    async def get_organization(self, org_id: uuid.UUID) -> dict[str, Any] | None:
        scope = await self.scope_service.resolve(self.actor_id)
        org = await self.service.get_organization(org_id)
        scope.require(org)
        return scope.present(org)

    async def get_organization_tree(self, root_id=None, max_depth=None) -> dict[str, Any]:
        scope = await self.scope_service.resolve(self.actor_id)
        if scope.global_access:
            return await self.service.get_organization_tree(root_id, max_depth)
        if root_id is not None:
            scope.require(await self.service.get_organization(root_id))
            return scope.present(await self.service.get_organization_tree(root_id, max_depth))
        roots = [scope.present(await self.service.get_organization_tree(root, max_depth)) for root in scope.root_ids]
        return {"roots": roots}

    async def list_organizations(self, skip=0, limit=100, is_active=None, parent_id=None):
        scope = await self.scope_service.resolve(self.actor_id)
        if scope.global_access:
            return await self.service.list_organizations(skip, limit, is_active, parent_id)
        if parent_id is not None:
            scope.require(await self.service.get_organization(parent_id))
        orgs = await self.repo.get_scoped_organizations(scope.root_ids)
        filtered = [
            scope.present(org)
            for org in orgs
            if (is_active is None or org["is_active"] == is_active)
            and (parent_id is None or org["parent_id"] == parent_id)
        ]
        return filtered[skip : skip + limit], len(filtered)

    async def search_organizations(self, query: str, max_results=20):
        scope = await self.scope_service.resolve(self.actor_id)
        if scope.global_access:
            return await self.service.search_organizations(query, max_results)
        terms = query.casefold().split()
        if not terms:
            return []
        orgs = await self.repo.get_scoped_organizations(scope.root_ids)
        matched = [
            org
            for org in orgs
            if all(
                any(term in str(org.get(field) or "").casefold() for field in ("name", "code", "description"))
                for term in terms
            )
        ]
        matched.sort(key=lambda org: org["name"])
        return [scope.present(org) for org in matched[:max_results]]

    async def get_organization_children(self, parent_id, direct_only=True):
        scope = await self.scope_service.resolve(self.actor_id)
        scope.require(await self.service.get_organization(parent_id))
        return [scope.present(org) for org in await self.service.get_organization_children(parent_id, direct_only)]

    async def get_organization_ancestors(self, org_id):
        scope = await self.scope_service.resolve(self.actor_id)
        scope.require(await self.service.get_organization(org_id))
        return [
            scope.present(org) for org in await self.service.get_organization_ancestors(org_id) if scope.contains(org)
        ]

    async def get_organization_stats(self):
        scope = await self.scope_service.resolve(self.actor_id)
        if scope.global_access:
            return await self.service.get_organization_stats()
        orgs = await self.repo.get_scoped_organizations(scope.root_ids)
        ids = {org["id"] for org in orgs}
        members = await self.members_repo.get_all_active_organization_users()
        depths: dict[int, int] = {}
        for org in orgs:
            level = scope.present(org)["level"]
            depths[level] = depths.get(level, 0) + 1
        return {
            "total_organizations": len(orgs),
            "total_users": len({member["user_id"] for member in members if member["organization_id"] in ids}),
            "total_permissions": await self.repo.count_scoped_permissions(list(ids)),
            "organizations_by_depth": depths,
        }

    async def create_organization(self, **values):
        scope = await self.scope_service.resolve(self.actor_id)
        parent_id = values.get("parent_id")
        if parent_id is None:
            if not scope.global_access:
                raise ForbiddenError(
                    message_key="errors.user_service.scoped_organization.only_a_global_administrator_can_create_a_root"
                )
        else:
            scope.require(await self.service.get_organization(parent_id))
        return scope.present(await self.service.create_organization(**values))

    async def update_organization(self, org_id, **updates):
        scope = await self.scope_service.resolve(self.actor_id)
        scope.require(await self.service.get_organization(org_id))
        if updates.get("is_active") is False:
            scope.require_mutable_root(org_id)
        return scope.present(await self.service.update_organization(org_id, **updates))

    async def delete_organization(self, org_id, cascade=False):
        scope = await self.scope_service.resolve(self.actor_id)
        scope.require(await self.service.get_organization(org_id))
        scope.require_mutable_root(org_id)
        return await self.service.delete_organization(org_id, cascade=cascade)

    async def move_organization(self, org_id, new_parent_id):
        scope = await self.scope_service.resolve(self.actor_id)
        scope.require(await self.service.get_organization(org_id))
        scope.require_mutable_root(org_id)
        if new_parent_id is None:
            scope.require_mutable_root(None)
        else:
            scope.require(await self.service.get_organization(new_parent_id))
        return scope.present(await self.service.move_organization(org_id, new_parent_id))

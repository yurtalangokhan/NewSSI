"""Actor scope for organization reads and mutations."""

from dataclasses import dataclass
from typing import Any
import uuid

from error_contract.identity import ForbiddenError

from src.repository import OrganizationRepository
from src.service.permission_resolver_service import get_permission_resolver_service


@dataclass(frozen=True)
class OrganizationScope:
    global_access: bool
    roots: list[dict[str, Any]]

    @property
    def root_ids(self) -> list[uuid.UUID]:
        return [uuid.UUID(str(root["id"])) for root in self.roots]

    def contains(self, organization: dict[str, Any]) -> bool:
        return self.global_access or any(
            str(organization["id"]) == str(root["id"]) or f"/{root['id']}/" in (organization.get("path") or "")
            for root in self.roots
        )

    def require(self, organization: dict[str, Any] | None) -> None:
        if organization is None or not self.contains(organization):
            raise ForbiddenError(
                message_key="errors.user_service.organization_scope.actor_cannot_access_the_selected_organization"
            )

    def require_mutable_root(self, organization_id: uuid.UUID | None) -> None:
        if not self.global_access and (organization_id is None or organization_id in self.root_ids):
            raise ForbiddenError(
                message_key="errors.user_service.organization_scope.an_assigned_scope_root_cannot_be_moved_or_deleted"
            )

    def present(self, organization: dict[str, Any]) -> dict[str, Any]:
        if self.global_access:
            return organization
        self.require(organization)
        result = dict(organization)
        for root in self.roots:
            if str(root["id"]) == str(result["id"]) or f"/{root['id']}/" in (result.get("path") or ""):
                prefix = root.get("path") or "/"
                result["path"] = "/" + (result.get("path") or "/")[len(prefix) :]
                result["level"] = result.get("level", 0) - root.get("level", 0)
                if str(root["id"]) == str(result["id"]):
                    result["parent_id"] = None
                    result["is_scope_root"] = True
                break
        if "children" in result:
            result["children"] = [self.present(child) for child in result["children"]]
        return result


class OrganizationScopeService:
    def __init__(self) -> None:
        self.repo = OrganizationRepository()
        self.resolver = get_permission_resolver_service()

    async def resolve(self, actor_id: uuid.UUID) -> OrganizationScope:
        permissions, is_admin = await self.resolver.resolve_effective_access(actor_id)
        if is_admin or "*" in permissions:
            return OrganizationScope(True, [])
        if not any(permission.startswith("org:") for permission in permissions):
            return OrganizationScope(False, [])
        assigned = await self.repo.get_manager_roots(actor_id)
        roots = [
            root
            for root in assigned
            if not any(
                other["id"] != root["id"] and f"/{other['id']}/" in (root.get("path") or "") for other in assigned
            )
        ]
        return OrganizationScope(False, roots)

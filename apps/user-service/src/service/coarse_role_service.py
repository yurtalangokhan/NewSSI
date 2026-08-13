import logging
from typing import Any

from i18n import t

from src.repository import PermissionRepository, RoleRepository

logger = logging.getLogger(__name__)


class RoleService:
    def __init__(self):
        self.repo = RoleRepository()
        self.permission_repo = PermissionRepository()

    # ----------------------------------------------------------------
    # CRUD
    # ----------------------------------------------------------------

    async def list_roles(self, service_client: str | None = None) -> list[dict[str, Any]]:
        roles = await self.repo.get_all(service_client=service_client)
        return [
            {
                "name": r.name,
                "description": r.description,
                "service_client": r.service_client,
                "permissions": r.permissions,
            }
            for r in roles
        ]

    async def get_role(self, name: str) -> dict[str, Any] | None:
        role = await self.repo.get_by_name(name)
        if not role:
            return None
        return {
            "name": role.name,
            "description": role.description,
            "service_client": role.service_client,
            "permissions": role.permissions,
        }

    async def create_role(
        self,
        name: str,
        service_client: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        if await self.repo.exists(name):
            raise ValueError(t("role.already_exists", name=name))
        await self._validate_permissions_for_service(permissions or [], service_client)
        role = await self.repo.create(
            name=name,
            service_client=service_client,
            description=description,
            permissions=permissions or [],
        )
        return {
            "name": role.name,
            "description": role.description,
            "service_client": role.service_client,
            "permissions": role.permissions,
        }

    async def update_role(
        self,
        name: str,
        description: str | None = None,
        service_client: str | None = None,
    ) -> dict[str, Any] | None:
        updates: dict[str, Any] = {}
        if description is not None:
            updates["description"] = description
        if service_client is not None:
            updates["service_client"] = service_client
        role = await self.repo.update(name, **updates)
        if not role:
            return None
        return {
            "name": role.name,
            "description": role.description,
            "service_client": role.service_client,
            "permissions": role.permissions,
        }

    async def delete_role(self, name: str) -> bool:
        role = await self.repo.get_by_name(name)
        if not role:
            return False
        return await self.repo.delete(name)

    # ----------------------------------------------------------------
    # Permissions management
    # ----------------------------------------------------------------

    async def get_role_permissions(self, name: str) -> dict[str, Any] | None:
        role = await self.repo.get_by_name(name)
        if not role:
            return None
        return {
            "name": role.name,
            "permissions": role.permissions,
        }

    async def set_role_permissions(
        self, name: str, permissions: list[str]
    ) -> dict[str, Any] | None:
        existing_role = await self.repo.get_by_name(name)
        if not existing_role:
            return None
        await self._validate_permissions_for_service(permissions, existing_role.service_client)
        role = await self.repo.update(name, permissions=permissions)
        if not role:
            return None
        return {
            "name": role.name,
            "permissions": role.permissions,
        }

    # ----------------------------------------------------------------
    # Aggregation helpers
    # ----------------------------------------------------------------

    async def get_aggregated_permissions(self, role_names: list[str]) -> list[str]:
        """Aggregate all permissions from a list of role names."""
        roles = await self.repo.get_by_names(role_names)
        seen: set[str] = set()
        for r in roles:
            for p in r.permissions or []:
                seen.add(p)
        return sorted(seen)

    async def list_service_clients(self) -> list[str]:
        return await self.repo.list_service_clients()

    async def _validate_permissions_for_service(
        self, permissions: list[str], service_client: str
    ) -> None:
        all_perms = await self.permission_repo.get_all()
        permission_by_name = {p.name: p for p in all_perms}
        invalid = [
            permission
            for permission in permissions
            if permission not in permission_by_name and permission != "*"
        ]
        if invalid:
            raise ValueError(t("permission.invalid_permissions", permissions=invalid))

        # service_client controls where the compact Keycloak client role lives.
        # Authorization scope comes from the permission catalog, so feature
        # bundles can group product capabilities that cross backend services.


_role_service_instance: RoleService | None = None


def get_role_service() -> RoleService:
    global _role_service_instance
    if _role_service_instance is None:
        _role_service_instance = RoleService()
    return _role_service_instance

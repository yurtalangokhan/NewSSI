import logging
from typing import Any

from src.repository import PermissionRepository, RoleRepository

from .keycloak_service import get_keycloak_service

logger = logging.getLogger(__name__)


class RoleService:
    def __init__(self):
        self.role_repo = RoleRepository()
        self.permission_repo = PermissionRepository()
        self.keycloak = get_keycloak_service()

    async def list_roles(self) -> list[dict[str, Any]]:
        roles = await self.role_repo.get_all()
        return [
            {
                "name": r.name,
                "description": r.description,
                "permissions": r.permissions,
                "is_builtin": r.is_builtin,
                "is_admin": r.is_admin,
            }
            for r in roles
        ]

    async def get_role(self, name: str) -> dict[str, Any] | None:
        role = await self.role_repo.get_by_name(name)
        if not role:
            return None
        return {
            "name": role.name,
            "description": role.description,
            "permissions": role.permissions,
            "is_builtin": role.is_builtin,
            "is_admin": role.is_admin,
        }

    async def create_role(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        is_builtin: bool = False,
    ) -> dict[str, Any]:
        if await self.role_repo.exists(name):
            raise ValueError(f"Role '{name}' already exists")
        role = await self.role_repo.create(
            name=name,
            description=description,
            permissions=permissions or [],
            is_builtin=is_builtin,
        )
        return {
            "name": role.name,
            "description": role.description,
            "permissions": role.permissions,
            "is_builtin": role.is_builtin,
            "is_admin": role.is_admin,
        }

    async def update_role(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, Any] | None:
        updates: dict[str, Any] = {}
        if description is not None:
            updates["description"] = description
        if permissions is not None:
            updates["permissions"] = permissions
        role = await self.role_repo.update(name, **updates)
        if not role:
            return None
        return {
            "name": role.name,
            "description": role.description,
            "permissions": role.permissions,
            "is_builtin": role.is_builtin,
            "is_admin": role.is_admin,
        }

    async def delete_role(self, name: str) -> bool:
        role = await self.role_repo.get_by_name(name)
        if role and role.is_builtin:
            raise ValueError(f"Cannot delete built-in role '{name}'")
        return await self.role_repo.delete(name)

    async def get_role_permissions(self, name: str) -> dict[str, Any] | None:
        role = await self.role_repo.get_by_name(name)
        if not role:
            return None
        return {
            "name": role.name,
            "permissions": role.permissions,
        }

    async def set_role_permissions(
        self, name: str, permissions: list[str]
    ) -> dict[str, Any] | None:
        all_perms = await self.permission_repo.get_all()
        valid_names = {p.name for p in all_perms}
        invalid = [p for p in permissions if p not in valid_names and p != "*"]
        if invalid:
            raise ValueError(f"Invalid permissions: {invalid}")

        role = await self.role_repo.update(name, permissions=permissions)
        if not role:
            return None
        return {
            "name": role.name,
            "permissions": role.permissions,
        }

    async def sync_to_keycloak(self) -> dict[str, Any]:
        if not self.keycloak.is_enabled():
            return {"status": "skipped", "reason": "Keycloak not enabled"}

        stats: dict[str, Any] = {
            "permission_roles_created": 0,
            "permission_roles_existing": 0,
            "composite_roles_created": 0,
            "composite_roles_updated": 0,
            "errors": [],
        }

        permissions = await self.permission_repo.get_all()
        permission_map = {p.name: p for p in permissions}

        for perm in permissions:
            try:
                existing = await self.keycloak.get_realm_role(perm.name)
                if not existing:
                    await self.keycloak.create_realm_role(perm.name, perm.label)
                    stats["permission_roles_created"] += 1
                else:
                    stats["permission_roles_existing"] += 1
            except Exception as e:
                stats["errors"].append(f"Failed to sync permission '{perm.name}': {e}")

        roles = await self.role_repo.get_all()
        for role in roles:
            try:
                kc_role = await self.keycloak.get_realm_role(role.name)
                if not kc_role:
                    await self.keycloak.create_realm_role(
                        role.name, role.description or f"{role.name} composite role"
                    )
                    stats["composite_roles_created"] += 1

                child_roles = []
                if role.permissions == ["*"]:
                    child_roles = [{"name": p.name} for p in permissions]
                else:
                    child_roles = [{"name": p} for p in role.permissions if p in permission_map]

                if child_roles:
                    await self.keycloak.set_role_composites(role.name, child_roles)
                    stats["composite_roles_updated"] += 1
            except Exception as e:
                stats["errors"].append(f"Failed to sync composite role '{role.name}': {e}")

        return stats


_role_service_instance: RoleService | None = None


def get_role_service() -> RoleService:
    global _role_service_instance
    if _role_service_instance is None:
        _role_service_instance = RoleService()
    return _role_service_instance

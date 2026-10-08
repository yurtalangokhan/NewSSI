from collections.abc import Iterable
from typing import Any

from error_contract import BadRequestError

from src.core.exceptions import ConflictError
from src.repository import PermissionRepository, RoleRepository
from src.repository.keycloak_role_client import CoarseRoleRecord, invalidate_role_access


def _to_dict(role: CoarseRoleRecord) -> dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "service_client": role.service_client,
        "permissions": list(role.permissions),
        "is_builtin": role.is_builtin,
    }


def _permissions_dict(role: CoarseRoleRecord) -> dict[str, Any]:
    return {"id": role.id, "name": role.name, "permissions": list(role.permissions)}


class RoleService:
    """Feature bundles (Keycloak client roles), addressed by their Keycloak role ID."""

    def __init__(self):
        self.repo = RoleRepository()
        self.permission_repo = PermissionRepository()

    async def _validate_permissions(self, permissions: Iterable[str]) -> None:
        valid = {p.name for p in await self.permission_repo.get_all()}
        invalid = [p for p in permissions if p not in valid and p != "*"]
        if invalid:
            raise BadRequestError(
                message_key="errors.user_service.permission.invalid_permissions",
                message_params={"permissions": invalid},
            )

    # ----------------------------------------------------------------
    # CRUD
    # ----------------------------------------------------------------

    async def list_roles(self, service_client: str | None = None) -> list[dict[str, Any]]:
        return [_to_dict(r) for r in await self.repo.get_all(service_client=service_client)]

    async def get_role(self, role_id: str) -> dict[str, Any] | None:
        role = await self.repo.get_by_id(role_id)
        return _to_dict(role) if role else None

    async def create_role(
        self,
        name: str,
        service_client: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        if await self.repo.exists(name, service_client):
            raise ConflictError(message_key="errors.user_service.role.already_exists", message_params={"name": name})
        # service_client decides where the Keycloak client role lives; authorization
        # scope comes from the permission catalog, so bundles may cross services.
        await self._validate_permissions(permissions or [])
        role = await self.repo.create(
            name=name,
            service_client=service_client,
            description=description,
            permissions=permissions or [],
        )
        return _to_dict(role)

    async def update_role(self, role_id: str, description: str | None = None) -> dict[str, Any] | None:
        role = await self.repo.update(role_id, description=description)
        invalidate_role_access()
        return _to_dict(role) if role else None

    async def delete_role(self, role_id: str) -> bool:
        role = await self.repo.get_by_id(role_id)
        if role and role.is_builtin:
            raise ValueError(t("role.cannot_delete_builtin", name=role.name))
        deleted = await self.repo.delete(role_id)
        invalidate_role_access()
        return deleted

    # ----------------------------------------------------------------
    # Permissions management
    # ----------------------------------------------------------------

    async def get_role_permissions(self, role_id: str) -> dict[str, Any] | None:
        role = await self.repo.get_by_id(role_id)
        return _permissions_dict(role) if role else None

    async def set_role_permissions(self, role_id: str, permissions: list[str]) -> dict[str, Any] | None:
        await self._validate_permissions(permissions)
        role = await self.repo.update(role_id, permissions=permissions)
        invalidate_role_access()
        return _permissions_dict(role) if role else None

    # ----------------------------------------------------------------
    # Aggregation helpers
    # ----------------------------------------------------------------

    async def get_aggregated_permissions(self, role_ids: Iterable[str]) -> list[str]:
        """Union of the expanded Keycloak grants of the given feature-role IDs."""
        permissions_by_role = await self.repo.get_permissions_by_ids(role_ids)
        return sorted({p for permissions in permissions_by_role.values() for p in permissions})

    async def list_service_clients(self) -> list[str]:
        return await self.repo.list_service_clients()


_role_service_instance: RoleService | None = None


def get_role_service() -> RoleService:
    global _role_service_instance
    if _role_service_instance is None:
        _role_service_instance = RoleService()
    return _role_service_instance

from typing import Any

from src.repository import PermissionRepository


class PermissionService:
    def __init__(self, repo: PermissionRepository | None = None):
        self.repo = repo or PermissionRepository()

    async def list_permissions(self, service: str | None = None) -> list[dict[str, Any]]:
        permissions = await self.repo.get_all(service=service)
        return [self._permission_to_dict(permission) for permission in permissions]

    async def get_permission(self, name: str) -> dict[str, Any] | None:
        permission = await self.repo.get_by_name(name)
        if not permission:
            return None
        return self._permission_to_dict(permission)

    async def list_entities(self) -> list[str]:
        return await self.repo.list_entities()

    async def list_services(self) -> dict[str, int]:
        return await self.repo.count_by_service()

    def _permission_to_dict(self, permission) -> dict[str, Any]:
        return {
            "name": permission.name,
            "label": permission.label,
            "description": permission.description,
            "entity": permission.entity,
            "service": permission.service,
            "action": permission.action,
            "is_system": permission.is_system,
        }


_permission_service_instance: PermissionService | None = None


def get_permission_service() -> PermissionService:
    global _permission_service_instance
    if _permission_service_instance is None:
        _permission_service_instance = PermissionService()
    return _permission_service_instance

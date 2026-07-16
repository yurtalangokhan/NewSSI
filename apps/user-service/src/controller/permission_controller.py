from typing import Any

from src.repository import PermissionRepository
from src.service.permission_sync_service import get_permission_sync_service

from .base import BaseController


class PermissionController(BaseController):
    def __init__(self):
        self.repo = PermissionRepository()

    async def list_permissions(self, service: str | None = None) -> dict[str, Any]:
        permissions = await self.repo.get_all(service=service)
        return {
            "permissions": [
                {
                    "name": p.name,
                    "label": p.label,
                    "description": p.description,
                    "entity": p.entity,
                    "service": p.service,
                    "action": p.action,
                    "is_system": p.is_system,
                }
                for p in permissions
            ]
        }

    async def get_permission(self, name: str) -> dict[str, Any]:
        perm = await self.repo.get_by_name(name)
        if not perm:
            self._raise_not_found(f"Permission '{name}' not found")
        return {
            "name": perm.name,
            "label": perm.label,
            "description": perm.description,
            "entity": perm.entity,
            "service": perm.service,
            "action": perm.action,
            "is_system": perm.is_system,
        }

    async def list_entities(self) -> dict[str, Any]:
        entities = await self.repo.list_entities()
        return {"entities": entities}

    async def list_services(self) -> dict[str, Any]:
        counts = await self.repo.count_by_service()
        return {"services": counts}

    async def sync_permissions(self) -> dict[str, Any]:
        return await get_permission_sync_service().sync_permissions()


_permission_controller_instance: PermissionController | None = None


def get_permission_controller() -> PermissionController:
    global _permission_controller_instance
    if _permission_controller_instance is None:
        _permission_controller_instance = PermissionController()
    return _permission_controller_instance

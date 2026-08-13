from typing import Any

from src.service import get_permission_service
from src.service.permission_sync_service import get_permission_sync_service

from .base import BaseController


class PermissionController(BaseController):
    def __init__(self):
        self.service = get_permission_service()

    async def list_permissions(self, service: str | None = None) -> dict[str, Any]:
        permissions = await self.service.list_permissions(service=service)
        return {"permissions": permissions}

    async def get_permission(self, name: str) -> dict[str, Any]:
        permission = await self.service.get_permission(name)
        if not permission:
            self._raise_not_found("permission.not_found", name=name)
        return permission

    async def list_entities(self) -> dict[str, Any]:
        entities = await self.service.list_entities()
        return {"entities": entities}

    async def list_services(self) -> dict[str, Any]:
        counts = await self.service.list_services()
        return {"services": counts}

    async def sync_permissions(self) -> dict[str, Any]:
        return await get_permission_sync_service().sync_permissions()


_permission_controller_instance: PermissionController | None = None


def get_permission_controller() -> PermissionController:
    global _permission_controller_instance
    if _permission_controller_instance is None:
        _permission_controller_instance = PermissionController()
    return _permission_controller_instance

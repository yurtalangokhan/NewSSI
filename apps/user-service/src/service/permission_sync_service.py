"""Report permissions discovered from Keycloak feature scopes and role grants."""

from collections import Counter
from typing import Any

from src.repository import PermissionRepository
from src.schema.permissions import PermissionSource, PermissionSyncResult


class PermissionSyncService:
    def __init__(self, repo: PermissionRepository | None = None):
        self.repo = repo or PermissionRepository()

    async def sync_permissions(self) -> dict[str, Any]:
        permissions = await self.repo.get_all()
        counts = Counter(permission.service for permission in permissions)
        sources = [
            PermissionSource(
                service=service,
                path="Keycloak feature scopes and client role attributes",
                loaded=True,
                count=count,
            )
            for service, count in sorted(counts.items())
        ]
        return PermissionSyncResult(
            synced_count=len(permissions),
            sources=sources,
        ).model_dump()


_permission_sync_service_instance: PermissionSyncService | None = None


def get_permission_sync_service() -> PermissionSyncService:
    global _permission_sync_service_instance
    if _permission_sync_service_instance is None:
        _permission_sync_service_instance = PermissionSyncService()
    return _permission_sync_service_instance

"""Synchronize permission catalog snapshots from service-owned manifests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from src.core.env import get_env
from src.core.permissions import list_service_permissions
from src.repository import PermissionRepository
from src.schema.permissions import (
    PermissionDefinition,
    PermissionSource,
    PermissionSyncResult,
)


class PermissionSyncService:
    def __init__(self, repo: PermissionRepository | None = None):
        self.repo = repo or PermissionRepository()

    async def sync_permissions(self) -> dict[str, Any]:
        permissions, sources = self._collect_permissions()
        synced_count = await self.repo.upsert_many(
            [permission.model_dump() for permission in permissions]
        )
        return PermissionSyncResult(
            synced_count=synced_count,
            sources=sources,
        ).model_dump()

    def collect_manifest_permissions(self) -> list[dict[str, Any]]:
        permissions, _sources = self._collect_permissions()
        return [permission.model_dump() for permission in permissions]

    def _collect_permissions(self) -> tuple[list[PermissionDefinition], list[PermissionSource]]:
        collected: dict[str, PermissionDefinition] = {}
        sources: list[PermissionSource] = []
        local_permissions = list_service_permissions()

        self._add_permissions(
            collected=collected,
            permissions=local_permissions,
            source=PermissionSource(
                service="user-service", path="src/core/permissions/manifest.py", loaded=True
            ),
        )
        sources.append(
            PermissionSource(
                service="user-service",
                path="src/core/permissions/manifest.py",
                loaded=True,
                count=len(local_permissions),
            )
        )

        for service, path in self._external_manifest_paths().items():
            source = self._load_external_manifest(service, path, collected)
            sources.append(source)

        return sorted(
            collected.values(), key=lambda item: (item.service, item.entity, item.name)
        ), sources

    def _add_permissions(
        self,
        *,
        collected: dict[str, PermissionDefinition],
        permissions: list[dict[str, Any]],
        source: PermissionSource,
    ) -> None:
        for raw_permission in permissions:
            permission = PermissionDefinition.model_validate(raw_permission)
            existing = collected.get(permission.name)
            if existing and existing.service != permission.service:
                raise ValueError(
                    f"Permission '{permission.name}' is defined by both "
                    f"'{existing.service}' and '{permission.service}'"
                )
            collected[permission.name] = permission
        source.count = len(permissions)

    def _external_manifest_paths(self) -> dict[str, Path]:
        repo_root = self._repo_root()
        return {
            "agent-service": repo_root / "apps/agent-service/src/models/permissions.py",
            "rag-service": repo_root / "apps/rag-service/langconnect/models/permissions.py",
            "tools-service": repo_root / "apps/tools-service/src/models/permissions.py",
        }

    def _repo_root(self) -> Path:
        configured_root = get_env().PERMISSION_MANIFEST_ROOT
        if configured_root:
            return Path(configured_root)

        service_file = Path(__file__).resolve()
        for parent in service_file.parents:
            if (parent / "apps/user-service").exists():
                return parent

        return Path.cwd()

    def _load_external_manifest(
        self,
        service: str,
        path: Path,
        collected: dict[str, PermissionDefinition],
    ) -> PermissionSource:
        source = PermissionSource(service=service, path=str(path), loaded=False)
        if not path.exists():
            source.error = "manifest file not found"
            return source

        try:
            module = self._load_module(service, path)
            permissions = module.list_service_permissions()
            self._add_permissions(
                collected=collected,
                permissions=permissions,
                source=source,
            )
            source.loaded = True
            return source
        except Exception as exc:
            source.error = str(exc)
            return source

    def _load_module(self, service: str, path: Path) -> ModuleType:
        module_name = f"permission_manifest_{service.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Unable to load permission manifest at {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


_permission_sync_service_instance: PermissionSyncService | None = None


def get_permission_sync_service() -> PermissionSyncService:
    global _permission_sync_service_instance
    if _permission_sync_service_instance is None:
        _permission_sync_service_instance = PermissionSyncService()
    return _permission_sync_service_instance

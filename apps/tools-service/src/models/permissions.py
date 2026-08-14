"""Permission catalog owned by tools-service."""

from __future__ import annotations

from typing import TypedDict


class PermissionDefinition(TypedDict, total=False):
    name: str
    label: str
    description: str | None
    entity: str
    service: str
    action: str
    is_system: bool


SERVICE_NAME = "tools-service"


def _permission(entity: str, action: str, label: str) -> PermissionDefinition:
    return {
        "name": f"{entity}:{action}",
        "label": label,
        "description": None,
        "entity": entity,
        "service": SERVICE_NAME,
        "action": action,
        "is_system": False,
    }


SERVICE_PERMISSIONS: list[PermissionDefinition] = [
    _permission("tool", "execute", "Execute Tools"),
]


def list_service_permissions() -> list[PermissionDefinition]:
    """Return the permission catalog owned by tools-service."""
    return list(SERVICE_PERMISSIONS)

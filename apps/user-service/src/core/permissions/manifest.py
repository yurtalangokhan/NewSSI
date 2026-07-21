from typing import TypedDict


class PermissionManifestItem(TypedDict, total=False):
    name: str
    label: str
    description: str | None
    entity: str
    service: str
    action: str
    is_system: bool


SERVICE_NAME = "user-service"


def _permission(
    entity: str,
    action: str,
    label: str,
    *,
    service: str = SERVICE_NAME,
    is_system: bool = False,
) -> PermissionManifestItem:
    return {
        "name": f"{entity}:{action}",
        "label": label,
        "description": None,
        "entity": entity,
        "service": service,
        "action": action,
        "is_system": is_system,
    }


SERVICE_PERMISSIONS: list[PermissionManifestItem] = [
    _permission("api_key", "create", "Create API Keys"),
    _permission("api_key", "delete", "Delete API Keys"),
    _permission("api_key", "read", "Read API Keys"),
    _permission("api_key", "update", "Update API Keys"),
    _permission("audit_log", "export", "Export Audit Logs"),
    _permission("audit_log", "list", "List Audit Logs"),
    _permission("audit_log", "manage", "Manage Audit Logs", is_system=True),
    _permission("audit_log", "read", "Read Audit Logs"),
    _permission("group", "create", "Create Groups"),
    _permission("group", "delete", "Delete Groups"),
    _permission("group", "list", "List Groups"),
    _permission("group", "manage", "Manage Groups"),
    _permission("group", "read", "Read Groups"),
    _permission("group", "update", "Update Groups"),
    _permission("memory", "create", "Create Memories"),
    _permission("memory", "delete", "Delete Memories"),
    _permission("memory", "read", "Read Memories"),
    _permission("memory", "update", "Update Memories"),
    _permission("permission", "create", "Create Permissions", is_system=True),
    _permission("permission", "delete", "Delete Permissions", is_system=True),
    _permission("permission", "list", "List Permissions"),
    _permission("permission", "manage", "Manage Permissions", is_system=True),
    _permission("permission", "read", "Read Permissions"),
    _permission("permission", "update", "Update Permissions", is_system=True),
    _permission("role", "create", "Create Roles"),
    _permission("role", "delete", "Delete Roles"),
    _permission("role", "list", "List Roles"),
    _permission("role", "manage", "Manage Roles", is_system=True),
    _permission("role", "read", "Read Roles"),
    _permission("role", "update", "Update Roles"),
    _permission("settings", "read", "Read Settings"),
    _permission("settings", "update", "Update Settings"),
    _permission("user", "create", "Create Users"),
    _permission("user", "delete", "Delete Users"),
    _permission("user", "list", "List Users"),
    _permission("user", "manage", "Manage Users"),
    _permission("user", "read", "Read Users"),
    _permission("user", "update", "Update Users"),
    _permission("monitor", "alert", "Manage Alerts", service="system"),
    _permission("monitor", "read", "Read System Monitoring", service="system"),
    _permission(
        "system.settings",
        "read",
        "Read System Settings",
        service="system",
        is_system=True,
    ),
    _permission(
        "system.settings",
        "update",
        "Update System Settings",
        service="system",
        is_system=True,
    ),
]


def list_service_permissions() -> list[PermissionManifestItem]:
    """Return the permission catalog owned by user-service."""
    return list(SERVICE_PERMISSIONS)

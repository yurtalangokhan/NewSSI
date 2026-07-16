"""Permission catalog owned by rag-service."""

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


SERVICE_NAME = "rag-service"


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
    _permission("chunk", "read", "Read Document Chunks"),
    _permission("chunk", "search", "Search Document Chunks"),
    _permission("collection", "create", "Create Collections"),
    _permission("collection", "delete", "Delete Collections"),
    _permission("collection", "list", "List Collections"),
    _permission("collection", "read", "Read Collections"),
    _permission("collection", "update", "Update Collections"),
    _permission("document", "create", "Upload Documents"),
    _permission("document", "delete", "Delete Documents"),
    _permission("document", "read", "Read Documents"),
    _permission("document", "search", "Search Documents"),
    _permission("document", "update", "Update Documents"),
    _permission("embedding", "read", "View Embeddings"),
    _permission("graph", "build", "Build Knowledge Graphs"),
    _permission("graph", "delete", "Delete Knowledge Graphs"),
    _permission("graph", "read", "Read Knowledge Graphs"),
    _permission("graph", "search", "Search Knowledge Graphs"),
]


def list_service_permissions() -> list[PermissionDefinition]:
    """Return the permission catalog owned by rag-service."""
    return list(SERVICE_PERMISSIONS)

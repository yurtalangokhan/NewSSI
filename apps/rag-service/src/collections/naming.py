"""User-facing descriptors of a collection shared by selector and search views."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.collections.schemas import CollectionDetails

_PLACEHOLDER_NAMES = frozenset({"", "unnamed", "datasource label"})
DEFAULT_SYNC_STATUS = "idle"


def _metadata(collection: CollectionDetails) -> dict[str, Any]:
    return collection.get("metadata") or {}


def collection_display_name(collection: CollectionDetails) -> str:
    """Return a friendly collection name, falling back to a stable short id."""
    metadata = _metadata(collection)
    candidate = metadata.get("friendly_name") or metadata.get("name") or collection.get("name") or ""
    normalized = str(candidate).strip()
    if normalized.lower() in _PLACEHOLDER_NAMES:
        return f"datasource-{collection['uuid'][:8]}"
    return normalized


def collection_connector_type(collection: CollectionDetails) -> str:
    """Return the connector type, or ``""`` for uploaded collections."""
    return str(_metadata(collection).get("connector_type") or "")


def collection_sync_status(collection: CollectionDetails) -> str:
    """Return the connector sync status, ``idle`` when never synced."""
    return str(_metadata(collection).get("sync_status") or DEFAULT_SYNC_STATUS)

# Copyright (c) 2026 Agentic AI Platform
"""Write-time guards for collection mutation endpoints.

Two unrelated write preconditions, both raised as HTTP errors before a
mutation proceeds: a collection mid graph-build is temporarily locked
(``ensure_collection_mutable``), and a connector-managed
collection is permanently read-only from this service's own document/graph
APIs, since only the owning connector pipeline may write to it
(``ensure_not_connector_managed_collection``).
"""

from error_contract import ConflictError, ForbiddenError

from src.collections.service import CollectionsManager
from src.graph.service import get_build_progress, is_build_stale

_ACTIVE_BUILD_STATUSES = {"pending", "extracting", "building"}


def ensure_collection_mutable(collection_id: str) -> None:
    """Raise HTTP 409 when a graph build is currently running for this collection.

    A build that stopped reporting progress (crashed process, collected
    task) is not treated as running — otherwise it would lock the
    collection until the progress record's TTL eventually evicts it.
    """
    progress = get_build_progress(collection_id)
    if progress and progress.status in _ACTIVE_BUILD_STATUSES and not is_build_stale(collection_id):
        raise ConflictError(
            code="collection.locked_graph_build_in_progress",
            message_key="errors.rag.collection.locked_graph_build_in_progress",
            details={"collection_id": collection_id},
        )


async def ensure_not_connector_managed_collection(collection_id: str) -> None:
    """Block write operations for connector-managed collections."""
    collection = await CollectionsManager("internal-service").get(collection_id)
    if not collection:
        # Let route handlers return their normal 404 behavior where applicable.
        return

    metadata = collection.get("metadata") or {}
    connector_type = metadata.get("connector_type")
    if connector_type:
        raise ForbiddenError(
            code="collection.connector_managed_readonly",
            message_key="errors.rag.collection.connector_managed_readonly",
            details={"collection_id": collection_id, "connector_type": connector_type},
        )

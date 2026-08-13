from fastapi import HTTPException, status
from i18n import t

from langconnect.services.graph_rag_service import get_build_progress

_ACTIVE_BUILD_STATUSES = {"pending", "extracting", "building"}


def ensure_collection_mutable(collection_id: str) -> None:
    """Raise HTTP 409 when a graph build is currently running for this collection."""
    progress = get_build_progress(collection_id)
    if progress and progress.status in _ACTIVE_BUILD_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=t("collection.locked_graph_build_in_progress"),
        )


async def ensure_not_connector_managed_collection(collection_id: str) -> None:
    """Block write operations for connector-managed (e.g. Airbyte) collections."""
    from langconnect.database.collections import CollectionsManager

    collection = await CollectionsManager("internal-service").get(collection_id)
    if not collection:
        # Let route handlers return their normal 404 behavior where applicable.
        return

    metadata = collection.get("metadata") or {}
    connector_type = metadata.get("connector_type")
    if connector_type:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=t("collection.connector_managed_readonly"),
        )

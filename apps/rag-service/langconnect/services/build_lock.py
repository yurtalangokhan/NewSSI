from fastapi import HTTPException, status

from langconnect.services.graph_rag_service import get_build_progress

_ACTIVE_BUILD_STATUSES = {"pending", "extracting", "building"}


def ensure_collection_mutable(collection_id: str) -> None:
    """Raise HTTP 409 when a graph build is currently running for this collection."""
    progress = get_build_progress(collection_id)
    if progress and progress.status in _ACTIVE_BUILD_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Collection is locked while Graph RAG build is in progress. "
                "Try again after the build completes."
            ),
        )

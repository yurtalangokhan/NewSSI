# Copyright (c) 2026 Agentic AI Platform
"""Document controller delegates to domain services without catching failures."""

from collections.abc import Callable
from typing import Any

from src.documents import api_service
from src.documents.schemas import (
    SearchQuery,
    SearchResult,
    UploadJobStartResponse,
    UploadProgress,
)
from src.documents.upload_limits import _AsyncReadable


async def documents_create(
    *,
    collection_id: str,
    user_id: str,
    files: list[_AsyncReadable],
    declared_content_length: str | None,
    metadatas_json: str | None,
) -> dict[str, Any]:
    """Delegate document ingestion to the domain upload service."""
    return await api_service.documents_create(
        collection_id=collection_id,
        user_id=user_id,
        files=files,
        declared_content_length=declared_content_length,
        metadatas_json=metadatas_json,
    )


async def documents_upload_job_start(
    *,
    collection_id: str,
    user_id: str,
    files: list[_AsyncReadable],
    declared_content_length: str | None,
    metadatas_json: str | None,
    schedule: Callable[..., Any],
) -> UploadJobStartResponse:
    """Delegate background upload scheduling to the domain service."""
    return await api_service.documents_upload_job_start(
        collection_id=collection_id,
        user_id=user_id,
        files=files,
        declared_content_length=declared_content_length,
        metadatas_json=metadatas_json,
        schedule=schedule,
    )


async def documents_upload_job_status(
    collection_id: str,
    user_id: str,
) -> UploadProgress | None:
    """Return the current upload progress for an accessible collection."""
    return await api_service.documents_upload_job_status(
        collection_id=collection_id,
        user_id=user_id,
    )


async def documents_list(
    collection_id: str,
    user_id: str,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """Return the requested document page for an accessible collection."""
    return await api_service.documents_list(
        collection_id=collection_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )


async def documents_list_chunks(
    collection_id: str,
    user_id: str,
    document_id: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Return a document chunk page after collection access checks."""
    return await api_service.documents_list_chunks(
        collection_id=collection_id,
        user_id=user_id,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )


async def documents_delete(
    collection_id: str,
    user_id: str,
    document_id: str,
) -> dict[str, bool]:
    """Delete the requested document after collection write checks."""
    return await api_service.documents_delete(
        collection_id=collection_id,
        user_id=user_id,
        document_id=document_id,
    )


async def documents_search(
    collection_id: str,
    user_id: str,
    search_query: SearchQuery,
) -> list[SearchResult]:
    """Search an accessible collection for matching document chunks."""
    return await api_service.documents_search(
        collection_id=collection_id,
        user_id=user_id,
        search_query=search_query,
    )

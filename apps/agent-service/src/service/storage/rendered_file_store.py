"""Persistence for a rendered document: cache, MinIO, and the ``document`` row.

Moved out of ``agents.tooling.document_tools._persist_generated_file`` so the
draft service (Task 13) can reuse the same best-effort save/delete without
depending on the tools module. Each storage tier stays best-effort exactly as
before: a MinIO or DB failure never stops the file from being usable for the
current session, it just won't survive a restart.
"""

from __future__ import annotations

import asyncio
import functools
import uuid

from core.observability.logger import get_logger
from core.types.authored_documents import StoredFileRef

logger = get_logger(__name__)


def download_url(file_id: str) -> str:
    return f"/api/chat/file/{file_id}?download=1"


class RenderedFileStore:
    async def save(
        self,
        *,
        data: bytes,
        filename: str,
        mime_type: str,
        user_id: str,
        thread_id: str | None,
    ) -> StoredFileRef:
        """Store bytes in the in-memory cache, MinIO, and the document table."""
        from service.storage import file_service

        file_id = uuid.uuid4().hex
        file_service.store_file(file_id, data, mime_type, filename, owner_id=user_id)

        object_key = ""
        try:
            from service.storage import minio_service

            # MinIO's client is synchronous; keep it off the event loop.
            object_key = await asyncio.to_thread(
                functools.partial(
                    minio_service.upload_file,
                    user_id=user_id,
                    file_id=file_id,
                    filename=filename,
                    data=data,
                    mime_type=mime_type,
                )
            )
        except Exception as exc:
            logger.warning("Could not upload generated file %s to MinIO: %s", file_id, exc)

        try:
            await file_service.persist_document_record(
                file_id=file_id,
                user_id=user_id,
                filename=filename,
                mime_type=mime_type,
                chat_file_type=file_service.mime_to_chat_file_type(mime_type),
                size_bytes=len(data),
                minio_object_key=object_key,
                thread_id=thread_id,
            )
        except Exception as exc:
            logger.warning("Could not persist generated file %s to document table: %s", file_id, exc)

        return StoredFileRef(
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
            download_url=download_url(file_id),
        )

    async def delete(self, file_id: str, user_id: str) -> None:
        """Drop the cache entry, document row, and MinIO object for a file.

        ``DocumentRepository.delete_by_file_id`` is not user-scoped, so
        ownership is verified first via ``get_by_file_id(file_id, user_id)`` —
        this must only ever delete a file the same user just saved. Every
        tier is best-effort, like ``save``.
        """
        from infrastructure.db.persistence_gateway import document_repository
        from service.storage import file_service, minio_service

        record = None
        try:
            record = await document_repository().get_by_file_id(file_id, user_id)
        except Exception as exc:
            logger.warning("Could not look up generated file %s for delete: %s", file_id, exc)

        if record is not None:
            object_key = record.get("minio_object_key")
            if object_key:
                try:
                    await asyncio.to_thread(minio_service.delete_file, object_key)
                except Exception as exc:
                    logger.warning("Could not delete MinIO object for file %s: %s", file_id, exc)

            try:
                await document_repository().delete_by_file_id(file_id)
            except Exception as exc:
                logger.warning("Could not delete document row for file %s: %s", file_id, exc)

        try:
            file_service.evict_file(file_id)
        except Exception as exc:
            logger.warning("Could not evict generated file %s from cache: %s", file_id, exc)

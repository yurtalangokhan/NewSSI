"""Image attachments of a chat thread, resolved for the caller only.

Authored documents embed them as ``![alt](attachment:<file_id>)``. Every lookup
is scoped to the requesting user: an id alone never grants access. Bytes come
from the in-process cache when it carries proof of ownership, otherwise from
the ``document`` row and MinIO (the cache is lost on restart). Images are
normalised so python-docx and reportlab can embed them (WebP, CMYK, EXIF
rotation), which also downscales oversized pixels.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any
from uuid import UUID

from core.observability.logger import get_logger
from core.types.authored_documents import AttachmentImageInfo
from service.documents.image_loading import MAX_IMAGE_BYTES
from service.storage import file_service

logger = get_logger(__name__)


class AttachmentImageStore:
    def __init__(self, repository: Any | None = None) -> None:
        self._repository = repository

    def _documents(self) -> Any:
        if self._repository is None:
            from infrastructure.db.persistence_gateway import document_repository

            self._repository = document_repository()
        return self._repository

    async def load(self, user_id: str, file_id: str) -> bytes | None:
        """Renderable image bytes, or ``None`` when unknown, foreign, not an image or too large."""
        try:
            record = await self._owned_record(user_id, file_id)
        except Exception as exc:
            logger.warning("Could not load attachment %s: %s", file_id, exc)
            return None
        if record is None:
            return None
        mime = record.mime_type.lower().split(";")[0].strip()
        if mime not in file_service.IMAGE_MIMES or len(record.data) > MAX_IMAGE_BYTES:
            return None
        encoded = base64.b64encode(record.data).decode("ascii")
        normalised, _ = file_service.normalize_image_for_llm(encoded, mime)
        try:
            data = base64.b64decode(normalised, validate=True)
        except ValueError:
            return None
        return data if _is_decodable_image(data) else None

    async def list_for_thread(self, user_id: str, thread_id: str | UUID) -> list[AttachmentImageInfo]:
        rows = await self._documents().list_by_thread(thread_id)
        return [
            AttachmentImageInfo(file_id=row["file_id"], filename=row["filename"], mime_type=row["mime_type"])
            for row in rows
            if row["user_id"] == user_id and row["chat_file_type"] == "image"
        ]

    async def _owned_record(self, user_id: str, file_id: str) -> file_service.FileRecord | None:
        record = file_service.get_file(file_id)
        if record is not None and record.owner_id == user_id:
            return record
        row = await self._documents().get_by_file_id(file_id, user_id)
        if row is None:
            return None
        if record is not None and record.owner_id is None:
            record.owner_id = user_id
            return record
        from service.storage import minio_service

        data = await asyncio.to_thread(minio_service.download_file, row["minio_object_key"])
        return file_service.store_file(file_id, data, row["mime_type"], row["filename"], owner_id=user_id)


def _is_decodable_image(data: bytes) -> bool:
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except Exception:
        return False
    return True

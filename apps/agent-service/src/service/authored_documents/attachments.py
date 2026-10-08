"""Resolve the chat-attachment images a draft embeds, for the requesting user only."""

from __future__ import annotations

from typing import Protocol

from core.exceptions.authored_documents import AttachmentReferenceError
from core.types.authored_documents import SourceFormat
from service.documents.attachment_refs import attachment_image_ids


class AttachmentImageLoader(Protocol):
    async def load(self, user_id: str, file_id: str) -> bytes | None: ...


class AttachmentResolver:
    def __init__(self, loader: AttachmentImageLoader | None = None) -> None:
        self._loader = loader

    def _images(self) -> AttachmentImageLoader:
        if self._loader is None:
            from service.storage.attachment_image_store import AttachmentImageStore

            self._loader = AttachmentImageStore()
        return self._loader

    async def resolve(
        self, user_id: str, content: str, source_format: SourceFormat, *, strict: bool
    ) -> dict[str, bytes]:
        """Bytes per ``attachment:`` file id in ``content``.

        ``strict`` (saving a draft) rejects every reference the caller cannot use,
        naming all of them so the model can fix them in one retry. Lenient
        (exporting an already saved draft) leaves those images out.
        """
        if source_format is not SourceFormat.MARKDOWN:
            return {}
        file_ids = attachment_image_ids(content)
        if not file_ids:
            return {}
        images: dict[str, bytes] = {}
        unusable: list[str] = []
        for file_id in file_ids:
            data = await self._images().load(user_id, file_id)
            if data is None:
                unusable.append(file_id)
            else:
                images[file_id] = data
        if unusable and strict:
            raise AttachmentReferenceError(tuple(unusable))
        return images

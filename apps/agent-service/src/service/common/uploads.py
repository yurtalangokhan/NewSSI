"""Transport-neutral view of an uploaded file.

Services that accept uploads need three things from them: a name, a declared
content type, and the bytes. Depending on ``fastapi.UploadFile`` for that would
tie the service layer to the web framework and force every caller — a worker, a
CLI, a test — to fabricate a Starlette object.

``UploadedFile`` is a structural protocol, so ``fastapi.UploadFile`` already
satisfies it and routes keep passing exactly what they receive. Reading stays
lazy: the service awaits ``read()`` per file, so a multi-file upload never has
to hold every payload in memory at once.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class UploadedFile(Protocol):
    """A file the caller uploaded, independent of how it arrived."""

    @property
    def filename(self) -> str | None:
        """Client-supplied name, if any. Never trusted as a path."""

    @property
    def content_type(self) -> str | None:
        """Client-declared media type, if any. Validated before it is trusted."""

    async def read(self, size: int = -1) -> bytes:
        """Return the file's bytes."""

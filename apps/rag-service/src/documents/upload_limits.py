"""Upload guards.

The previous flow read every file fully into memory with a bare
``UploadFile.read()`` and checked the 200 MB limit afterwards
(processor.py), so the limit could not protect the process --
an oversized upload was already fully buffered before ever being
rejected. read_bounded enforces the limit during the read itself,
aborting as soon as the threshold is crossed rather than after the fact.

It also streams straight to a private temp file instead of accumulating
the read in process memory: a batch of N files near the size limit used
to hold all N files' bytes simultaneously (upload -> validation ->
parsing), even though only one file is ever actually being parsed at a
time. The SHA-256 content hash used for dedup (document_upload_service.py)
is computed incrementally in the same pass, so nothing has to re-read the
file to hash it afterward.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from typing import Protocol

from error_contract import UploadTooLargeError

from src.documents.schemas import FileUploadDTO

MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_TOTAL_BYTES = 500 * 1024 * 1024
MAX_FILE_COUNT = 20
CHUNK_BYTES = 1024 * 1024

#: Every temp file this module creates uses this prefix, so a leak (a
#: process killed hard enough to skip every finally) is identifiable and
#: safely globbable for an external cleanup sweep.
_TEMP_PREFIX = "rag-upload-"


class _AsyncReadable(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int) -> bytes: ...


async def read_bounded(file: _AsyncReadable, *, max_bytes: int = MAX_FILE_BYTES) -> FileUploadDTO:
    """Stream *file* into a private temp file and return a FileUploadDTO.

    Reads in fixed-size chunks, raising UploadTooLargeError as soon as the
    cumulative size crosses max_bytes -- never buffering more than one
    chunk beyond the limit, and never holding the file's own bytes in
    memory at all. The SHA-256 content hash is computed incrementally
    across the same chunks.

    A size violation, or any other exception raised while reading (a
    disconnected client surfaces as one), deletes the partial temp file
    before re-raising: this function never leaves a half-written file
    behind for the caller to clean up.
    """
    fd, raw_path = tempfile.mkstemp(prefix=_TEMP_PREFIX, suffix=".part")
    path = Path(raw_path)
    hasher = hashlib.sha256()
    written = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await file.read(CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise UploadTooLargeError(f"{file.filename!r} exceeds the {max_bytes} byte limit")
                hasher.update(chunk)
                out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    return FileUploadDTO(
        filename=file.filename or "",
        content_type=file.content_type,
        size=written,
        path=path,
        content_hash=hasher.hexdigest(),
    )


def check_batch_size(*, file_count: int, declared_content_length: str | None) -> None:
    """Reject a batch with too many files, or one whose declared
    Content-Length already exceeds the total limit, before any file is
    read. The per-file, during-the-read limit (read_bounded) still applies
    on top of this -- a client can lie about Content-Length.
    """
    if file_count > MAX_FILE_COUNT:
        raise UploadTooLargeError(f"At most {MAX_FILE_COUNT} files are allowed per request")

    if declared_content_length is not None:
        try:
            if int(declared_content_length) > MAX_TOTAL_BYTES:
                raise UploadTooLargeError("Request body exceeds the total upload size limit")
        except ValueError:
            pass


async def read_files_within_total_limit(
    files: list[_AsyncReadable],
) -> list[FileUploadDTO]:
    """Read every file into a DTO, aborting once the running total across
    the whole batch exceeds MAX_TOTAL_BYTES -- read_bounded only caps one
    file at a time, so many just-under-the-limit files could otherwise
    still add up past it.

    Every DTO already spooled to disk is cleaned up before an error
    propagates: a batch rejected partway through (this file's own size,
    or the running total) must not leak the temp files of the files that
    were already read.
    """
    dtos: list[FileUploadDTO] = []
    total = 0
    try:
        for file in files:
            dto = await read_bounded(file, max_bytes=MAX_FILE_BYTES)
            dtos.append(dto)
            total += dto.size
            if total > MAX_TOTAL_BYTES:
                raise UploadTooLargeError("Total upload size exceeds the limit")
        return dtos
    except BaseException:
        for dto in dtos:
            dto.cleanup()
        raise

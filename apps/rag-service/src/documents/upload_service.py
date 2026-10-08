"""Document upload/embedding orchestration with pollable progress.

Mirrors the in-memory progress-tracking pattern used by
``graph/service.py`` for graph builds: a plain process-local dict keyed
by ``collection_id``, populated synchronously before a background task
starts (to avoid a race where a status poll sees stale/missing data), and
updated as the background task runs.
"""

from typing import Any

from cachetools import TTLCache
from error_contract import ApplicationError, InternalServerError, render_error_message

from src.documents.processor import process_document
from src.documents.schemas import FileUploadDTO, UploadProgress, UploadStatus
from src.documents.service import Collection
from src.shared.observability import get_logger

logger = get_logger(__name__)

UPLOAD_EMBED_BATCH_SIZE = 16

# In-memory upload progress tracking (per collection). Bounded: an unbounded
# dict here grew one entry per collection ever uploaded to, for the lifetime
# of the process.
_upload_progress: TTLCache[str, UploadProgress] = TTLCache(maxsize=1_000, ttl=3_600)
_upload_errors: TTLCache[str, ApplicationError] = TTLCache(maxsize=1_000, ttl=3_600)

ACTIVE_UPLOAD_STATUSES: frozenset[UploadStatus] = frozenset({UploadStatus.PENDING, UploadStatus.PROCESSING})


def get_upload_progress(collection_id: str) -> UploadProgress | None:
    """Get current upload progress for a collection."""
    progress = _upload_progress.get(collection_id)
    error = _upload_errors.get(collection_id)
    if progress is not None and error is not None:
        return progress.model_copy(update={"error": render_error_message(error)})
    return progress


def initialize_upload_progress(collection_id: str, *, total_files: int) -> UploadProgress:
    """Pre-register a pending upload record before the background task starts."""
    _upload_errors.pop(collection_id, None)
    progress = UploadProgress(
        collection_id=collection_id,
        status=UploadStatus.PENDING,
        total_files=total_files,
    )
    _upload_progress[collection_id] = progress
    return progress


def _batched(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def run_upload_job(
    collection_id: str,
    user_id: str,
    files: list[FileUploadDTO],
    metadatas: list[dict | None],
) -> None:
    """Process and embed uploaded files, updating progress as it goes.

    Args:
        collection_id: Target collection identifier.
        user_id: Identity of the uploading user.
        files: Framework-agnostic upload DTOs.  The API layer reads bytes
            from FastAPI ``UploadFile`` and builds these so that this
            module has no framework dependency.
        metadatas: Per-file metadata dicts (or ``None``) aligned 1-to-1
            with *files*.
    """
    progress = _upload_progress[collection_id]
    progress.status = UploadStatus.PROCESSING

    try:
        collection = Collection(collection_id=collection_id, user_id=user_id)
        (
            seen_filenames,
            seen_content_hashes,
        ) = await collection.list_upload_fingerprints()

        for file, metadata in zip(files, metadatas, strict=False):
            filename = file.filename
            progress.current_file = filename

            try:
                # Computed once, incrementally, during the bounded read
                # that spooled this file to disk (upload_limits.read_bounded)
                # -- no need to re-read it from disk just to hash it again.
                content_hash = file.content_hash

                if filename in seen_filenames or content_hash in seen_content_hashes:
                    progress.duplicate_files.append(filename)
                    progress.processed_files += 1
                    continue

                file_metadata = dict(metadata) if metadata else {}
                file_metadata["filename"] = filename
                file_metadata["content_hash"] = content_hash

                try:
                    langchain_docs = await process_document(file, metadata=file_metadata)
                except Exception as exc:
                    logger.info("Error processing file %s: %s", filename, exc)
                    progress.failed_files.append(filename)
                    progress.processed_files += 1
                    continue

                if not langchain_docs:
                    progress.processed_files += 1
                    continue

                seen_filenames.add(filename)
                seen_content_hashes.add(content_hash)
                progress.total_chunks += len(langchain_docs)

                for batch in _batched(langchain_docs, UPLOAD_EMBED_BATCH_SIZE):
                    added_ids = await collection.upsert(batch)
                    progress.added_chunk_ids.extend(added_ids)
                    progress.processed_chunks += len(batch)

                progress.processed_files += 1
            finally:
                # Freed as soon as this file is done with, rather than
                # waiting for the whole batch -- a large batch otherwise
                # keeps every earlier file's temp data on disk for the
                # duration of the whole job.
                file.cleanup()

        progress.status = UploadStatus.COMPLETED
    except Exception as exc:  # Terminal background-job boundary.
        logger.info("Upload job failed for collection %s: %s", collection_id, exc)
        progress.status = UploadStatus.FAILED
        error = exc if isinstance(exc, ApplicationError) else InternalServerError()
        _upload_errors[collection_id] = error
        progress.error = render_error_message(error)
    finally:
        progress.current_file = None
        # Safety net: an exception between files (e.g. collection.upsert)
        # skips the rest of the loop, which would otherwise leak the temp
        # files of every file after the one that failed. cleanup() is
        # idempotent, so a file the loop already cleaned up is a no-op here.
        for file in files:
            file.cleanup()

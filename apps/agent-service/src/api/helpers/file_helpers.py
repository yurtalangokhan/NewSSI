"""Pure helpers for file download and preview routes.

Extracted from ``file_route`` to keep the route file focused on endpoint
definitions and HTTP handling.
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote

from error_contract import DependencyUnavailableError
from fastapi import HTTPException
from localization import t
from minio.error import S3Error
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from core.observability.logger import get_logger
from service.storage.file_service import FileRecord, get_file, store_file

logger = get_logger(__name__)

# Presentation-side response headers for security hardening
HARDENED_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox; default-src 'none'",
}


def file_not_found_exception() -> HTTPException:
    """404 with no-store — a transient failure (e.g. MinIO down while the
    in-memory cache is cold) must never be cached by the browser, or every
    later preview attempt for that file_id will fail from disk cache without
    ever hitting the backend again, even once the file becomes available."""
    return HTTPException(
        status_code=404,
        detail=t("file.not_found"),
        headers={"Cache-Control": "no-store"},
    )


def safe_content_disposition(disposition: str, filename: str) -> str:
    """Build a Content-Disposition value that survives latin-1 encoding.

    filename is also stripped of quote/CR/LF characters first: unescaped
    they could break out of the quoted filename value or, for CR/LF,
    inject additional header lines.
    """
    cleaned_name = "".join(ch for ch in filename if ch not in '"\r\n')

    try:
        cleaned_name.encode("latin-1")
        return f'{disposition}; filename="{cleaned_name}"'
    except (UnicodeEncodeError, UnicodeDecodeError):
        encoded = quote(cleaned_name, safe="")
        return f"{disposition}; filename*=UTF-8''{encoded}"


async def resolve_file_record(file_id: str, user_id: str) -> FileRecord:
    """Return the caller's FileRecord from memory or MinIO; 404 otherwise.

    A cached record is served only when it is known to belong to the caller.
    Records cached without an owner (history rehydration stores bytes straight
    from message metadata) fall through to the document row, which is the
    authoritative answer to "whose file is this".
    """
    record = get_file(file_id)
    if record is not None and record.owner_id == user_id:
        return record

    try:
        from infrastructure.db.repositories.document_repo import DocumentRepository
        from service.storage.minio_service import download_file as minio_download

        doc = await DocumentRepository().get_by_file_id(file_id, user_id)
        if doc is None:
            raise file_not_found_exception()

        if record is not None and record.owner_id is None:
            record.owner_id = user_id
            return record

        data = await asyncio.to_thread(minio_download, doc["minio_object_key"])
        record = store_file(file_id, data, doc["mime_type"], doc["filename"], owner_id=user_id)
        return record
    except HTTPException:
        raise
    except (S3Error, Urllib3HTTPError, OSError) as exc:
        logger.error("Failed to retrieve file %s from MinIO: %s", file_id, exc)
        raise DependencyUnavailableError() from exc

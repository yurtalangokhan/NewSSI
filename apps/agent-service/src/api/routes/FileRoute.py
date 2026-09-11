"""
FileRoute — chat file retrieval endpoint.

Files are first looked up in the in-memory FileService._STORE (fast path).
If not found there (e.g. after a service restart), the record is fetched from
the ``document`` DB table and the raw bytes are downloaded from MinIO on demand,
then cached back into the in-memory store for subsequent requests.

GET  /api/chat/file/{file_id} — serve stored file bytes (XLSX served as CSV)
GET  /api/chat/file/{file_id}/text — extract and return plain text
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from i18n import t

from api.dependencies import require_user
from core.logger import get_logger
from service.FileService import (
    FileRecord,
    get_file,
    process_file_for_llm,
    store_file,
    to_csv_text,
)

logger = get_logger(__name__)

router = APIRouter(tags=["files"], dependencies=[Depends(require_user)])

# XLSX / XLS MIME types that should be served as CSV for frontend table rendering
_EXCEL_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


async def _resolve_file(file_id: str) -> FileRecord:
    """Return a FileRecord from memory or MinIO; raise 404 if not found anywhere."""
    record = get_file(file_id)
    if record is not None:
        return record

    # Not in memory — check DB then fetch bytes from MinIO
    try:
        from core.db.repositories.document_repo import DocumentRepository
        from service.MinioService import download_file as minio_download

        doc = await DocumentRepository().get_by_file_id(file_id)
        if doc is None:
            raise _not_found()

        data = minio_download(doc["minio_object_key"])
        # Warm the in-memory cache for subsequent requests this session
        record = store_file(file_id, data, doc["mime_type"], doc["filename"])
        return record
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to retrieve file %s from MinIO: %s", file_id, exc)
        raise _not_found() from exc


def _not_found() -> HTTPException:
    """404 with no-store — a transient failure (e.g. MinIO down while the
    in-memory cache is cold) must never be cached by the browser, or every
    later preview attempt for that file_id will fail from disk cache without
    ever hitting the backend again, even once the file becomes available."""
    return HTTPException(
        status_code=404,
        detail=t("file.not_found"),
        headers={"Cache-Control": "no-store"},
    )


def _safe_disposition(disposition: str, filename: str) -> str:
    """Build a Content-Disposition value that survives latin-1 encoding."""
    from urllib.parse import quote

    try:
        filename.encode("latin-1")
        return f'{disposition}; filename="{filename}"'
    except (UnicodeEncodeError, UnicodeDecodeError):
        encoded = quote(filename, safe="")
        return f"{disposition}; filename*=UTF-8''{encoded}"


@router.get("/api/chat/file/{file_id}")
async def get_chat_file(file_id: str, download: bool = False) -> Response:
    """
    Serve a previously uploaded or agent-generated file.

    Checks in-memory cache first; falls back to MinIO if the service
    restarted since the file was uploaded.

    XLSX/XLS files are converted to CSV text so that the frontend's CsvContent
    component can render them as a table without any extra parsing logic —
    unless ``?download=1`` is set, in which case the original bytes and
    filename are served with ``Content-Disposition: attachment`` so the
    browser downloads the real .xlsx file instead.
    """
    record = await _resolve_file(file_id)
    m = record.mime_type.lower().split(";")[0].strip()

    # Serve XLSX as CSV so the CsvContent component can parse it directly —
    # but not when the caller explicitly wants to download the real file.
    if not download and m in _EXCEL_MIMES:
        csv_text = to_csv_text(record)
        return Response(
            content=csv_text.encode("utf-8"),
            media_type="text/csv",
            headers={
                "Content-Disposition": _safe_disposition("inline", record.filename + ".csv"),
            },
        )

    disposition = "attachment" if download else "inline"
    return Response(
        content=record.data,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": _safe_disposition(disposition, record.filename),
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/api/chat/file/{file_id}/text")
async def get_chat_file_text(file_id: str) -> Response:
    """Extract and return plain text from a document file (docx, pdf, pptx, etc.)."""
    record = await _resolve_file(file_id)

    text = process_file_for_llm(record)
    if text is None:
        raise HTTPException(
            status_code=422,
            detail=t("file.text_extraction_unsupported"),
        )

    return Response(
        content=text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "private, max-age=3600"},
    )

"""
FileRoute — chat file retrieval endpoint.

Files are stored in the in-memory FileService._STORE when the frontend sends them
inline (as base64) inside the message payload.  This route simply serves them back
so the frontend's CsvContent / InMessageImage components can display them.

GET  /api/chat/file/{file_id} — serve stored file bytes (XLSX served as CSV)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from service.FileService import (
    get_file,
    process_file_for_llm,
    to_csv_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["files"])

# XLSX / XLS MIME types that should be served as CSV for frontend table rendering
_EXCEL_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


@router.get("/api/chat/file/{file_id}")
async def get_chat_file(file_id: str) -> Response:
    """
    Serve a previously uploaded file.

    XLSX/XLS files are converted to CSV text so that the frontend's CsvContent
    component can render them as a table without any extra parsing logic.
    """
    record = get_file(file_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="File not found or has expired (TTL: 2 hours).",
        )

    m = record.mime_type.lower().split(";")[0].strip()

    def _safe_disposition(disposition: str, filename: str) -> str:
        """Build a Content-Disposition value that survives latin-1 encoding.

        HTTP headers must be latin-1 safe.  For non-ASCII filenames we use
        the RFC 5987 extended parameter (filename*=UTF-8''<percent-encoded>)
        so browsers still show the real name.
        """
        from urllib.parse import quote
        try:
            # Fast path: pure ASCII — no encoding needed
            filename.encode("latin-1")
            return f'{disposition}; filename="{filename}"'
        except (UnicodeEncodeError, UnicodeDecodeError):
            encoded = quote(filename, safe="")
            return f"{disposition}; filename*=UTF-8''{encoded}"

    # Serve XLSX as CSV so the CsvContent component can parse it directly
    if m in _EXCEL_MIMES:
        csv_text = to_csv_text(record)
        return Response(
            content=csv_text.encode("utf-8"),
            media_type="text/csv",
            headers={
                "Content-Disposition": _safe_disposition("inline", record.filename + ".csv"),
            },
        )

    return Response(
        content=record.data,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": _safe_disposition("inline", record.filename),
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/api/chat/file/{file_id}/text")
async def get_chat_file_text(file_id: str) -> Response:
    """Extract and return plain text from a document file (docx, pdf, pptx, etc.)."""
    record = get_file(file_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="File not found or has expired (TTL: 2 hours).",
        )

    text = process_file_for_llm(record)
    if text is None:
        raise HTTPException(
            status_code=422,
            detail="Cannot extract text from this file type (images are not supported).",
        )

    return Response(
        content=text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "private, max-age=3600"},
    )

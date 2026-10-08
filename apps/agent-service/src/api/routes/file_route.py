"""
file_route — chat file retrieval endpoint.

Files are first looked up in the in-memory FileService._STORE (fast path).
If not found there (e.g. after a service restart), the record is fetched from
the ``document`` DB table and the raw bytes are downloaded from MinIO on demand,
then cached back into the in-memory store for subsequent requests.

GET  /api/chat/file/{file_id} — serve stored file bytes (XLSX served as CSV)
GET  /api/chat/file/{file_id}/text — extract and return plain text
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from localization import t

from api.dependencies import require_user
from api.helpers.file_helpers import (
    HARDENED_HEADERS,
    file_not_found_exception,
    resolve_file_record,
    safe_content_disposition,
)
from core.observability.logger import get_logger
from service.auth.auth_service import AuthenticatedUser
from service.storage.file_service import (
    EXCEL_MIMES,
    process_file_for_llm,
    to_csv_text,
)

logger = get_logger(__name__)

router = APIRouter(tags=["files"], dependencies=[Depends(require_user)])


# Backward-compatibility aliases
_EXCEL_MIMES = EXCEL_MIMES
_HARDENED_HEADERS = HARDENED_HEADERS
_not_found = file_not_found_exception
_safe_disposition = safe_content_disposition
_resolve_file = resolve_file_record


@router.get(
    "/api/chat/file/{file_id}",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                "text/csv": {"schema": {"type": "string"}},
            },
            "description": "Raw file data or CSV representation",
        }
    },
)
async def get_chat_file(
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    download: bool = False,
) -> Response:
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
    record = await _resolve_file(file_id, user.user_id)
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
                **_HARDENED_HEADERS,
            },
        )

    disposition = "attachment" if download else "inline"
    return Response(
        content=record.data,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": _safe_disposition(disposition, record.filename),
            "Cache-Control": "private, max-age=3600",
            **_HARDENED_HEADERS,
        },
    )


@router.get(
    "/api/chat/file/{file_id}/text",
    response_class=Response,
    responses={
        200: {
            "content": {"text/plain": {"schema": {"type": "string"}}},
            "description": "Extracted plain text",
        }
    },
)
async def get_chat_file_text(
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> Response:
    """Extract and return plain text from a document file (docx, pdf, pptx, etc.)."""
    record = await _resolve_file(file_id, user.user_id)

    text = process_file_for_llm(record)
    if text is None:
        raise HTTPException(
            status_code=422,
            detail=t("file.text_extraction_unsupported"),
        )

    return Response(
        content=text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "private, max-age=3600", **_HARDENED_HEADERS},
    )

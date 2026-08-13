"""Tests for the ?download=1 attachment variant of GET /api/chat/file/{file_id}."""

from __future__ import annotations

import pytest

from api.routes.FileRoute import get_chat_file
from service.FileService import store_file


@pytest.fixture(autouse=True)
def _clear_file_store():
    from service.FileService import _STORE

    _STORE.clear()
    yield
    _STORE.clear()


@pytest.mark.asyncio
async def test_default_request_serves_inline_disposition():
    record = store_file("file-1", b"hello", "text/plain", "notes.txt")

    response = await get_chat_file(record.file_id)

    assert response.headers["Content-Disposition"].startswith("inline")
    assert response.body == b"hello"


@pytest.mark.asyncio
async def test_download_request_serves_attachment_disposition_with_original_bytes():
    record = store_file("file-2", b"hello", "text/plain", "notes.txt")

    response = await get_chat_file(record.file_id, download=True)

    assert response.headers["Content-Disposition"].startswith("attachment")
    assert 'filename="notes.txt"' in response.headers["Content-Disposition"]
    assert response.body == b"hello"
    assert response.media_type == "text/plain"


@pytest.mark.asyncio
async def test_default_request_converts_xlsx_to_csv():
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.append(["a", "b"])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    record = store_file(
        "file-3",
        xlsx_bytes,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "satis.xlsx",
    )

    response = await get_chat_file(record.file_id)

    assert response.media_type == "text/csv"
    assert response.body.decode("utf-8").strip() == "a,b"


@pytest.mark.asyncio
async def test_download_request_does_not_convert_xlsx_to_csv():
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.append(["a", "b"])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    record = store_file(
        "file-4",
        xlsx_bytes,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "satis.xlsx",
    )

    response = await get_chat_file(record.file_id, download=True)

    assert response.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.body == xlsx_bytes
    assert 'filename="satis.xlsx"' in response.headers["Content-Disposition"]

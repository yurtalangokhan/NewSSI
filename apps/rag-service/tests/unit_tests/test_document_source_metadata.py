"""A processed document's ``source`` names the upload, not the server's disk.

Uploads are spooled to a private temp file before parsing, and
``Blob.from_path`` makes that path the blob's source -- which every
LangChain parser copies into ``Document.metadata["source"]``. The value
then reached the vector store, the API and the UI, so each chunk carried
a ``/tmp/rag-upload-<random>.part`` string: a server-internal path that
is meaningless to the reader, different on every upload of the same file,
and dangling the moment the temp file is deleted. The name the uploader
gave the file is the source they actually mean.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src.documents.processor import process_document
from src.documents.schemas import FileUploadDTO

if TYPE_CHECKING:
    from pathlib import Path


def _upload(tmp_path: Path, filename: str) -> FileUploadDTO:
    spooled = tmp_path / "rag-upload-abc123.part"
    spooled.write_bytes(b"Hello world. This is a test document.")
    return FileUploadDTO(
        filename=filename,
        content_type="text/plain",
        size=spooled.stat().st_size,
        path=spooled,
        content_hash="0" * 64,
    )


@pytest.mark.asyncio
async def test_the_temp_path_never_reaches_document_metadata(tmp_path: Path):
    docs = await process_document(_upload(tmp_path, "quarterly-report.txt"))

    assert docs
    for doc in docs:
        source = doc.metadata.get("source")
        assert "rag-upload-" not in str(source)
        assert str(tmp_path) not in str(source)


@pytest.mark.asyncio
async def test_the_source_is_the_uploaded_filename(tmp_path: Path):
    docs = await process_document(_upload(tmp_path, "quarterly-report.txt"))

    assert docs
    assert all(doc.metadata.get("source") == "quarterly-report.txt" for doc in docs)


@pytest.mark.asyncio
async def test_an_unnamed_upload_has_no_source_rather_than_a_path(tmp_path: Path):
    docs = await process_document(_upload(tmp_path, ""))

    assert docs
    assert all(doc.metadata.get("source") is None for doc in docs)

"""Upload guards. Spec T4.

read_bounded streams every upload straight to a private temp file instead
of accumulating it in process memory, enforcing the size limit during the
read itself (aborting as soon as the threshold is crossed, not after the
whole file was already buffered), and computes its SHA-256 content hash
incrementally in the same pass.
"""

import hashlib
import io
from pathlib import Path

import pytest
from fastapi import UploadFile

from src.documents.schemas import FileUploadDTO
from src.documents.upload_limits import (
    MAX_FILE_BYTES,
    UploadTooLargeError,
    read_bounded,
)


@pytest.mark.asyncio
async def test_small_file_is_spooled_to_a_real_temp_file():
    upload = UploadFile(filename="a.txt", file=io.BytesIO(b"hello"))

    dto = await read_bounded(upload, max_bytes=MAX_FILE_BYTES)

    assert isinstance(dto, FileUploadDTO)
    assert dto.path.is_file()
    assert dto.path.read_bytes() == b"hello"
    dto.cleanup()


@pytest.mark.asyncio
async def test_dto_fields_are_populated_from_the_upload_and_the_read():
    upload = UploadFile(
        filename="a.txt",
        file=io.BytesIO(b"hello"),
        headers={"content-type": "text/plain"},
    )

    dto = await read_bounded(upload, max_bytes=MAX_FILE_BYTES)

    assert dto.filename == "a.txt"
    assert dto.content_type == "text/plain"
    assert dto.size == 5
    dto.cleanup()


@pytest.mark.asyncio
async def test_content_hash_matches_a_direct_sha256_of_the_bytes():
    payload = b"the quick brown fox jumps over the lazy dog"
    upload = UploadFile(filename="a.txt", file=io.BytesIO(payload))

    dto = await read_bounded(upload, max_bytes=MAX_FILE_BYTES)

    assert dto.content_hash == hashlib.sha256(payload).hexdigest()
    dto.cleanup()


@pytest.mark.asyncio
async def test_missing_filename_defaults_to_empty_string():
    upload = UploadFile(filename=None, file=io.BytesIO(b"hello"))

    dto = await read_bounded(upload, max_bytes=MAX_FILE_BYTES)

    assert dto.filename == ""
    dto.cleanup()


@pytest.mark.asyncio
async def test_empty_file_is_accepted_with_zero_size_and_the_empty_hash():
    upload = UploadFile(filename="empty.txt", file=io.BytesIO(b""))

    dto = await read_bounded(upload, max_bytes=MAX_FILE_BYTES)

    assert dto.size == 0
    assert dto.path.read_bytes() == b""
    assert dto.content_hash == hashlib.sha256(b"").hexdigest()
    dto.cleanup()


@pytest.mark.asyncio
async def test_a_file_exactly_at_the_limit_is_accepted_not_rejected():
    payload = b"x" * 1000
    upload = UploadFile(filename="exact.txt", file=io.BytesIO(payload))

    dto = await read_bounded(upload, max_bytes=1000)

    assert dto.size == 1000
    dto.cleanup()


@pytest.mark.asyncio
async def test_oversized_file_is_rejected_before_being_fully_read():
    payload = io.BytesIO(b"x" * 5000)
    upload = UploadFile(filename="big.txt", file=payload)
    with pytest.raises(UploadTooLargeError, match="big.txt"):
        await read_bounded(upload, max_bytes=1000)


@pytest.mark.asyncio
async def test_rejection_does_not_keep_reading_past_the_limit(monkeypatch):
    """The guard must stop reading, not read everything and then complain."""
    read_calls = {"count": 0}
    source = io.BytesIO(b"x" * 100_000)

    class _Counting(io.BytesIO):
        def read(self, size=-1):
            read_calls["count"] += 1
            return source.read(size)

    upload = UploadFile(filename="big.txt", file=_Counting())
    with pytest.raises(UploadTooLargeError):
        await read_bounded(upload, max_bytes=1024)
    assert read_calls["count"] < 10


@pytest.mark.asyncio
async def test_rejection_does_not_leak_the_partial_temp_file():
    """A size violation must not leave a `.part` file behind on disk."""
    import tempfile

    before = set(Path(tempfile.gettempdir()).glob("rag-upload-*"))

    upload = UploadFile(filename="big.txt", file=io.BytesIO(b"x" * 5000))
    with pytest.raises(UploadTooLargeError):
        await read_bounded(upload, max_bytes=1000)

    after = set(Path(tempfile.gettempdir()).glob("rag-upload-*"))
    assert after == before


@pytest.mark.asyncio
async def test_an_unexpected_read_failure_does_not_leak_the_partial_temp_file():
    """Not just the size guard: any exception mid-read (client disconnect,
    broken pipe) must still clean up before propagating.
    """
    import tempfile

    class _BrokenStream:
        def __init__(self) -> None:
            self._served_first_chunk = False

        async def read(self, size: int) -> bytes:
            if not self._served_first_chunk:
                self._served_first_chunk = True
                return b"partial data"
            raise ConnectionError("client disconnected")

    class _FakeUploadFile:
        filename = "broken.txt"
        content_type = "text/plain"

        def __init__(self) -> None:
            self.file = _BrokenStream()

        async def read(self, size: int) -> bytes:
            return await self.file.read(size)

    before = set(Path(tempfile.gettempdir()).glob("rag-upload-*"))

    with pytest.raises(ConnectionError):
        await read_bounded(_FakeUploadFile(), max_bytes=MAX_FILE_BYTES)

    after = set(Path(tempfile.gettempdir()).glob("rag-upload-*"))
    assert after == before


@pytest.mark.asyncio
async def test_two_concurrent_reads_get_distinct_temp_files():
    upload_a = UploadFile(filename="a.txt", file=io.BytesIO(b"aaa"))
    upload_b = UploadFile(filename="b.txt", file=io.BytesIO(b"bbb"))

    dto_a, dto_b = (
        await read_bounded(upload_a, max_bytes=MAX_FILE_BYTES),
        await read_bounded(upload_b, max_bytes=MAX_FILE_BYTES),
    )

    assert dto_a.path != dto_b.path
    assert dto_a.path.read_bytes() == b"aaa"
    assert dto_b.path.read_bytes() == b"bbb"
    dto_a.cleanup()
    dto_b.cleanup()


@pytest.mark.asyncio
async def test_cleanup_is_idempotent():
    upload = UploadFile(filename="a.txt", file=io.BytesIO(b"hello"))
    dto = await read_bounded(upload, max_bytes=MAX_FILE_BYTES)

    dto.cleanup()
    dto.cleanup()  # must not raise

    assert not dto.path.exists()


@pytest.mark.asyncio
async def test_cleanup_on_an_externally_deleted_file_does_not_raise():
    upload = UploadFile(filename="a.txt", file=io.BytesIO(b"hello"))
    dto = await read_bounded(upload, max_bytes=MAX_FILE_BYTES)
    dto.path.unlink()  # simulate something else removing it first

    dto.cleanup()  # must not raise

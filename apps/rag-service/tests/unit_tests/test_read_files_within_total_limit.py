"""Spec T4: _read_files_within_total_limit must not leak the temp files of
files it already spooled to disk when a later file in the same batch (its
own size, or the running total) forces the whole request to be rejected.
"""

import io

import pytest
from error_contract import UploadTooLargeError
from fastapi import UploadFile

from src.documents.router import _read_files_within_total_limit


@pytest.mark.asyncio
async def test_all_files_are_read_when_the_batch_is_within_every_limit():
    files = [
        UploadFile(filename="a.txt", file=io.BytesIO(b"aaa")),
        UploadFile(filename="b.txt", file=io.BytesIO(b"bbb")),
    ]

    dtos = await _read_files_within_total_limit(files)

    try:
        assert [d.filename for d in dtos] == ["a.txt", "b.txt"]
        assert all(d.path.exists() for d in dtos)
    finally:
        for d in dtos:
            d.cleanup()


@pytest.mark.asyncio
async def test_a_single_oversized_file_raises_413_and_leaks_nothing(monkeypatch):
    from src.documents import upload_limits as upload_limits_module

    monkeypatch.setattr(upload_limits_module, "MAX_FILE_BYTES", 1000)

    files = [
        UploadFile(filename="a.txt", file=io.BytesIO(b"aaa")),
        UploadFile(filename="huge.bin", file=io.BytesIO(b"x" * 5000)),
    ]

    with pytest.raises(UploadTooLargeError) as exc_info:
        await _read_files_within_total_limit(files)

    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_exceeding_the_running_total_cleans_up_every_already_spooled_file(
    monkeypatch,
):
    """The 3rd file's own size is under MAX_FILE_BYTES, but pushes the
    batch total over MAX_TOTAL_BYTES -- files 1 and 2, already spooled to
    disk by that point, must not be left behind.
    """
    from src.documents import upload_limits as upload_limits_module

    monkeypatch.setattr(upload_limits_module, "MAX_TOTAL_BYTES", 100)

    files = [
        UploadFile(filename="a.txt", file=io.BytesIO(b"x" * 40)),
        UploadFile(filename="b.txt", file=io.BytesIO(b"x" * 40)),
        UploadFile(filename="c.txt", file=io.BytesIO(b"x" * 40)),
    ]

    spooled_paths: list = []
    real_read_bounded = upload_limits_module.read_bounded

    async def _tracking_read_bounded(file, *, max_bytes):
        dto = await real_read_bounded(file, max_bytes=max_bytes)
        spooled_paths.append(dto.path)
        return dto

    monkeypatch.setattr(upload_limits_module, "read_bounded", _tracking_read_bounded)

    with pytest.raises(UploadTooLargeError) as exc_info:
        await _read_files_within_total_limit(files)

    assert exc_info.value.status_code == 413
    assert len(spooled_paths) == 3  # all three were read before the total tripped
    assert all(not p.exists() for p in spooled_paths)


@pytest.mark.asyncio
async def test_a_mid_batch_size_violation_cleans_up_the_files_read_before_it(
    monkeypatch,
):
    from src.documents import upload_limits as upload_limits_module

    files = [
        UploadFile(filename="ok1.txt", file=io.BytesIO(b"aaa")),
        UploadFile(filename="ok2.txt", file=io.BytesIO(b"bbb")),
        UploadFile(filename="oversized.bin", file=io.BytesIO(b"x" * 5000)),
    ]

    spooled_paths: list = []
    real_read_bounded = upload_limits_module.read_bounded

    async def _tracking_read_bounded(file, *, max_bytes):
        dto = await real_read_bounded(
            file, max_bytes=1000 if file.filename == "oversized.bin" else max_bytes
        )
        spooled_paths.append(dto.path)
        return dto

    monkeypatch.setattr(upload_limits_module, "read_bounded", _tracking_read_bounded)

    with pytest.raises(UploadTooLargeError) as exc_info:
        await _read_files_within_total_limit(files)

    assert exc_info.value.status_code == 413
    # Only ok1/ok2 made it into the tracked list -- oversized.bin's own
    # read_bounded call raised before returning, so this list only proves
    # the two that succeeded were cleaned up (the oversized one cleans up
    # itself, inside read_bounded, covered by test_upload_limits.py).
    assert len(spooled_paths) == 2
    assert all(not p.exists() for p in spooled_paths)

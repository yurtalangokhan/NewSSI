"""AttachmentImageStore: owner-scoped image bytes for documents that embed chat attachments."""

from __future__ import annotations

import io

from PIL import Image
import pytest

from core.types.authored_documents import AttachmentImageInfo
from service.documents.image_loading import MAX_IMAGE_BYTES
from service.storage import file_service
from service.storage.attachment_image_store import AttachmentImageStore

USER = "user-1"


def _png(size: tuple[int, int] = (4, 3)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeRepository:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []

    async def get_by_file_id(self, file_id: str, user_id: str):
        return next((r for r in self.rows if r["file_id"] == file_id and r["user_id"] == user_id), None)

    async def list_by_thread(self, thread_id):
        return [r for r in self.rows if r["thread_id"] == str(thread_id)]


def _row(file_id: str, **overrides) -> dict:
    return {
        "file_id": file_id,
        "user_id": USER,
        "filename": f"{file_id}.png",
        "mime_type": "image/png",
        "chat_file_type": "image",
        "minio_object_key": f"documents/{file_id}",
        "thread_id": "00000000-0000-0000-0000-000000000001",
        **overrides,
    }


@pytest.fixture(autouse=True)
def _clean_cache():
    yield
    for file_id in ("cached", "remote", "foreign", "doc", "big", "row"):
        file_service.evict_file(file_id)


@pytest.mark.asyncio
async def test_a_cached_image_owned_by_the_caller_is_returned() -> None:
    file_service.store_file("cached", _png(), "image/png", "a.png", owner_id=USER)

    data = await AttachmentImageStore(repository=_FakeRepository()).load(USER, "cached")

    assert data is not None
    assert Image.open(io.BytesIO(data)).size == (4, 3)


@pytest.mark.asyncio
async def test_a_cached_image_of_another_user_is_not_served() -> None:
    file_service.store_file("foreign", _png(), "image/png", "a.png", owner_id="someone-else")

    assert await AttachmentImageStore(repository=_FakeRepository()).load(USER, "foreign") is None


@pytest.mark.asyncio
async def test_an_uncached_image_is_recovered_from_object_storage(monkeypatch) -> None:
    monkeypatch.setattr("service.storage.minio_service.download_file", lambda key: _png())
    repository = _FakeRepository([_row("remote")])

    data = await AttachmentImageStore(repository=repository).load(USER, "remote")

    assert data is not None
    assert file_service.get_file("remote").owner_id == USER


@pytest.mark.asyncio
async def test_an_unknown_id_resolves_to_nothing() -> None:
    assert await AttachmentImageStore(repository=_FakeRepository()).load(USER, "nope") is None


@pytest.mark.asyncio
async def test_a_non_image_attachment_is_refused() -> None:
    file_service.store_file("doc", b"%PDF-1.4", "application/pdf", "a.pdf", owner_id=USER)

    assert await AttachmentImageStore(repository=_FakeRepository()).load(USER, "doc") is None


@pytest.mark.asyncio
async def test_an_oversized_image_is_refused() -> None:
    file_service.store_file("big", b"x" * (MAX_IMAGE_BYTES + 1), "image/png", "a.png", owner_id=USER)

    assert await AttachmentImageStore(repository=_FakeRepository()).load(USER, "big") is None


@pytest.mark.asyncio
async def test_an_undecodable_image_is_refused() -> None:
    file_service.store_file("row", b"not an image", "image/png", "a.png", owner_id=USER)

    assert await AttachmentImageStore(repository=_FakeRepository()).load(USER, "row") is None


@pytest.mark.asyncio
async def test_a_webp_image_is_normalised_to_a_format_the_renderers_embed() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (5, 5), "blue").save(buffer, format="WEBP")
    file_service.store_file("cached", buffer.getvalue(), "image/webp", "a.webp", owner_id=USER)

    data = await AttachmentImageStore(repository=_FakeRepository()).load(USER, "cached")

    assert data is not None
    assert Image.open(io.BytesIO(data)).format in {"PNG", "JPEG"}


@pytest.mark.asyncio
async def test_thread_listing_returns_only_the_callers_images() -> None:
    thread_id = "00000000-0000-0000-0000-000000000001"
    repository = _FakeRepository(
        [
            _row("one"),
            _row("pdf", mime_type="application/pdf", chat_file_type="document"),
            _row("theirs", user_id="other"),
            _row("elsewhere", thread_id="00000000-0000-0000-0000-000000000002"),
        ]
    )

    images = await AttachmentImageStore(repository=repository).list_for_thread(USER, thread_id)

    assert images == [AttachmentImageInfo(file_id="one", filename="one.png", mime_type="image/png")]

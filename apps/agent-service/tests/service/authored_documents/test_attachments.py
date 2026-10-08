"""AttachmentResolver and the service's use of it: save is strict, export is lenient."""

from __future__ import annotations

import pytest

from core.exceptions.authored_documents import AttachmentReferenceError
from core.types.authored_documents import SourceFormat
from service.authored_documents.attachments import AttachmentResolver
from tests.service.authored_documents.test_service import ACTOR, FakeRepo, FakeStore, FakeValidator
from service.authored_documents.service import AuthoredDocumentService
from service.documents.rendering import RenderedDocument


class _Loader:
    def __init__(self, images: dict[str, bytes]) -> None:
        self.images = images
        self.calls: list[tuple[str, str]] = []

    async def load(self, user_id: str, file_id: str) -> bytes | None:
        self.calls.append((user_id, file_id))
        return self.images.get(file_id)


MARKDOWN = SourceFormat.MARKDOWN


@pytest.mark.asyncio
async def test_resolves_every_referenced_image_for_the_caller() -> None:
    loader = _Loader({"a": b"A", "b": b"B"})
    content = "![x](attachment:a)\n\n![y](attachment:b)\n\n![z](attachment:a)\n"

    images = await AttachmentResolver(loader).resolve("u1", content, MARKDOWN, strict=True)

    assert images == {"a": b"A", "b": b"B"}
    assert loader.calls == [("u1", "a"), ("u1", "b")]


@pytest.mark.asyncio
async def test_strict_mode_names_every_unusable_reference() -> None:
    loader = _Loader({"a": b"A"})

    with pytest.raises(AttachmentReferenceError) as caught:
        await AttachmentResolver(loader).resolve(
            "u1", "![](attachment:a)\n\n![](attachment:gone)\n\n![](attachment:nope)", MARKDOWN, strict=True
        )

    assert caught.value.file_ids == ("gone", "nope")


@pytest.mark.asyncio
async def test_lenient_mode_skips_unusable_references() -> None:
    images = await AttachmentResolver(_Loader({"a": b"A"})).resolve(
        "u1", "![](attachment:a)\n\n![](attachment:gone)", MARKDOWN, strict=False
    )

    assert images == {"a": b"A"}


@pytest.mark.asyncio
async def test_content_without_references_never_touches_storage() -> None:
    loader = _Loader({})

    assert await AttachmentResolver(loader).resolve("u1", "# T\n\ntext", MARKDOWN, strict=True) == {}
    assert loader.calls == []


@pytest.mark.asyncio
async def test_only_markdown_sources_are_scanned() -> None:
    loader = _Loader({})

    assert await AttachmentResolver(loader).resolve("u1", '{"a": "attachment:x"}', SourceFormat.JSON, strict=True) == {}
    assert loader.calls == []


class _RecordingRenderer:
    def __init__(self) -> None:
        self.attachment_images: list[dict[str, bytes]] = []

    async def render(self, *, source_format, format, filename, title, content, options, attachment_images=None):
        self.attachment_images.append(dict(attachment_images or {}))
        return RenderedDocument(content.encode(), "text/markdown", filename)


def _service(images: dict[str, bytes]):
    renderer = _RecordingRenderer()
    service = AuthoredDocumentService(
        repository=FakeRepo(),
        file_store=FakeStore(),
        renderer=renderer,
        validator=FakeValidator(),
        attachments=AttachmentResolver(_Loader(images)),
    )
    return service, renderer


@pytest.mark.asyncio
async def test_create_hands_resolved_images_to_the_renderer() -> None:
    service, renderer = _service({"a": b"A"})

    await service.create(ACTOR, filename="r", format="pdf", content="# R\n\n![x](attachment:a)\n")

    assert renderer.attachment_images == [{"a": b"A"}]


@pytest.mark.asyncio
async def test_create_rejects_an_unknown_attachment_and_saves_nothing() -> None:
    service, renderer = _service({})

    with pytest.raises(AttachmentReferenceError):
        await service.create(ACTOR, filename="r", format="pdf", content="![x](attachment:gone)")

    assert renderer.attachment_images == []
    assert service._file_store.saved == []


@pytest.mark.asyncio
async def test_export_skips_a_vanished_attachment_instead_of_failing() -> None:
    service, renderer = _service({"a": b"A"})
    created = await service.create(ACTOR, filename="r", format="md", content="![x](attachment:a)")
    service._attachments = AttachmentResolver(_Loader({}))

    exported = await service.export(ACTOR.user_id, created.document.id, 1, "pdf")

    assert exported.filename == "r.pdf"
    assert renderer.attachment_images[-1] == {}

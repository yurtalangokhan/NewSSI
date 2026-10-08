"""Tests for DocumentRenderer, the format-dispatch extracted from the tools."""

from __future__ import annotations

import pytest

from core.exceptions.authored_documents import InvalidDocumentContentError
from core.types.authored_documents import SourceFormat
from service.documents.rendering import DocumentRenderer


class NoDiagrams:
    async def resolve(self, sources):
        self.sources = list(sources)
        return {}


@pytest.mark.asyncio
async def test_markdown_to_docx_resolves_diagrams_first() -> None:
    diagrams = NoDiagrams()
    rendered = await DocumentRenderer(diagram_images=diagrams).render(
        source_format=SourceFormat.MARKDOWN,
        format="docx",
        filename="rapor.docx",
        title="R",
        content="# R\n\n```mermaid\nflowchart LR\n  A-->B\n```\n",
        options={},
    )
    assert rendered.mime_type.endswith("wordprocessingml.document")
    assert diagrams.sources == ["flowchart LR\n  A-->B"]


@pytest.mark.asyncio
async def test_sheets_to_csv() -> None:
    rendered = await DocumentRenderer(diagram_images=NoDiagrams()).render(
        source_format=SourceFormat.SHEETS_JSON,
        format="csv",
        filename="t.csv",
        title=None,
        content='[{"name": "S", "rows": [["a", 1]]}]',
        options={},
    )
    assert rendered.data.decode("utf-8-sig").startswith("a")


@pytest.mark.asyncio
async def test_invalid_json_is_a_domain_error() -> None:
    with pytest.raises(InvalidDocumentContentError):
        await DocumentRenderer(diagram_images=NoDiagrams()).render(
            source_format=SourceFormat.JSON,
            format="json",
            filename="x.json",
            title=None,
            content="{oops",
            options={},
        )


class SomeDiagrams:
    def __init__(self, ok: set[str]):
        self.ok = ok

    async def resolve(self, sources):
        from service.documents.blocks import DiagramBlock

        return {DiagramBlock(s).digest: b"png" for s in sources if s in self.ok}


_TWO_DIAGRAMS = "# R\n\n```mermaid\ngraph A\n```\n\n```mermaid\ngraph B\n```\n"


async def _render(diagrams, fmt: str = "docx", content: str = _TWO_DIAGRAMS):
    return await DocumentRenderer(diagram_images=diagrams).render(
        source_format=SourceFormat.MARKDOWN, format=fmt, filename="r", title=None, content=content, options={}
    )


@pytest.mark.asyncio
async def test_diagrams_complete_reflects_every_segment_resolving(monkeypatch: pytest.MonkeyPatch) -> None:
    import service.documents as docgen

    monkeypatch.setattr(docgen, "render_docx", lambda *a, **k: b"docx")
    assert (await _render(SomeDiagrams({"graph A", "graph B"}))).diagrams_complete is True
    assert (await _render(SomeDiagrams({"graph A"}))).diagrams_complete is False
    assert (await _render(NoDiagrams(), content="# no diagrams")).diagrams_complete is True
    assert (await _render(NoDiagrams(), fmt="md")).diagrams_complete is True

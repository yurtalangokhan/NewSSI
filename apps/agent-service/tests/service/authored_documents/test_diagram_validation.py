import pytest

from core.types.authored_documents import DiagramCheck, SourceFormat
from core.types.diagrams import DiagramDiagnostic, DiagramRenderTimeout
from service.authored_documents.diagram_validation import DiagramValidator
from core.exceptions.authored_documents import DiagramValidationError

DOC = "# T\n\n```mermaid\nflowchart LR\n  A --> B\n  B -->> C\n```\n\n```mermaid\npie\n  \"a\": 1\n```\n"


class Renderer:
    renderer_version = "fake"

    def __init__(self, bad_line: int | None = 3, raise_exc: Exception | None = None):
        self.validated: list[str] = []
        self.bad_line, self.raise_exc = bad_line, raise_exc

    async def validate(self, source):
        self.validated.append(source)
        if self.raise_exc:
            raise self.raise_exc
        if "-->>" in source:
            return DiagramDiagnostic(line=self.bad_line, message="Parse error on line 3")
        return None

    async def render_png(self, source, *, scale=3.0):  # pragma: no cover
        return b""

    async def aclose(self):  # pragma: no cover
        return None


@pytest.mark.asyncio
async def test_reports_document_line_of_the_bad_diagram_line() -> None:
    with pytest.raises(DiagramValidationError) as caught:
        await DiagramValidator(renderer=Renderer()).check(DOC, SourceFormat.MARKDOWN)
    (diag,) = caught.value.diagnostics
    assert (diag.block_index, diag.document_line, diag.line) == (0, 6, 3)


@pytest.mark.asyncio
async def test_known_valid_blocks_are_not_revalidated() -> None:
    renderer = Renderer()
    validator = DiagramValidator(renderer=renderer)
    good = "```mermaid\npie\n  \"a\": 1\n```"
    assert await validator.check(good, SourceFormat.MARKDOWN) is DiagramCheck.PASSED
    assert await validator.check(good, SourceFormat.MARKDOWN) is DiagramCheck.PASSED
    assert len(renderer.validated) == 1


@pytest.mark.asyncio
async def test_unavailable_renderer_skips_and_non_markdown_is_not_applicable() -> None:
    validator = DiagramValidator(renderer=Renderer(raise_exc=DiagramRenderTimeout("t")))
    assert await validator.check(DOC, SourceFormat.MARKDOWN) is DiagramCheck.SKIPPED
    assert await validator.check("{}", SourceFormat.JSON) is DiagramCheck.NOT_APPLICABLE
    assert await validator.check("# no diagrams", SourceFormat.MARKDOWN) is DiagramCheck.NOT_APPLICABLE


@pytest.mark.asyncio
async def test_local_image_references_are_rejected_before_rendering() -> None:
    renderer = Renderer()
    validator = DiagramValidator(renderer=renderer)
    doc = (
        "# T\n\n```mermaid\nflowchart LR\n"
        '  A@{ img: "/etc/passwd", label: "x" }\n```\n'
    )

    with pytest.raises(DiagramValidationError) as caught:
        await validator.check(doc, SourceFormat.MARKDOWN)

    (diag,) = caught.value.diagnostics
    assert (diag.block_index, diag.document_line, diag.line) == (0, 5, 2)
    assert "/etc/passwd" in diag.message
    # The renderer never ran, so nothing could read the file.
    assert renderer.validated == []


@pytest.mark.asyncio
async def test_inline_and_remote_image_references_are_allowed() -> None:
    renderer = Renderer()
    validator = DiagramValidator(renderer=renderer)
    doc = (
        "# T\n\n```mermaid\nflowchart LR\n"
        '  A@{ img: "data:image/png;base64,AAAA", label: "x" }\n'
        '  B@{ img: "https://example.com/a.png", label: "y" }\n```\n'
    )

    assert await validator.check(doc, SourceFormat.MARKDOWN) is DiagramCheck.PASSED
    assert len(renderer.validated) == 1


def _install_fake_factory(monkeypatch: pytest.MonkeyPatch, fake_cls) -> list:
    import infrastructure.diagrams as diagrams
    import infrastructure.diagrams.mermaidx_renderer as mermaidx

    created: list = []

    def factory(**_kwargs):
        instance = fake_cls()
        created.append(instance)
        return instance

    monkeypatch.setattr(diagrams, "_renderer", None)
    monkeypatch.setattr(mermaidx, "MermaidxDiagramRenderer", factory)
    return created


@pytest.mark.asyncio
async def test_default_renderer_is_resolved_per_check_after_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    from infrastructure.diagrams import close_diagram_renderer

    created = _install_fake_factory(monkeypatch, Renderer)
    validator = DiagramValidator()
    ok = "# T\n\n```mermaid\npie\n  \"a\": 1\n```\n"
    await validator.check(ok, SourceFormat.MARKDOWN)
    await close_diagram_renderer()
    await validator.check(ok.replace("1", "2"), SourceFormat.MARKDOWN)
    assert len(created) == 2 and all(len(r.validated) == 1 for r in created)
    await close_diagram_renderer()


@pytest.mark.asyncio
async def test_unsafe_later_segment_is_rejected_even_after_a_renderer_timeout() -> None:
    renderer = Renderer(raise_exc=DiagramRenderTimeout("t"))
    doc = (
        "# T\n\n```mermaid\npie\n  \"a\": 1\n```\n\n"
        '```mermaid\nflowchart LR\n  A@{ img: "/etc/passwd", label: "x" }\n```\n'
    )

    with pytest.raises(DiagramValidationError) as caught:
        await DiagramValidator(renderer=renderer).check(doc, SourceFormat.MARKDOWN)

    (diag,) = caught.value.diagnostics
    assert diag.block_index == 1 and "/etc/passwd" in diag.message

"""Tests for DiagramImageService: digest-keyed resolution, caching, and the
degrade-to-source-code policy on render failure/timeout."""

from __future__ import annotations

import pytest

from core.types.diagrams import DiagramDiagnostic, DiagramRenderError, DiagramRenderTimeout
from service.documents.blocks import DiagramBlock
from service.documents.diagram_images import DiagramImageService, diagram_display_width


class FakeRenderer:
    renderer_version = "fake-1"

    def __init__(self, fail: dict[str, Exception] | None = None) -> None:
        self.calls: list[str] = []
        self.fail = fail or {}

    async def validate(self, source):  # pragma: no cover - not used here
        return None

    async def render_png(self, source, *, scale=3.0):
        self.calls.append(source)
        if source in self.fail:
            raise self.fail[source]
        return b"png:" + source.encode()

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_resolves_by_digest_and_caches() -> None:
    renderer = FakeRenderer()
    service = DiagramImageService(renderer=renderer, cache_size=8)
    images = await service.resolve(["graph A", "graph A", "graph B"])
    assert set(images) == {DiagramBlock("graph A").digest, DiagramBlock("graph B").digest}
    await service.resolve(["graph A"])
    assert renderer.calls == ["graph A", "graph B"]


@pytest.mark.asyncio
async def test_failures_are_skipped_not_raised() -> None:
    renderer = FakeRenderer(
        fail={"bad": DiagramRenderError(DiagramDiagnostic(1, "x")), "slow": DiagramRenderTimeout("t")}
    )
    images = await DiagramImageService(renderer=renderer, cache_size=8).resolve(["bad", "slow", "ok"])
    assert list(images) == [DiagramBlock("ok").digest]


# ---------------------------------------------------------------------------
# diagram_display_width — a 3x-rendered PNG must be placed at its logical
# (1x) size, converted to the caller's unit, and never blown up past the
# page's content width.
# ---------------------------------------------------------------------------


def testdiagram_display_width_uses_logical_size_below_cap() -> None:
    # 300px actual width, rendered at 3x -> 100 logical px -> 75pt at 0.75pt/px.
    assert diagram_display_width(300, 0.75, max_width=420) == pytest.approx(75.0)


def testdiagram_display_width_caps_at_max_width() -> None:
    # 3000px actual width -> 1000 logical px -> 750pt, capped at the 420pt content width.
    assert diagram_display_width(3000, 0.75, max_width=420) == pytest.approx(420.0)


def testdiagram_display_width_in_inches() -> None:
    # 288px actual width, rendered at 3x -> 96 logical px -> exactly 1 inch at 1/96 in/px.
    assert diagram_display_width(288, 1.0 / 96, max_width=6.0) == pytest.approx(1.0)


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
async def test_default_renderer_is_resolved_per_call_after_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    from infrastructure.diagrams import close_diagram_renderer

    created = _install_fake_factory(monkeypatch, FakeRenderer)
    service = DiagramImageService(cache_size=8)
    await service.resolve(["graph A"])
    await close_diagram_renderer()
    await service.resolve(["graph B"])
    assert len(created) == 2
    assert (created[0].calls, created[1].calls) == (["graph A"], ["graph B"])
    await close_diagram_renderer()


@pytest.mark.asyncio
async def test_unsafe_image_reference_never_reaches_the_renderer() -> None:
    renderer = FakeRenderer()
    unsafe = 'flowchart LR\n  A@{ img: "/etc/passwd", label: "x" }'
    images = await DiagramImageService(renderer=renderer, cache_size=8).resolve([unsafe, "graph ok"])
    assert list(images) == [DiagramBlock("graph ok").digest]
    assert renderer.calls == ["graph ok"]

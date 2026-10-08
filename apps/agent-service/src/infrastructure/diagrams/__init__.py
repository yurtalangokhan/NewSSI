"""Diagram rendering adapters. One process-wide renderer, closed on shutdown."""

from __future__ import annotations

from config_manager import env

from core.types.diagrams import DiagramRenderer

_renderer: DiagramRenderer | None = None


def get_diagram_renderer() -> DiagramRenderer:
    global _renderer
    if _renderer is None:
        from infrastructure.diagrams.mermaidx_renderer import MermaidxDiagramRenderer

        _renderer = MermaidxDiagramRenderer(
            workers=env.MERMAID_RENDER_WORKERS,
            timeout_seconds=env.MERMAID_RENDER_TIMEOUT_SECONDS,
            max_source_chars=env.MERMAID_MAX_SOURCE_CHARS,
        )
    return _renderer


async def close_diagram_renderer() -> None:
    global _renderer
    if _renderer is not None:
        await _renderer.aclose()
        _renderer = None

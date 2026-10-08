"""Resolve Mermaid sources to PNG bytes for the PDF/DOCX renderers.

Explicit degradation policy: a diagram that fails or times out is absent from
the result and the renderer falls back to its source code. Exports never fail
because of a diagram.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable

from config_manager import env

from core.observability.logger import get_logger
from core.types.diagrams import DiagramRenderer, DiagramRenderError, DiagramRendererUnavailable
from service.authored_documents.diagram_source_guard import unsafe_image_reference
from service.documents.blocks import DiagramBlock

logger = get_logger(__name__)

PNG_SCALE = 3.0

# CSS/logical pixel conversions used to place a `PNG_SCALE`x-rendered PNG at
# its logical (1x) size rather than its raw pixel size.
CSS_PX_TO_PT = 0.75
CSS_PX_TO_IN = 1.0 / 96


def diagram_display_width(pixel_width: float, unit_per_px: float, max_width: float) -> float:
    """Logical display width for a `PNG_SCALE`x-rendered diagram PNG.

    `pixel_width` is the PNG's actual pixel width. The diagram was rasterized
    at `PNG_SCALE`x for crispness, so its logical (CSS) pixel width is
    `pixel_width / PNG_SCALE`. `unit_per_px` converts that logical pixel width
    into the caller's unit (points via `CSS_PX_TO_PT`, inches via
    `CSS_PX_TO_IN`), and the result is capped at `max_width` so a small
    diagram is never blown up to the page's full content width.
    """
    return min(max_width, (pixel_width / PNG_SCALE) * unit_per_px)


class DiagramImageService:
    def __init__(self, renderer: DiagramRenderer | None = None, cache_size: int | None = None) -> None:
        # An injected renderer is kept (tests); otherwise the process-wide one
        # is looked up per call, so a renderer closed at shutdown and recreated
        # later is never held on to by a long-lived service.
        self._injected = renderer
        self._cache_size = cache_size if cache_size is not None else env.DOCUMENT_DIAGRAM_CACHE_SIZE
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    def _renderer(self) -> DiagramRenderer:
        if self._injected is not None:
            return self._injected
        from infrastructure.diagrams import get_diagram_renderer

        return get_diagram_renderer()

    async def resolve(self, sources: Iterable[str]) -> dict[str, bytes]:
        images: dict[str, bytes] = {}
        renderer = self._renderer()
        for source in sources:
            digest = DiagramBlock(source).digest
            if digest in images:
                continue
            # Stored revisions may predate the guard or have skipped validation;
            # an unsafe source falls back to code like an unrenderable diagram.
            if unsafe_image_reference(source) is not None:
                logger.warning("Diagram left as source code in export: local image reference")
                continue
            key = f"{renderer.renderer_version}:{digest}"
            if key in self._cache:
                self._cache.move_to_end(key)
                images[digest] = self._cache[key]
                continue
            try:
                png = await renderer.render_png(source, scale=PNG_SCALE)
            except (DiagramRenderError, DiagramRendererUnavailable) as exc:
                logger.warning("Diagram left as source code in export: %s", exc)
                continue
            images[digest] = png
            self._cache[key] = png
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return images

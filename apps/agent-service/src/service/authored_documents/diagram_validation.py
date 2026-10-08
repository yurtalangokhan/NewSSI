"""Validate every Mermaid block of a draft before it is saved."""

from __future__ import annotations

from collections import OrderedDict

from core.exceptions.authored_documents import DiagramBlockDiagnostic, DiagramValidationError
from core.observability.logger import get_logger
from core.types.authored_documents import DiagramCheck, SourceFormat, content_sha256
from core.types.diagrams import DiagramRenderer, DiagramRendererUnavailable
from service.authored_documents.diagram_source_guard import unsafe_image_reference
from service.authored_documents.markdown_segments import mermaid_segments

logger = get_logger(__name__)
_KNOWN_VALID_LIMIT = 1024


class DiagramValidator:
    def __init__(self, renderer: DiagramRenderer | None = None) -> None:
        # Injected renderers are kept (tests); otherwise the process-wide one is
        # resolved per check so a renderer closed at shutdown is never reused.
        self._injected = renderer
        self._known_valid: OrderedDict[str, None] = OrderedDict()

    async def check(self, content: str, source_format: SourceFormat) -> DiagramCheck:
        if source_format is not SourceFormat.MARKDOWN:
            return DiagramCheck.NOT_APPLICABLE
        segments = mermaid_segments(content)
        if not segments:
            return DiagramCheck.NOT_APPLICABLE
        failures: list[DiagramBlockDiagnostic] = []
        # The pure guard covers every block first: a renderer outage (or timeout)
        # later in the loop must never let an unsafe reference through unchecked.
        unsafe_blocks: set[int] = set()
        for index, segment in enumerate(segments):
            # Local file references would be resolved by resvg at render time.
            unsafe = unsafe_image_reference(segment.text)
            if unsafe is None:
                continue
            offset, reference = unsafe
            unsafe_blocks.add(index)
            failures.append(
                DiagramBlockDiagnostic(
                    index,
                    segment.start_line + offset - 1,
                    offset,
                    f"Image reference '{reference}' is not allowed; use a data: URI.",
                )
            )
        renderer = self._renderer()
        for index, segment in enumerate(segments):
            digest = content_sha256(segment.text.strip())
            if index in unsafe_blocks or digest in self._known_valid:
                continue
            try:
                diagnostic = await renderer.validate(segment.text)
            except DiagramRendererUnavailable as exc:
                logger.warning("Diagram validation skipped: %s", exc)
                if failures:
                    break
                return DiagramCheck.SKIPPED
            if diagnostic is None:
                self._remember(digest)
                continue
            line = segment.start_line + (diagnostic.line - 1 if diagnostic.line else 0)
            failures.append(DiagramBlockDiagnostic(index, line, diagnostic.line, diagnostic.message))
        if failures:
            raise DiagramValidationError(tuple(failures))
        return DiagramCheck.PASSED

    def _renderer(self) -> DiagramRenderer:
        if self._injected is not None:
            return self._injected
        from infrastructure.diagrams import get_diagram_renderer

        return get_diagram_renderer()

    def _remember(self, digest: str) -> None:
        self._known_valid[digest] = None
        while len(self._known_valid) > _KNOWN_VALID_LIMIT:
            self._known_valid.popitem(last=False)

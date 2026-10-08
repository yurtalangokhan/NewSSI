"""Diagram rendering port shared by the service layer and its adapters.

The service layer validates and rasterizes diagram sources through
:class:`DiagramRenderer` without knowing which engine or process model sits
behind it, so the port and its error vocabulary live in ``core``.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

_LINE_RE = re.compile(r"Parse error on line (\d+)")
# Engine messages can echo large chunks of source; the diagnostic is shown to
# the model and the user, so it stays short.
_MAX_MESSAGE_CHARS = 600


@dataclass(frozen=True)
class DiagramDiagnostic:
    line: int | None
    message: str


class DiagramRenderError(Exception):
    """The source itself is invalid; retrying the same source cannot succeed."""

    def __init__(self, diagnostic: DiagramDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


class DiagramRendererUnavailable(Exception):  # noqa: N818 - port contract name shared with the service layer
    """The renderer could not answer (worker start failure, crash)."""


class DiagramRenderTimeout(DiagramRendererUnavailable):
    """A render exceeded its time budget; the worker was recycled."""


class DiagramRenderer(Protocol):
    renderer_version: str

    async def validate(self, source: str) -> DiagramDiagnostic | None: ...

    async def render_png(self, source: str, *, scale: float = 3.0) -> bytes: ...

    async def aclose(self) -> None: ...


def diagnostic_from_error(text: str) -> DiagramDiagnostic:
    """Strip engine wrapper prefixes and pull the 1-based line out of a parse error."""
    message = text.strip()
    for prefix in ("Mermaid rendering failed:", "Error:"):
        message = message.removeprefix(prefix).strip()
    match = _LINE_RE.search(message)
    return DiagramDiagnostic(line=int(match.group(1)) if match else None, message=message[:_MAX_MESSAGE_CHARS])

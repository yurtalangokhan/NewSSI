"""Markdown/plain-text passthrough rendering.

Markdown/text output is already the raw richness the model wrote; there is
nothing to reconstruct from the parsed block tree the way DOCX/PDF need to.
`options` is accepted for signature parity with the other renderers but is
not yet consumed — front-matter reconstruction lands in a later phase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from service.documents.options import DocumentOptions


def render_markdown_text(
    title: str | None, markdown: str, options: DocumentOptions | None = None
) -> bytes:
    if not (markdown or "").strip():
        raise ValueError("render_markdown_text: content must not be empty")
    if title:
        return f"# {title}\n\n{markdown}".encode()
    return markdown.encode()

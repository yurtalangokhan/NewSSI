"""Markdown/plain-text passthrough rendering.

Markdown/text output is already the raw richness the model wrote; there is
nothing to reconstruct from the parsed block tree the way DOCX/PDF need to.
`options` is accepted for signature parity with the other renderers but is
not yet consumed — front-matter reconstruction lands in a later phase.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

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


def render_json(
    title: str | None, content: str | dict[str, Any] | list[Any], options: DocumentOptions | None = None
) -> bytes:
    """Pretty-print `content` as a JSON file.

    `content` is either already-parsed JSON (dict/list) or a JSON-encoded
    string; a string that fails to parse is rejected rather than silently
    wrapped, since a broken JSON file is worse than an error the model can
    correct. When `title` is given, the top-level value is wrapped in
    `{"title": ..., "content": ...}` so it survives even for a JSON array.
    """
    if isinstance(content, str):
        if not content.strip():
            raise ValueError("render_json: content must not be empty")
        try:
            parsed: Any = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"render_json: content is not valid JSON: {exc}") from exc
    elif isinstance(content, (dict, list)):
        parsed = content
    else:
        raise ValueError("render_json: content must be a JSON string, object, or array")

    if title:
        parsed = {"title": title, "content": parsed}

    return json.dumps(parsed, indent=2, ensure_ascii=False).encode("utf-8")

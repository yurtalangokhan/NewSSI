"""Small text helpers shared by content-oriented sources."""

from __future__ import annotations

import html as _html
import re

_BLOCK_END = re.compile(r"<(br|/p|/div|/li|/tr|/h[1-6]|/blockquote|/pre)\s*/?>", re.IGNORECASE)
_DROP = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


def html_to_text(markup: str | None) -> str:
    """Best-effort HTML to plain text: keeps block boundaries as newlines."""
    if not markup:
        return ""
    text = _DROP.sub("", markup)
    text = _BLOCK_END.sub("\n", text)
    text = _TAG.sub("", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

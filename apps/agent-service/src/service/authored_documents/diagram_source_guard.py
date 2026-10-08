"""Reject Mermaid image references that could read local files at render time.

``mermaidx`` renders through resvg, which follows ``<image href>`` values. A
``file:`` URL or a bare absolute path inside a Mermaid image shape would let a
draft embed any file the service can read (``/etc/passwd``) into the exported
PNG or into the panel's SVG. Only inline ``data:`` images and ``http(s)``
references are allowed: resvg resolves neither against the local filesystem.
"""

from __future__ import annotations

import html
import re

_ALLOWED_PREFIXES = ("data:", "http://", "https://")

# A value is either quoted (single or double, optionally backslash-escaped as in
# a string embedded in another string) or bare up to whitespace or the tag end.
_HTML_VALUE = r"""\s*=\s*(?:\\*(?P<quote>['"])(?P<quoted>.*?)\\*(?P=quote)|(?P<bare>[^\s>'"\\]+))"""
_INLINE_VALUE = r"""\s*:\s*(?:\\*(?P<quote>['"])(?P<quoted>.*?)\\*(?P=quote)|(?P<bare>[^\s,}'"\\]+))"""

_IMAGE_PATTERNS = (
    re.compile(r"<img\b[^>]*?\bsrc" + _HTML_VALUE, re.I | re.S),
    re.compile(r"<image\b[^>]*?\bhref" + _HTML_VALUE, re.I | re.S),
    re.compile(r"\bimg" + _INLINE_VALUE, re.I | re.S),
)


def _is_allowed(reference: str) -> bool:
    # XML/HTML entities are decoded before resvg sees the value, so the prefix
    # check must run on the decoded form (``&#47;etc`` is ``/etc``).
    return html.unescape(reference).strip().lower().startswith(_ALLOWED_PREFIXES)


def unsafe_image_reference(source: str) -> tuple[int, str] | None:
    """Return the ``(line, reference)`` of the first disallowed image reference.

    ``line`` is 1-based within ``source``; ``None`` means every image reference
    is inline data or an absolute URL.
    """
    for pattern in _IMAGE_PATTERNS:
        for match in pattern.finditer(source):
            group = "quoted" if match.group("quoted") is not None else "bare"
            reference = match.group(group).strip()
            if not reference or _is_allowed(reference):
                continue
            line = source.count("\n", 0, match.start(group)) + 1
            return line, reference
    return None

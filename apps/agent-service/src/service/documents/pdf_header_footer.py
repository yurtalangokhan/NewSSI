"""PDF header/footer text resolution.

Mirrors `service.documents.header_footer` but returns plain strings for
direct canvas drawing instead of python-docx runs. `{pages}` is left as a
literal placeholder because the final page count isn't known until the
whole document has been laid out — `pdf_canvas.NumberedCanvas` performs
that substitution once building is complete.
"""

from __future__ import annotations

import re

_PLACEHOLDER_RE = re.compile(r"\{(page|pages|title|date|version)\}")


def needs_deferred_page_count(template: str) -> bool:
    return "{pages}" in template


def resolve_segment(template: str, page_num: int, substitutions: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "page":
            return str(page_num)
        if token == "pages":
            return "{pages}"
        return substitutions.get(token, "")

    return _PLACEHOLDER_RE.sub(replace, template)

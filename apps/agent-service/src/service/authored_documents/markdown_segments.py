"""Fence-aware segmentation of Markdown into top-level blocks.

Deliberately independent of ``service.documents.markdown_parser``: the parser
builds a rendering tree and drops source positions, while diffs, stats,
outlines and diagram validation need the *source text and line numbers* of
each block. ``start_line`` of a fenced block is the line of its first content
line (the line after the opening fence).
"""

from __future__ import annotations

from dataclasses import dataclass
import re

_SEGMENT_FENCE_RE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)")
_SEGMENT_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SEGMENT_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_SEGMENT_TABLE_RE = re.compile(r"^\s*\|")


@dataclass(frozen=True)
class Segment:
    kind: str
    label: str
    text: str
    start_line: int
    end_line: int
    language: str | None = None


def _line_kind(line: str) -> str:
    if _SEGMENT_TABLE_RE.match(line):
        return "table"
    if _SEGMENT_LIST_RE.match(line):
        return "list"
    if line.lstrip().startswith(">"):
        return "quote"
    return "paragraph"


def segment_markdown(markdown: str) -> list[Segment]:
    lines = (markdown or "").split("\n")
    segments: list[Segment] = []
    label = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        fence = _SEGMENT_FENCE_RE.match(line)
        if fence:
            marker, language = fence.group(1), (fence.group(2) or None)
            body_start = i + 1
            j = body_start
            while j < len(lines) and not lines[j].strip().startswith(marker):
                j += 1
            kind = "mermaid" if (language or "").lower() == "mermaid" else "code"
            start_line = body_start + 1
            end_line = max(j, start_line)
            segments.append(Segment(kind, label, "\n".join(lines[body_start:j]), start_line, end_line, language))
            i = j + 1
            continue

        heading = _SEGMENT_HEADING_RE.match(line)
        if heading:
            label = heading.group(2).strip()
            segments.append(Segment("heading", label, line, i + 1, i + 1))
            i += 1
            continue

        kind = _line_kind(line)
        j = i + 1
        while j < len(lines) and lines[j].strip() and not _SEGMENT_FENCE_RE.match(lines[j]):
            if _SEGMENT_HEADING_RE.match(lines[j]):
                break
            if kind in ("table", "list") and _line_kind(lines[j]) != kind and not lines[j].startswith(" "):
                break
            j += 1
        segments.append(Segment(kind, label, "\n".join(lines[i:j]), i + 1, j))
        i = j
    return segments


def mermaid_segments(markdown: str) -> list[Segment]:
    return [s for s in segment_markdown(markdown) if s.kind == "mermaid"]


def outline(markdown: str) -> list[dict[str, int | str]]:
    items: list[dict[str, int | str]] = []
    for segment in segment_markdown(markdown):
        if segment.kind != "heading":
            continue
        match = _SEGMENT_HEADING_RE.match(segment.text)
        if match:
            items.append({"line": segment.start_line, "level": len(match.group(1)), "text": segment.label})
    return items

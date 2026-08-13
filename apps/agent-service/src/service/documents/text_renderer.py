"""Markdown/plain-text/JSON rendering.

Markdown/text output is mostly the raw richness the model wrote, so the
body itself is left untouched except when `numbering.headings` is set (which
requires re-deriving the body from the parsed block tree). What `options`
*does* drive for md/txt: a front-matter block (title/cover metadata,
revision history, approvals, document control), a table of contents, and a
trailing header/footer note — the same content DOCX/PDF render as real page
furniture, expressed here as plain text/Markdown since neither format has a
notion of pages. For json, only `cover`/`front_matter` contribute a
`metadata` envelope; the rest of `options` (fonts, page setup, tables, …)
has no meaning for a data format and is ignored.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from service.documents import header_footer
from service.documents.blocks import HeadingBlock
from service.documents.numbering import prepare_blocks

if TYPE_CHECKING:
    from service.documents.options import DocumentOptions, FrontMatterOptions

_PLACEHOLDER_RE = re.compile(r"\{(page|pages|title|date|version)\}")
_SLUG_STRIP_RE = re.compile(r"[^\w\s-]")
_SLUG_SPACE_RE = re.compile(r"[\s]+")


def _slugify(text: str) -> str:
    slug = _SLUG_STRIP_RE.sub("", text).strip().lower()
    return _SLUG_SPACE_RE.sub("-", slug)


def _substitute_placeholders(template: str, substitutions: dict[str, str]) -> str:
    return _PLACEHOLDER_RE.sub(lambda m: substitutions.get(m.group(1), ""), template)


def _render_front_matter_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    separator = "|".join(["---"] * len(headers))
    header_line = f"| {' | '.join(headers)} |"
    row_lines = [f"| {' | '.join(row)} |" for row in rows]
    return "\n".join([header_line, f"|{separator}|", *row_lines])


def _render_front_matter_section(title: str | None, options: DocumentOptions) -> str | None:
    sections: list[str] = []
    if title:
        sections.append(f"# {title}")

    cover = options.cover
    if cover.enabled:
        meta_lines = []
        if cover.subtitle:
            meta_lines.append(f"*{cover.subtitle}*")
        for value in (
            cover.project,
            f"v{cover.version}" if cover.version else "",
            cover.date,
            cover.author,
            cover.organization,
            cover.classification,
        ):
            if value:
                meta_lines.append(value)
        if meta_lines:
            sections.append("\n".join(meta_lines))

    fm: FrontMatterOptions = options.front_matter
    if fm.document_control:
        lines = [f"- **{key}:** {value}" for key, value in fm.document_control.items()]
        sections.append("**Document Control**\n\n" + "\n".join(lines))
    if fm.revision_history:
        table = _render_front_matter_table(
            ("Version", "Date", "Author", "Description"),
            [(e.version, e.date, e.author, e.description) for e in fm.revision_history],
        )
        sections.append("**Revision History**\n\n" + table)
    if fm.approvals:
        table = _render_front_matter_table(
            ("Role", "Name", "Date"),
            [(e.role, e.name, e.date) for e in fm.approvals],
        )
        sections.append("**Approvals**\n\n" + table)

    return "\n\n".join(sections) if sections else None


def _render_toc_section(blocks: list[Any], toc_title: str, depth: int) -> str | None:
    entries = []
    for block in blocks:
        if isinstance(block, HeadingBlock) and block.level <= depth:
            indent = "  " * (block.level - 1)
            entries.append(f"{indent}- [{block.text}](#{_slugify(block.text)})")
    if not entries:
        return None
    return f"## {toc_title}\n\n" + "\n".join(entries)


def _render_header_footer_note(title: str | None, options: DocumentOptions) -> str | None:
    substitutions = {
        "title": title or options.cover.project or "",
        "date": options.cover.date,
        "version": options.cover.version,
        "page": "",
        "pages": "",
    }
    lines = []
    for hf in (options.header, options.footer):
        if not header_footer.has_content(hf):
            continue
        segments = [
            _substitute_placeholders(segment, substitutions).strip()
            for segment in (hf.left, hf.center, hf.right)
            if segment
        ]
        segments = [s for s in segments if s]
        if segments:
            lines.append(" | ".join(segments))
    if not lines:
        return None
    return "---\n" + "\n".join(lines)


def render_markdown_text(
    title: str | None, markdown: str, options: DocumentOptions | None = None
) -> bytes:
    if not (markdown or "").strip():
        raise ValueError("render_markdown_text: content must not be empty")

    from service.documents.options import DocumentOptions as _DocumentOptions

    options = options or _DocumentOptions()

    body = markdown
    blocks = None
    if options.numbering.headings or options.toc.enabled:
        blocks = prepare_blocks(markdown, options)
        if options.numbering.headings:
            body = _blocks_to_markdown(blocks)

    parts: list[str] = []

    front_matter = _render_front_matter_section(title, options)
    if front_matter:
        parts.append(front_matter)

    if options.toc.enabled and blocks is not None:
        toc = _render_toc_section(blocks, options.toc.title, options.toc.depth)
        if toc:
            parts.append(toc)

    parts.append(body)

    footer_note = _render_header_footer_note(title, options)
    if footer_note:
        parts.append(footer_note)

    return "\n\n".join(parts).encode()


# ---------------------------------------------------------------------------
# Block tree -> Markdown (only used when heading numbering is requested, to
# keep numbered headings consistent with DOCX/PDF without hand-parsing the
# raw text a second time)
# ---------------------------------------------------------------------------


def _spans_to_markdown(spans: list[Any]) -> str:
    parts = []
    for span in spans:
        if span.footnote_id:
            parts.append(f"[^{span.footnote_id}]")
            continue
        text = span.text
        if span.code:
            text = f"`{text}`"
        if span.bold:
            text = f"**{text}**"
        if span.italic:
            text = f"*{text}*"
        if span.link:
            text = f"[{text}]({span.link})"
        parts.append(text)
    return "".join(parts)


def _blocks_to_markdown(blocks: list[Any]) -> str:
    from service.documents.blocks import (
        BulletListBlock,
        CodeBlock,
        FootnoteDefBlock,
        HorizontalRuleBlock,
        ImageBlock,
        OrderedListBlock,
        PageBreakBlock,
        ParagraphBlock,
        QuoteBlock,
        TableBlock,
    )

    lines: list[str] = []
    for block in blocks:
        if isinstance(block, HeadingBlock):
            lines.append(f"{'#' * block.level} {_spans_to_markdown(block.spans)}")
        elif isinstance(block, ParagraphBlock):
            lines.append(_spans_to_markdown(block.spans))
        elif isinstance(block, BulletListBlock | OrderedListBlock):
            is_ordered = isinstance(block, OrderedListBlock)
            counters: dict[int, int] = {}
            for item in block.items:
                for level in [lvl for lvl in counters if lvl > item.level]:
                    del counters[level]
                counters[item.level] = counters.get(item.level, 0) + 1
                marker = f"{counters[item.level]}." if is_ordered else "-"
                indent = "  " * item.level
                checkbox = ""
                if item.checked is not None:
                    checkbox = "[x] " if item.checked else "[ ] "
                lines.append(f"{indent}{marker} {checkbox}{_spans_to_markdown(item.spans)}")
        elif isinstance(block, TableBlock):
            headers = [cell.text for cell in block.header]
            lines.append(f"| {' | '.join(headers)} |")
            lines.append(f"|{'|'.join(['---'] * len(headers))}|")
            for row in block.rows:
                lines.append(f"| {' | '.join(cell.text for cell in row)} |")
            if block.caption:
                lines.append(f"*Tablo: {block.caption}*")
        elif isinstance(block, CodeBlock):
            lines.append(f"```{block.language or ''}\n{block.text}\n```")
        elif isinstance(block, QuoteBlock):
            prefix = f"[!{block.callout_type}] " if block.callout_type else ""
            lines.append(f"> {prefix}{_spans_to_markdown(block.spans)}")
        elif isinstance(block, ImageBlock):
            lines.append(f"![{block.alt}]({block.src})")
            if block.caption:
                lines.append(f"*Şekil: {block.caption}*")
        elif isinstance(block, HorizontalRuleBlock):
            lines.append("---")
        elif isinstance(block, PageBreakBlock):
            lines.append("<!-- pagebreak -->")
        elif isinstance(block, FootnoteDefBlock):
            lines.append(f"[^{block.id}]: {_spans_to_markdown(block.spans)}")
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _json_extra_metadata(options: DocumentOptions) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    cover = options.cover
    if cover.enabled:
        for field_name in (
            "subtitle",
            "project",
            "version",
            "date",
            "author",
            "organization",
            "classification",
        ):
            value = getattr(cover, field_name)
            if value:
                metadata[field_name] = value

    fm = options.front_matter
    if fm.document_control:
        metadata["document_control"] = fm.document_control
    if fm.revision_history:
        metadata["revision_history"] = [entry.model_dump() for entry in fm.revision_history]
    if fm.approvals:
        metadata["approvals"] = [entry.model_dump() for entry in fm.approvals]

    return metadata


def render_json(
    title: str | None,
    content: str | dict[str, Any] | list[Any],
    options: DocumentOptions | None = None,
) -> bytes:
    """Pretty-print `content` as a JSON file.

    `content` is either already-parsed JSON (dict/list) or a JSON-encoded
    string; a string that fails to parse is rejected rather than silently
    wrapped, since a broken JSON file is worse than an error the model can
    correct. When `title` is given (and `options` contributes nothing else),
    the top-level value is wrapped in `{"title": ..., "content": ...}` so it
    survives even for a JSON array. When `options.cover` or
    `options.front_matter` also carry data, they're folded into a richer
    `{"metadata": {...}, "content": ...}` envelope instead.
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

    from service.documents.options import DocumentOptions as _DocumentOptions

    options = options or _DocumentOptions()
    extra_metadata = _json_extra_metadata(options)

    if extra_metadata:
        metadata = {"title": title, **extra_metadata} if title else extra_metadata
        parsed = {"metadata": metadata, "content": parsed}
    elif title:
        parsed = {"title": title, "content": parsed}

    return json.dumps(parsed, indent=2, ensure_ascii=False).encode("utf-8")

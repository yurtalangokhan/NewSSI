"""Markdown → block-tree parser.

Supports a restricted Markdown subset chosen for LLM-authored software
lifecycle documents (SRS/SDD/STD): headings, paragraphs, nested bullet/
ordered/task lists, pipe tables (with column alignment and cell inline
formatting), fenced code blocks, blockquotes/callouts, images, horizontal
rules, manual page breaks and footnotes. Inline emphasis is preserved as
structured spans rather than stripped, so renderers can apply real
bold/italic/code/link formatting.
"""

from __future__ import annotations

import re

from service.documents.blocks import (
    Block,
    BulletListBlock,
    CodeBlock,
    FootnoteDefBlock,
    HeadingBlock,
    HorizontalRuleBlock,
    ImageBlock,
    InlineSpan,
    ListItem,
    OrderedListBlock,
    PageBreakBlock,
    ParagraphBlock,
    QuoteBlock,
    TableBlock,
    TableCell,
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\d+\.\s+(.*)$")
_TASK_MARKER_RE = re.compile(r"^\[([ xX])\]\s+(.*)$")
_FENCE_RE = re.compile(r"^```\s*(\S*)\s*$")
_TABLE_ROW_RE = re.compile(r"^\|.*\|$")
_TABLE_SEPARATOR_CELL_RE = re.compile(r"^(:?-{2,}:?)$")
_HR_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
_CALLOUT_RE = re.compile(r"^\[!(NOTE|TIP|WARNING|IMPORTANT|CAUTION)\]\s*(.*)$", re.IGNORECASE)
_IMAGE_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")
_TABLE_CAPTION_RE = re.compile(r"^\*(Tablo|Table|Şekil|Figure):\s*(.+?)\*$", re.IGNORECASE)
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
_PAGEBREAK_RE = re.compile(r"^(<!--\s*pagebreak\s*-->|\\pagebreak)$", re.IGNORECASE)
_CAPTION_PREFIXES = ("tablo", "table", "şekil", "figure")

# Two spaces (or one tab) of leading indentation advance a list item one
# nesting level; this matches the convention used by GitHub-flavored Markdown.
_INDENT_WIDTH = 2


def _indent_level(raw_line: str) -> int:
    expanded = raw_line.replace("\t", " " * _INDENT_WIDTH)
    stripped = expanded.lstrip(" ")
    indent = len(expanded) - len(stripped)
    return indent // _INDENT_WIDTH


# ---------------------------------------------------------------------------
# Inline span parsing
# ---------------------------------------------------------------------------

_INLINE_TOKEN_RE = re.compile(
    r"(?P<link>\[(?P<link_text>[^\]]*)\]\((?P<link_url>[^)]+)\))"
    r"|(?P<footnote>\[\^(?P<footnote_id>[^\]]+)\])"
    r"|(?P<bold>\*\*(?P<bold_text>.+?)\*\*)"
    r"|(?P<italic>(?<!\*)\*(?!\*)(?P<italic_text>.+?)(?<!\*)\*(?!\*))"
    r"|(?P<code>`(?P<code_text>.+?)`)"
)


def parse_inline(text: str) -> list[InlineSpan]:
    """Tokenize a line of Markdown into plain/bold/italic/code/link/footnote spans."""
    spans: list[InlineSpan] = []
    pos = 0
    for match in _INLINE_TOKEN_RE.finditer(text):
        if match.start() > pos:
            spans.append(InlineSpan(text=text[pos : match.start()]))

        if match.group("link"):
            spans.append(InlineSpan(text=match.group("link_text"), link=match.group("link_url")))
        elif match.group("footnote"):
            spans.append(InlineSpan(text="", footnote_id=match.group("footnote_id")))
        elif match.group("bold"):
            spans.append(InlineSpan(text=match.group("bold_text"), bold=True))
        elif match.group("italic"):
            spans.append(InlineSpan(text=match.group("italic_text"), italic=True))
        elif match.group("code"):
            spans.append(InlineSpan(text=match.group("code_text"), code=True))

        pos = match.end()

    if pos < len(text):
        spans.append(InlineSpan(text=text[pos:]))

    return spans or [InlineSpan(text="")]


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------


def _parse_table_row(line: str) -> list[str]:
    trimmed = line.strip()
    if trimmed.startswith("|"):
        trimmed = trimmed[1:]
    if trimmed.endswith("|"):
        trimmed = trimmed[:-1]
    return [cell.strip() for cell in trimmed.split("|")]


def _cell_alignment(separator_cell: str) -> str:
    starts = separator_cell.startswith(":")
    ends = separator_cell.endswith(":")
    if starts and ends:
        return "center"
    if ends:
        return "right"
    return "left"


def _parse_separator_row(line: str) -> list[str] | None:
    cells = _parse_table_row(line)
    if not cells or not all(_TABLE_SEPARATOR_CELL_RE.match(c) for c in cells):
        return None
    return [_cell_alignment(c) for c in cells]


# ---------------------------------------------------------------------------
# Multi-line block parsers — each consumes lines starting at `i` and returns
# the finished block plus the index of the first unconsumed line.
# ---------------------------------------------------------------------------


def _parse_code_block(lines: list[str], i: int) -> tuple[CodeBlock, int]:
    language = _FENCE_RE.match(lines[i].strip()).group(1) or None
    i += 1
    code_lines: list[str] = []
    while i < len(lines) and not lines[i].strip().startswith("```"):
        code_lines.append(lines[i])
        i += 1
    return CodeBlock(text="\n".join(code_lines), language=language), i + 1


def _parse_table(lines: list[str], i: int) -> tuple[TableBlock, int]:
    header_cells = [TableCell(spans=parse_inline(c)) for c in _parse_table_row(lines[i])]
    alignments = _parse_separator_row(lines[i + 1].strip())
    i += 2
    rows: list[list[TableCell]] = []
    while i < len(lines) and _TABLE_ROW_RE.match(lines[i].strip()):
        rows.append([TableCell(spans=parse_inline(c)) for c in _parse_table_row(lines[i])])
        i += 1
    return TableBlock(header=header_cells, rows=rows, alignments=alignments), i


def _parse_blockquote(lines: list[str], i: int) -> tuple[QuoteBlock, int]:
    n = len(lines)
    quote_lines = [_BLOCKQUOTE_RE.match(lines[i].strip()).group(1)]
    i += 1
    while i < n:
        next_match = _BLOCKQUOTE_RE.match(lines[i].strip())
        if not next_match:
            break
        quote_lines.append(next_match.group(1))
        i += 1

    callout_type: str | None = None
    callout_match = _CALLOUT_RE.match(quote_lines[0].strip())
    if callout_match:
        callout_type = callout_match.group(1).upper()
        quote_lines[0] = callout_match.group(2)
        quote_lines = [line for line in quote_lines if line]

    return QuoteBlock(spans=parse_inline(" ".join(quote_lines)), callout_type=callout_type), i


def _parse_list(lines: list[str], i: int) -> tuple[BulletListBlock | OrderedListBlock, int]:
    n = len(lines)
    is_ordered = _ORDERED_RE.match(lines[i].strip()) is not None
    marker_re = _ORDERED_RE if is_ordered else _BULLET_RE
    items: list[ListItem] = []
    while i < n:
        match = marker_re.match(lines[i].strip())
        if not match:
            break
        level = _indent_level(lines[i])
        content = match.group(1)
        checked: bool | None = None
        task_match = _TASK_MARKER_RE.match(content)
        if task_match:
            checked = task_match.group(1).lower() == "x"
            content = task_match.group(2)
        items.append(ListItem(spans=parse_inline(content), level=level, checked=checked))
        i += 1
    block = OrderedListBlock(items=items) if is_ordered else BulletListBlock(items=items)
    return block, i


def _try_attach_caption(blocks: list[Block], line: str) -> bool:
    """If `line` is a `*Tablo:/Şekil: ...*` caption and the previous block can
    carry one, attach it and report success so the caller can skip the line."""
    match = _TABLE_CAPTION_RE.match(line)
    if not match or match.group(1).lower() not in _CAPTION_PREFIXES:
        return False
    if not blocks or not isinstance(blocks[-1], TableBlock | ImageBlock):
        return False
    blocks[-1].caption = match.group(2).strip()
    return True


# ---------------------------------------------------------------------------
# Main parse loop
# ---------------------------------------------------------------------------


def parse_markdown_blocks(markdown: str) -> list[Block]:
    lines = (markdown or "").splitlines()
    blocks: list[Block] = []
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            blocks.append(ParagraphBlock(spans=parse_inline(" ".join(paragraph_buffer))))
            paragraph_buffer.clear()

    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()

        if not stripped:
            flush_paragraph()
            i += 1
        elif _PAGEBREAK_RE.match(stripped):
            flush_paragraph()
            blocks.append(PageBreakBlock())
            i += 1
        elif _FENCE_RE.match(stripped):
            flush_paragraph()
            block, i = _parse_code_block(lines, i)
            blocks.append(block)
        elif _HEADING_RE.match(stripped):
            flush_paragraph()
            match = _HEADING_RE.match(stripped)
            blocks.append(
                HeadingBlock(level=len(match.group(1)), spans=parse_inline(match.group(2).strip()))
            )
            i += 1
        elif (
            _TABLE_ROW_RE.match(stripped)
            and i + 1 < n
            and _parse_separator_row(lines[i + 1].strip()) is not None
        ):
            flush_paragraph()
            block, i = _parse_table(lines, i)
            blocks.append(block)
        elif _TABLE_CAPTION_RE.match(stripped) and _try_attach_caption(blocks, stripped):
            i += 1
        elif _IMAGE_LINE_RE.match(stripped):
            flush_paragraph()
            match = _IMAGE_LINE_RE.match(stripped)
            blocks.append(ImageBlock(alt=match.group(1), src=match.group(2)))
            i += 1
        elif _FOOTNOTE_DEF_RE.match(stripped):
            flush_paragraph()
            match = _FOOTNOTE_DEF_RE.match(stripped)
            blocks.append(FootnoteDefBlock(id=match.group(1), spans=parse_inline(match.group(2))))
            i += 1
        elif _HR_RE.match(stripped):
            flush_paragraph()
            blocks.append(HorizontalRuleBlock())
            i += 1
        elif _BLOCKQUOTE_RE.match(stripped):
            flush_paragraph()
            block, i = _parse_blockquote(lines, i)
            blocks.append(block)
        elif _BULLET_RE.match(stripped) or _ORDERED_RE.match(stripped):
            flush_paragraph()
            block, i = _parse_list(lines, i)
            blocks.append(block)
        else:
            paragraph_buffer.append(stripped)
            i += 1

    flush_paragraph()
    return blocks

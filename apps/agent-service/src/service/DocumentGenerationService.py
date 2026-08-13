"""
DocumentGenerationService — pure rendering of a restricted Markdown subset
(and tabular data) into PDF, DOCX, XLSX, CSV and plain-text bytes.

No MinIO, no database, no LangChain here — this module only turns content
into bytes. Callers (agents/document_tools.py) own persistence.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Markdown block model
# ---------------------------------------------------------------------------


@dataclass
class HeadingBlock:
    level: int
    text: str


@dataclass
class ParagraphBlock:
    text: str


@dataclass
class BulletListBlock:
    items: list[str]


@dataclass
class OrderedListBlock:
    items: list[str]


@dataclass
class TableBlock:
    header: list[str]
    rows: list[list[str]]


@dataclass
class CodeBlock:
    text: str
    language: str | None = None


Block = HeadingBlock | ParagraphBlock | BulletListBlock | OrderedListBlock | TableBlock | CodeBlock


# ---------------------------------------------------------------------------
# Inline emphasis stripping
# ---------------------------------------------------------------------------

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE_SPAN_RE = re.compile(r"`(.+?)`")


def _strip_inline(text: str) -> str:
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _CODE_SPAN_RE.sub(r"\1", text)
    return text


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\d+\.\s+(.*)$")
_FENCE_RE = re.compile(r"^```\s*(\S*)\s*$")
_TABLE_ROW_RE = re.compile(r"^\|.*\|$")
_TABLE_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")


def _parse_table_row(line: str) -> list[str]:
    trimmed = line.strip()
    if trimmed.startswith("|"):
        trimmed = trimmed[1:]
    if trimmed.endswith("|"):
        trimmed = trimmed[:-1]
    return [cell.strip() for cell in trimmed.split("|")]


def _is_table_separator_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    cells = _parse_table_row(stripped) if _TABLE_ROW_RE.match(stripped) else stripped.split("|")
    cells = [c.strip() for c in cells if c.strip()]
    return bool(cells) and all(_TABLE_SEPARATOR_CELL_RE.match(c) for c in cells)


def parse_markdown_blocks(markdown: str) -> list[Block]:
    """Parse a restricted Markdown subset into a flat list of blocks.

    Supported: headings (#-######), paragraphs, bullet/ordered lists, GitHub
    pipe tables, fenced code blocks, and inline **bold**/*italic*/`code`
    (stripped to plain text for non-code blocks).
    """
    lines = (markdown or "").splitlines()
    blocks: list[Block] = []
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            blocks.append(ParagraphBlock(text=_strip_inline(" ".join(paragraph_buffer))))
            paragraph_buffer.clear()

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        fence_match = _FENCE_RE.match(stripped)
        if fence_match:
            flush_paragraph()
            language = fence_match.group(1) or None
            i += 1
            code_lines: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            blocks.append(CodeBlock(text="\n".join(code_lines), language=language))
            continue

        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            text = _strip_inline(heading_match.group(2).strip())
            blocks.append(HeadingBlock(level=level, text=text))
            i += 1
            continue

        if (
            _TABLE_ROW_RE.match(stripped)
            and i + 1 < n
            and _is_table_separator_line(lines[i + 1])
        ):
            flush_paragraph()
            header = _parse_table_row(stripped)
            i += 2  # skip header + separator
            rows: list[list[str]] = []
            while i < n and _TABLE_ROW_RE.match(lines[i].strip()):
                rows.append(_parse_table_row(lines[i]))
                i += 1
            blocks.append(TableBlock(header=header, rows=rows))
            continue

        bullet_match = _BULLET_RE.match(stripped)
        if bullet_match:
            flush_paragraph()
            items = [_strip_inline(bullet_match.group(1))]
            i += 1
            while i < n:
                next_match = _BULLET_RE.match(lines[i].strip())
                if not next_match:
                    break
                items.append(_strip_inline(next_match.group(1)))
                i += 1
            blocks.append(BulletListBlock(items=items))
            continue

        ordered_match = _ORDERED_RE.match(stripped)
        if ordered_match:
            flush_paragraph()
            items = [_strip_inline(ordered_match.group(1))]
            i += 1
            while i < n:
                next_match = _ORDERED_RE.match(lines[i].strip())
                if not next_match:
                    break
                items.append(_strip_inline(next_match.group(1)))
                i += 1
            blocks.append(OrderedListBlock(items=items))
            continue

        paragraph_buffer.append(stripped)
        i += 1

    flush_paragraph()
    return blocks


# ---------------------------------------------------------------------------
# Filename / mime helpers
# ---------------------------------------------------------------------------

_FORBIDDEN_FILENAME_CHARS_RE = re.compile(r'[<>:"|?*\x00-\x1f]')
_PATH_SEPARATOR_RE = re.compile(r"[\\/]+")
_MAX_FILENAME_LENGTH = 120

_MIME_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "md": "text/markdown",
    "txt": "text/plain",
}


def mime_for_format(fmt: str) -> str:
    try:
        return _MIME_TYPES[fmt]
    except KeyError:
        raise ValueError(f"Unsupported format: {fmt!r}") from None


def sanitize_filename(raw: str, fmt: str) -> str:
    """Build a safe, extension-correct filename from user-supplied input."""
    ext = f".{fmt}"
    raw = (raw or "").strip()
    if not raw:
        return f"document{ext}"

    segments = [s for s in _PATH_SEPARATOR_RE.split(raw) if s not in ("", ".", "..")]
    name = "_".join(segments) if segments else "document"
    name = _FORBIDDEN_FILENAME_CHARS_RE.sub("_", name)

    if not name.lower().endswith(ext.lower()):
        name = f"{name}{ext}"

    if len(name) > _MAX_FILENAME_LENGTH:
        stem = name[: -len(ext)][: _MAX_FILENAME_LENGTH - len(ext)]
        name = f"{stem}{ext}"

    return name


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def render_csv(rows: list[list[Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in rows:
        writer.writerow(["" if cell is None else cell for cell in row])
    # UTF-8 BOM so Excel opens Turkish characters correctly.
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------

_INVALID_SHEET_NAME_CHARS_RE = re.compile(r"[\\/*?:\[\]]")
_MAX_SHEET_NAME_LENGTH = 31


def _sanitize_sheet_name(name: str) -> str:
    sanitized = _INVALID_SHEET_NAME_CHARS_RE.sub("_", name)
    return sanitized[:_MAX_SHEET_NAME_LENGTH] or "Sheet"


def render_xlsx(sheets: list[dict[str, Any]]) -> bytes:
    import openpyxl

    if not sheets:
        raise ValueError("render_xlsx requires at least one sheet")

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    for spec in sheets:
        rows = spec.get("rows") or []
        if not rows:
            raise ValueError(f"Sheet '{spec.get('name', '')}' has no rows")
        worksheet = workbook.create_sheet(title=_sanitize_sheet_name(spec.get("name") or "Sheet"))
        for row in rows:
            worksheet.append(list(row))

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def render_docx(title: str | None, markdown: str) -> bytes:
    import docx

    if not (markdown or "").strip():
        raise ValueError("render_docx: content must not be empty")

    document = docx.Document()
    if title:
        document.add_heading(title, level=0)

    for block in parse_markdown_blocks(markdown):
        _add_docx_block(document, block)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _add_docx_block(document: Any, block: Block) -> None:
    if isinstance(block, HeadingBlock):
        document.add_heading(block.text, level=block.level)
    elif isinstance(block, ParagraphBlock):
        document.add_paragraph(block.text)
    elif isinstance(block, BulletListBlock):
        for item in block.items:
            document.add_paragraph(item, style="List Bullet")
    elif isinstance(block, OrderedListBlock):
        for item in block.items:
            document.add_paragraph(item, style="List Number")
    elif isinstance(block, CodeBlock):
        paragraph = document.add_paragraph()
        run = paragraph.add_run(block.text)
        run.font.name = "Courier New"
    elif isinstance(block, TableBlock):
        table = document.add_table(rows=0, cols=len(block.header))
        table.style = "Table Grid"
        header_cells = table.add_row().cells
        for cell, text in zip(header_cells, block.header, strict=False):
            cell.text = text
        for row in block.rows:
            row_cells = table.add_row().cells
            for cell, text in zip(row_cells, row, strict=False):
                cell.text = text


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

_DEJAVU_REGULAR_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
)
_DEJAVU_BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
)

_pdf_font_name = "Helvetica"
_pdf_font_bold_name = "Helvetica-Bold"
_pdf_font_registered = False


def _register_pdf_font() -> None:
    """Register DejaVu Sans for Unicode (Turkish) PDF text, once per process."""
    global _pdf_font_name, _pdf_font_bold_name, _pdf_font_registered
    if _pdf_font_registered:
        return
    _pdf_font_registered = True

    regular_path = next((p for p in _DEJAVU_REGULAR_CANDIDATES if os.path.exists(p)), None)
    if not regular_path:
        logger.warning(
            "DejaVu Sans font not found; PDF output falls back to Helvetica "
            "and non-Latin1 characters (e.g. Turkish) will not render."
        )
        return

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    bold_path = next((p for p in _DEJAVU_BOLD_CANDIDATES if os.path.exists(p)), regular_path)
    pdfmetrics.registerFont(TTFont("DejaVuSans", regular_path))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold_path))
    _pdf_font_name = "DejaVuSans"
    _pdf_font_bold_name = "DejaVuSans-Bold"


def _escape_pdf_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pdf_styles() -> dict[str, Any]:
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "DocBody", parent=base["Normal"], fontName=_pdf_font_name, fontSize=11, leading=15
    )
    title = ParagraphStyle(
        "DocTitle", parent=base["Title"], fontName=_pdf_font_bold_name, fontSize=20, leading=24
    )
    headings = {
        level: ParagraphStyle(
            f"DocHeading{level}",
            parent=base["Heading1"],
            fontName=_pdf_font_bold_name,
            fontSize=max(18 - level * 2, 12),
            leading=max(22 - level * 2, 16),
        )
        for level in range(1, 7)
    }
    code = ParagraphStyle(
        "DocCode", parent=base["Code"], fontName=_pdf_font_name, fontSize=9, leading=12
    )
    return {"title": title, "body": body, "headings": headings, "code": code}


def _pdf_flowables_for_block(block: Block, styles: dict[str, Any]) -> list[Any]:
    from reportlab.lib import colors
    from reportlab.platypus import (
        ListFlowable,
        ListItem,
        Paragraph,
        Preformatted,
        Spacer,
        Table,
        TableStyle,
    )

    if isinstance(block, HeadingBlock):
        style = styles["headings"].get(block.level, styles["headings"][6])
        return [Paragraph(_escape_pdf_xml(block.text), style), Spacer(1, 6)]
    if isinstance(block, ParagraphBlock):
        return [Paragraph(_escape_pdf_xml(block.text), styles["body"]), Spacer(1, 6)]
    if isinstance(block, BulletListBlock):
        items = [ListItem(Paragraph(_escape_pdf_xml(i), styles["body"])) for i in block.items]
        return [ListFlowable(items, bulletType="bullet"), Spacer(1, 6)]
    if isinstance(block, OrderedListBlock):
        items = [ListItem(Paragraph(_escape_pdf_xml(i), styles["body"])) for i in block.items]
        return [ListFlowable(items, bulletType="1"), Spacer(1, 6)]
    if isinstance(block, CodeBlock):
        return [Preformatted(block.text, styles["code"]), Spacer(1, 6)]
    if isinstance(block, TableBlock):
        data = [block.header, *block.rows]
        table = Table(data)
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), _pdf_font_name),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ]
            )
        )
        return [table, Spacer(1, 6)]
    return []


def render_pdf(title: str | None, markdown: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Spacer

    if not (markdown or "").strip():
        raise ValueError("render_pdf: content must not be empty")

    _register_pdf_font()
    styles = _pdf_styles()

    story: list[Any] = []
    if title:
        from reportlab.platypus import Paragraph

        story.append(Paragraph(_escape_pdf_xml(title), styles["title"]))
        story.append(Spacer(1, 12))

    for block in parse_markdown_blocks(markdown):
        story.extend(_pdf_flowables_for_block(block, styles))

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4).build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Markdown / plain text passthrough
# ---------------------------------------------------------------------------


def render_markdown_text(title: str | None, markdown: str) -> bytes:
    if not (markdown or "").strip():
        raise ValueError("render_markdown_text: content must not be empty")
    if title:
        return f"# {title}\n\n{markdown}".encode()
    return markdown.encode()

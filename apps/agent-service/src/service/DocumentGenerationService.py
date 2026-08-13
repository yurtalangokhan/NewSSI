"""DocumentGenerationService — façade re-exporting `service.documents`.

The rendering implementation moved into the `service.documents` package
(content model, options, themes and one renderer module per output format)
so each part stays focused and independently testable. This module is kept
so `from service import DocumentGenerationService as docgen` and direct
imports of these names keep working unchanged.
"""

from __future__ import annotations

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
from service.documents.docx_renderer import render_docx
from service.documents.markdown_parser import parse_inline, parse_markdown_blocks
from service.documents.naming import mime_for_format, sanitize_filename
from service.documents.options import (
    DocumentOptions,
    SpreadsheetOptions,
    parse_document_options,
    parse_spreadsheet_options,
    warn_unsupported_document_options,
    warn_unsupported_spreadsheet_options,
)
from service.documents.pdf_renderer import render_pdf
from service.documents.text_renderer import render_json, render_markdown_text
from service.documents.xlsx_renderer import render_csv, render_xlsx

__all__ = [
    "Block",
    "BulletListBlock",
    "CodeBlock",
    "DocumentOptions",
    "FootnoteDefBlock",
    "HeadingBlock",
    "HorizontalRuleBlock",
    "ImageBlock",
    "InlineSpan",
    "ListItem",
    "OrderedListBlock",
    "PageBreakBlock",
    "ParagraphBlock",
    "QuoteBlock",
    "SpreadsheetOptions",
    "TableBlock",
    "TableCell",
    "mime_for_format",
    "parse_document_options",
    "parse_inline",
    "parse_markdown_blocks",
    "parse_spreadsheet_options",
    "render_csv",
    "render_docx",
    "render_markdown_text",
    "render_json",
    "render_pdf",
    "render_xlsx",
    "sanitize_filename",
    "warn_unsupported_document_options",
    "warn_unsupported_spreadsheet_options",
]

"""Document generation package — content model, options and format renderers
for the create_document / create_spreadsheet tools."""

from __future__ import annotations

from service.documents.docx_renderer import render_docx
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
    "DocumentOptions",
    "SpreadsheetOptions",
    "mime_for_format",
    "parse_document_options",
    "parse_spreadsheet_options",
    "render_csv",
    "render_docx",
    "render_json",
    "render_markdown_text",
    "render_pdf",
    "render_xlsx",
    "sanitize_filename",
    "warn_unsupported_document_options",
    "warn_unsupported_spreadsheet_options",
]

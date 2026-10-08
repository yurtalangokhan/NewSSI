"""The create tools: draft 1 of a new document or spreadsheet.

Each tool validates the format, then hands the call to ``_create``, which owns
the whole live lifecycle — every failure after the generation opens closes it
with exactly one ``document_generation_end`` error packet.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, tool
from pydantic import Field

from agents.tooling.document_tool_messages import describe_error, unexpected_failure
from agents.tooling.document_tool_support import (
    MissingUserError,
    StreamProgressSink,
    actor_from_config,
    document_service,
    emit_generation_failed,
    emit_rendering_started,
    publish,
)
from core.exceptions import ApplicationError
from core.types.authored_documents import MAX_DOCUMENT_CONTENT_CHARS
from service.authored_documents.formats import DOCUMENT_FORMATS, SPREADSHEET_FORMATS, serialize_sheets
import service.documents as docgen

# The draft operation the create tools perform, as carried on every packet.
_CREATE = "create"

_DOCUMENT_OPTIONS_REFERENCE = """
options (all optional; unknown/invalid values fall back to defaults and never fail the call):
  theme: default|corporate_blue|minimal_gray|academic|dark_accent (pdf/docx only)
  font: {body, heading, mono, size, line_spacing, space_after} (pdf/docx only)
  colors: {heading, accent, text, table_header_bg, table_header_text, table_zebra_bg, code_bg, link} (hex or CSS name; pdf/docx only)
  page: {size: A4|Letter, orientation: portrait|landscape, margins: {top, right, bottom, left} in mm} (pdf/docx only)
  cover: {enabled, subtitle, project, version, date, author, organization, classification, logo} — full page for pdf/docx; rendered as a metadata block for md/txt/json (logo only applies to pdf/docx)
  toc: {enabled, depth, title, mode: auto|field|static} — real navigable TOC for pdf/docx; a plain link list for md; mode ignored outside pdf/docx
  numbering: {headings, max_level, separator} — renders 1 / 1.1 / 1.1.1 heading numbers; applies to pdf/docx/md/txt
  header / footer: {left, center, right, different_first_page, rule} — text supports {page} {pages} {title} {date} {version}; real page furniture for pdf/docx, a trailing text note for md/txt ({page}/{pages} have no meaning there and render empty)
  front_matter: {revision_history: [{version, date, author, description}], approvals: [{role, name, date}], document_control: {key: value}} — rendered as tables/lists on all of pdf/docx/md/txt, and folded into a "metadata" envelope for json
  tables: {style: grid|zebra|minimal, header_bold, caption_prefix, figure_caption_prefix} (pdf/docx only)
  requirement_ids: {enabled, pattern} — regex highlighting for tokens like [SRS-FUNC-001] (pdf/docx only)
  watermark: {text, color} (pdf/docx only)
  pdf: {bookmarks, metadata: {author, title, subject, keywords}} (pdf only)
  Example (pdf/docx): {"theme": "corporate_blue", "cover": {"enabled": true, "version": "1.0"}, "toc": {"enabled": true}, "numbering": {"headings": true}}
  Example (md/txt/json): {"cover": {"enabled": true, "author": "Ada"}, "front_matter": {"revision_history": [{"version": "1.0", "date": "2026-01-01", "author": "Ada", "description": "Initial draft"}]}}
"""

_SPREADSHEET_OPTIONS_REFERENCE = """
options (all optional; unknown/invalid values fall back to defaults and never fail the call):
  theme: default|corporate_blue|minimal_gray|academic|dark_accent (xlsx only)
  header_row, freeze_header, autofilter, autofit_columns, zebra: bool (xlsx only)
  column_widths: [int, ...] (xlsx only)
  column_formats: [text|number|date|percent|currency, ...] (xlsx only)
  column_alignments: [left|center|right, ...] (xlsx only)
  conditional_formats: [{column, rule: equals|greater_than|less_than|contains, value, color}] (xlsx only)
  delimiter: ,|;|\\t|| (csv only, default ",")
  csv_bom: bool — leading UTF-8 BOM so Excel opens Turkish characters correctly; disable for tools that don't expect one (csv only, default true)
  Example (xlsx): {"theme": "corporate_blue", "zebra": true, "conditional_formats": [{"column": 3, "rule": "equals", "value": "FAIL", "color": "#FFC7CE"}]}
  Example (csv): {"delimiter": ";", "csv_bom": false}
"""


async def _create(
    tool_name: str,
    *,
    config: RunnableConfig,
    filename: str,
    format: str,
    chars: int,
    content: Callable[[], str],
    title: str | None,
    options: dict[str, Any] | str | None,
    warn_options: Callable[[str, dict[str, Any] | str | None], None],
) -> str:
    """Draft 1 of a new document through the service, with its stream lifecycle.

    Sanitizing, option parsing, content serialization and publishing all run
    inside the failure handling: whichever step breaks, the UI gets one error
    end for the generation it was shown, and the model a fixed message.
    """
    shown_filename = filename
    try:
        shown_filename = docgen.sanitize_filename(filename, format)
        emit_rendering_started(tool_name, _CREATE, shown_filename, format, chars)
        warn_options(format, options)
        result = await document_service().create(
            actor_from_config(config),
            filename=shown_filename,
            format=format,
            content=content(),
            title=title,
            options=options,
            summary=f"created {shown_filename}",
            progress=StreamProgressSink(tool_name, _CREATE, shown_filename, format, None),
        )
        return publish(tool_name, result)
    except (ApplicationError, MissingUserError) as exc:
        message = describe_error(tool_name, exc)
    except Exception as exc:
        message = unexpected_failure(tool_name, exc)
    emit_generation_failed(tool_name, _CREATE, shown_filename, format, message)
    return message


def _count_rows(sheets: list[dict[str, Any]] | None) -> int:
    """Rows across the sheets, for the progress card only.

    Malformed rows (`{"rows": 5}`) count as zero here; the service's sheet
    validation then rejects them with the normal invalid-content message.
    """
    total = 0
    for sheet in sheets or []:
        rows = sheet.get("rows") if isinstance(sheet, dict) else None
        total += len(rows) if isinstance(rows, list) else 0
    return total


def _warn_document_options(format: str, options: dict[str, Any] | str | None) -> None:
    docgen.warn_unsupported_document_options(format, docgen.parse_document_options(options))


def _warn_spreadsheet_options(format: str, options: dict[str, Any] | str | None) -> None:
    docgen.warn_unsupported_spreadsheet_options(format, docgen.parse_spreadsheet_options(options))


@tool
async def create_document(
    filename: str,
    format: str,
    content: Annotated[str, Field(max_length=MAX_DOCUMENT_CONTENT_CHARS)],
    config: Annotated[RunnableConfig, InjectedToolArg],
    title: str | None = None,
    options: dict[str, Any] | str | None = None,
) -> str:
    """Create a downloadable document (PDF, DOCX, Markdown, plain text, or JSON).

    Args:
        filename: Base file name, without or with the correct extension.
        format: One of "pdf", "docx", "md", "txt", "json". Any other value is rejected.
        content: The document body. For pdf/docx/md/txt this is Markdown
            (headings, paragraphs, lists, pipe tables, and fenced code blocks
            are supported). For json, this must be a valid JSON string (an
            object or array) — it is parsed and re-serialized pretty-printed;
            invalid JSON is rejected rather than written as-is.
        title: Optional document title, rendered above the content. For json,
            wraps the value as `{"title": ..., "content": ...}`.
        options: Optional style/layout configuration (theme, fonts, colors,
            page setup, cover page, table of contents, heading numbering,
            header/footer, tables, watermark) — see the options reference
            appended to this tool's description. Omit for a sensibly-themed
            default; any unrecognized or invalid field silently falls back
            to its default rather than failing the call.

    Returns:
        On success a JSON object describing the saved file (file_id, filename,
        document_id, revision_no, ...); on failure an error description. The
        `download_url` in it is for the UI only — never repeat it to the user.
    """
    if format not in DOCUMENT_FORMATS:
        return f"Error: unsupported document format '{format}'. Use one of: {', '.join(DOCUMENT_FORMATS)}."

    return await _create(
        "create_document",
        config=config,
        filename=filename,
        format=format,
        chars=len(content or ""),
        content=lambda: content,
        title=title,
        options=options,
        warn_options=_warn_document_options,
    )


@tool
async def create_spreadsheet(
    filename: str,
    format: str,
    sheets: list[dict[str, Any]],
    config: Annotated[RunnableConfig, InjectedToolArg],
    options: dict[str, Any] | str | None = None,
) -> str:
    """Create a downloadable spreadsheet (XLSX or CSV) from tabular data.

    Args:
        filename: Base file name, without or with the correct extension.
        format: One of "xlsx", "csv". Any other value is rejected.
        sheets: One or more sheets, each `{"name": str, "rows": [[...], ...]}`.
            For CSV output, only the first sheet's rows are used.
        options: Optional styling (theme, header row, freeze pane, autofilter,
            zebra striping, column widths/formats/alignments, conditional
            formatting) — see the options reference appended to this tool's
            description. Most fields are XLSX-only; CSV only honors
            `delimiter` and `csv_bom`. Any unrecognized or invalid field
            silently falls back to its default.

    Returns:
        On success a JSON object describing the saved file (file_id, filename,
        document_id, revision_no, ...); on failure an error description. The
        `download_url` in it is for the UI only — never repeat it to the user.
    """
    if format not in SPREADSHEET_FORMATS:
        return f"Error: unsupported spreadsheet format '{format}'. Use one of: {', '.join(SPREADSHEET_FORMATS)}."

    row_count = _count_rows(sheets)
    return await _create(
        "create_spreadsheet",
        config=config,
        filename=filename,
        format=format,
        chars=row_count,
        content=lambda: serialize_sheets(sheets or []),
        title=None,
        options=options,
        warn_options=_warn_spreadsheet_options,
    )


create_document.description += _DOCUMENT_OPTIONS_REFERENCE
create_spreadsheet.description += _SPREADSHEET_OPTIONS_REFERENCE

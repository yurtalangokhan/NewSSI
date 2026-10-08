"""Format ↔ kind ↔ source-format rules and structured-content validation."""

from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any

from core.exceptions.authored_documents import (
    InvalidDocumentContentError,
    UnsupportedFormatChangeError,
)
from core.types.authored_documents import (
    MAX_DOCUMENT_CONTENT_CHARS,
    MAX_EDIT_SNIPPET_CHARS,
    MAX_EDITS_PER_CALL,
    MAX_REVISION_SUMMARY_CHARS,
    DocumentKind,
    EditOp,
    SourceFormat,
)

DOCUMENT_FORMATS = ("pdf", "docx", "md", "txt", "json")
SPREADSHEET_FORMATS = ("xlsx", "csv")


def kind_for_format(fmt: str) -> DocumentKind:
    if fmt in DOCUMENT_FORMATS:
        return DocumentKind.DOCUMENT
    if fmt in SPREADSHEET_FORMATS:
        return DocumentKind.SPREADSHEET
    raise InvalidDocumentContentError(f"unsupported format '{fmt}'")


def source_format_for(fmt: str) -> SourceFormat:
    kind = kind_for_format(fmt)
    if kind is DocumentKind.SPREADSHEET:
        return SourceFormat.SHEETS_JSON
    return SourceFormat.JSON if fmt == "json" else SourceFormat.MARKDOWN


def filename_stem(name: str) -> str:
    """Drop one trailing supported-format extension, keeping any other suffix.

    ``sanitize_filename`` only appends the target extension, so a name that
    still carries the previous format's (``r.docx`` → pdf) would otherwise
    become ``r.docx.pdf``; ``plan v1.2`` must keep its ``.2``.
    """
    stem, dot, ext = name.rpartition(".")
    if dot and ext.lower() in DOCUMENT_FORMATS + SPREADSHEET_FORMATS:
        return stem
    return name


def ensure_format_change(current_fmt: str, new_fmt: str, *, content_replaced: bool) -> None:
    if current_fmt == new_fmt:
        return
    if kind_for_format(current_fmt) is not kind_for_format(new_fmt):
        raise UnsupportedFormatChangeError(current_fmt, new_fmt)
    if source_format_for(current_fmt) is not source_format_for(new_fmt) and not content_replaced:
        raise UnsupportedFormatChangeError(current_fmt, new_fmt)


def parse_sheets(content: str) -> list[dict[str, Any]]:
    try:
        sheets = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidDocumentContentError(f"sheets must be JSON: {exc}") from exc
    valid = (
        isinstance(sheets, list)
        and sheets
        and all(
            isinstance(s, dict) and isinstance(s.get("name"), str) and isinstance(s.get("rows"), list) for s in sheets
        )
    )
    if not valid:
        raise InvalidDocumentContentError('sheets must be a list of {"name": str, "rows": [...]}')
    return sheets


def serialize_sheets(sheets: list[dict[str, Any]]) -> str:
    return json.dumps(sheets, ensure_ascii=False, indent=2)


def ensure_valid_content(source_format: SourceFormat, content: str) -> None:
    if not (content or "").strip():
        raise InvalidDocumentContentError("content must not be empty")
    if source_format is SourceFormat.JSON:
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            raise InvalidDocumentContentError(f"invalid JSON: {exc}") from exc
    elif source_format is SourceFormat.SHEETS_JSON:
        parse_sheets(content)


def ensure_within_limits(content: str | None, summary: str) -> None:
    """Bound content and summary before any diffing or rendering touches them."""
    if content is not None and len(content) > MAX_DOCUMENT_CONTENT_CHARS:
        raise InvalidDocumentContentError(f"content exceeds {MAX_DOCUMENT_CONTENT_CHARS} characters")
    if len(summary or "") > MAX_REVISION_SUMMARY_CHARS:
        raise InvalidDocumentContentError(f"summary exceeds {MAX_REVISION_SUMMARY_CHARS} characters")


def ensure_edits_within_limits(edits: Sequence[EditOp]) -> None:
    if len(edits) > MAX_EDITS_PER_CALL:
        raise InvalidDocumentContentError(f"at most {MAX_EDITS_PER_CALL} edits per call")
    for edit in edits:
        if len(edit.old_str) > MAX_EDIT_SNIPPET_CHARS or len(edit.new_str) > MAX_EDIT_SNIPPET_CHARS:
            raise InvalidDocumentContentError(f"edit text exceeds {MAX_EDIT_SNIPPET_CHARS} characters")

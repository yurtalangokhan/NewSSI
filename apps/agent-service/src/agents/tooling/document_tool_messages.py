"""Model-facing wording for authored-document domain errors.

The domain errors carry an i18n ``message`` translated to the *request*
locale — right for the HTTP API, wrong for the model, which needs stable
English instructions it can act on. So every text here is built from the
errors' structured attributes, never from ``str(exc)`` or ``exc.message``.
"""

from __future__ import annotations

from agents.tooling.document_tool_support import MissingUserError
from core.exceptions import ApplicationError
from core.exceptions.authored_documents import (
    AttachmentReferenceError,
    DiagramValidationError,
    DocumentNotFoundError,
    EditApplicationError,
    InvalidDocumentContentError,
    NoChangeError,
    RevisionConflictError,
    RevisionNotFoundError,
    UnsupportedFormatChangeError,
)
from core.observability.logger import get_logger
from service.authored_documents.formats import kind_for_format

logger = get_logger(__name__)

_REASONS = {
    "not_found": "old_str was not found in the current draft",
    "ambiguous": (
        "old_str matches {count} places; add surrounding text so it matches exactly one place "
        "(replace_all=true is only for renaming every occurrence, never for inserting)"
    ),
    "replace_all_insert": (
        "old_str matches {count} places and new_str contains it, so replace_all=true would insert the new "
        "text at every match; anchor on text that occurs once (add surrounding text) and set replace_all=false"
    ),
    "empty_old_str": "old_str is empty; anchor the edit on existing text",
    "no_change": "old_str and new_str are identical",
}


def _describe_format_change_error(exc: UnsupportedFormatChangeError) -> str:
    try:
        same_kind = kind_for_format(exc.from_format) is kind_for_format(exc.to_format)
    except InvalidDocumentContentError:
        same_kind = False
    if same_kind:
        return (
            f"Error: {exc.from_format} → {exc.to_format} needs the content replaced; "
            f"call rewrite_document with the content written as {exc.to_format}."
        )
    return (
        f"Error: {exc.from_format} cannot become {exc.to_format} (documents and "
        "spreadsheets can't be converted into each other). Tell the user."
    )


def describe_error(tool_name: str, exc: Exception) -> str:
    """Turn a document error into an instruction the model can follow on retry."""
    if isinstance(exc, EditApplicationError):
        lines = [f"Error: {tool_name} failed and nothing was saved. Fix these edits and call it again:"]
        for d in exc.diagnostics:
            lines.append(f"- edit {d.index + 1}: " + _REASONS[d.reason].format(count=d.match_count))
            if d.closest:
                lines.append(f"  closest text in the draft (copy it exactly):\n<<<\n{d.closest}\n>>>")
        return "\n".join(lines)
    if isinstance(exc, RevisionConflictError):
        return (
            f"Error: the document changed since draft {exc.base_revision_no}; the latest is draft "
            f"{exc.head_revision_no}. Call read_document and redo your change against it."
        )
    if isinstance(exc, DiagramValidationError):
        parts = [f"diagram {d.block_index + 1} (document line {d.document_line}): {d.message}" for d in exc.diagnostics]
        return "Error: nothing was saved; invalid Mermaid - " + "; ".join(parts) + ". Fix the block and retry once."
    if isinstance(exc, AttachmentReferenceError):
        return (
            "Error: nothing was saved; these attachment images are unknown, not images, or too large: "
            + ", ".join(exc.file_ids)
            + ". Call list_attachments and use a file_id from it as ![alt](attachment:<file_id>)."
        )
    if isinstance(exc, NoChangeError):
        return "Error: the requested change does not modify the document."
    if isinstance(exc, UnsupportedFormatChangeError):
        return _describe_format_change_error(exc)
    if isinstance(exc, InvalidDocumentContentError):
        return f"Error: invalid content: {exc.reason}"
    if isinstance(exc, DocumentNotFoundError | RevisionNotFoundError):
        return "Error: that document or draft does not exist. Call list_documents to see available documents."
    if isinstance(exc, MissingUserError):
        return f"Error: {tool_name} needs an authenticated user and cannot run without one."
    if isinstance(exc, ApplicationError):
        # Any other contract error: its message is locale-dependent, its code is not.
        return f"Error: {tool_name} failed ({exc.code})."
    return unexpected_failure(tool_name, exc)


def unexpected_failure(tool_name: str, exc: Exception) -> str:
    """Log an unanticipated failure and give the model a fixed text.

    Raw exception text can carry internals (paths, SQL, hostnames) and is not
    something the model can act on, so it goes to the log only.
    """
    logger.error("%s failed unexpectedly: %s", tool_name, exc, exc_info=exc)
    return f"Error: {tool_name} failed unexpectedly; the error was logged."

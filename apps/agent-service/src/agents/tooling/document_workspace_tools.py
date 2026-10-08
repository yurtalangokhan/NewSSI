"""The read-side document tools: list this conversation's documents and
attached images, and read a draft's text, so the model can locate what it is
about to edit or embed."""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, tool

from agents.tooling.document_tool_messages import describe_error, unexpected_failure
from agents.tooling.document_tool_support import (
    MissingUserError,
    actor_from_config,
    attachment_store,
    configurable_of,
    document_service,
    parse_uuid,
)
from core.exceptions import ApplicationError
from core.exceptions.authored_documents import DocumentNotFoundError, RevisionNotFoundError
from core.types.authored_documents import AuthoredDocument, SourceFormat
from service.authored_documents.markdown_segments import outline


def _document_entry(document: AuthoredDocument, active_id: str | None) -> dict[str, Any]:
    return {
        "document_id": str(document.id),
        "title": document.title,
        "filename": document.filename,
        "format": document.format,
        "kind": document.kind.value,
        "head_revision_no": document.head_revision_no,
        "updated_at": document.updated_at.isoformat(),
        "active": str(document.id) == active_id,
    }


def _active_document_id(configurable: dict[str, Any]) -> str | None:
    active = configurable.get("active_document")
    if isinstance(active, dict) and active.get("document_id"):
        return str(active["document_id"])
    return None


@tool
async def list_documents(config: Annotated[RunnableConfig, InjectedToolArg]) -> str:
    """List the documents created in this conversation: the active document first,
    then newest first. The entry marked "active" is the one the user currently has
    open. Use it to find a document_id before read_document / edit_document /
    rewrite_document."""
    try:
        actor = actor_from_config(config)
        if actor.thread_id is None:
            return json.dumps({"documents": []})
        documents = await document_service().list_for_thread(actor.user_id, actor.thread_id)
    except (ApplicationError, MissingUserError) as exc:
        return describe_error("list_documents", exc)
    except Exception as exc:
        return unexpected_failure("list_documents", exc)

    active_id = _active_document_id(configurable_of(config))
    entries = [_document_entry(d, active_id) for d in sorted(documents, key=lambda d: d.updated_at, reverse=True)]
    # Stable sort: the open document first, the rest stay newest first.
    entries.sort(key=lambda entry: not entry["active"])
    return json.dumps({"documents": entries}, ensure_ascii=False)


@tool
async def list_attachments(config: Annotated[RunnableConfig, InjectedToolArg]) -> str:
    """List the images the user attached to this conversation, oldest first. To put one in
    a document, write its `markdown` value on its own line in the document content, e.g.
    `![Sales chart](attachment:<file_id>)`, and set a meaningful alt text. Only ids from
    this list work; call it whenever the user asks to include an attached image."""
    try:
        actor = actor_from_config(config)
        if actor.thread_id is None:
            return json.dumps({"attachments": []})
        images = await attachment_store().list_for_thread(actor.user_id, actor.thread_id)
    except (ApplicationError, MissingUserError) as exc:
        return describe_error("list_attachments", exc)
    except Exception as exc:
        return unexpected_failure("list_attachments", exc)
    entries = [
        {
            "file_id": image.file_id,
            "filename": image.filename,
            "mime_type": image.mime_type,
            "markdown": f"![{image.filename}](attachment:{image.file_id})",
        }
        for image in images
    ]
    return json.dumps({"attachments": entries}, ensure_ascii=False)


def _line_window(content: str, start_line: int | None, end_line: int | None) -> tuple[list[str], int, int, int]:
    """Clamp a 1-based inclusive range to the draft; (lines, start, end, total)."""
    lines = content.splitlines()
    total = len(lines)
    if total == 0:
        return [], 0, 0, 0
    start = min(max(start_line or 1, 1), total)
    end = min(max(end_line or total, start), total)
    return lines[start - 1 : end], start, end, total


@tool
async def read_document(
    document_id: str,
    config: Annotated[RunnableConfig, InjectedToolArg],
    revision_no: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    with_line_numbers: bool = True,
) -> str:
    """Read a draft's source text (Markdown, JSON, or sheets JSON) with its outline.

    Line numbers are for orientation only; edit_document matches exact text, so
    copy old_str without the `NNNN | ` prefix.

    Args:
        document_id: The document to read (see list_documents).
        revision_no: A specific draft number; omit for the latest draft.
        start_line: First line to return (1-based, inclusive); omit for the start.
        end_line: Last line to return (inclusive); omit for the end. Out-of-range
            values are clamped to the draft.
        with_line_numbers: Prefix each line with `NNNN | `; set false for raw text.
    """
    try:
        user_id = actor_from_config(config).user_id
        parsed_id = parse_uuid(document_id)
        if parsed_id is None:
            raise DocumentNotFoundError(document_id)
        service = document_service()
        document = await service.get_document(user_id, parsed_id)
        # Only an omitted number means "latest"; 0 or a negative one is a bad reference.
        if revision_no is not None and revision_no < 1:
            raise RevisionNotFoundError(parsed_id, revision_no)
        revision = await service.get_revision(
            user_id, parsed_id, document.head_revision_no if revision_no is None else revision_no
        )
    except (ApplicationError, MissingUserError) as exc:
        return describe_error("read_document", exc)
    except Exception as exc:
        return unexpected_failure("read_document", exc)

    lines, start, end, total = _line_window(revision.content, start_line, end_line)
    if with_line_numbers:
        lines = [f"{n:>4} | {line}" for n, line in enumerate(lines, start=start)]
    is_markdown = revision.source_format is SourceFormat.MARKDOWN
    return json.dumps(
        {
            "document_id": str(document.id),
            "revision_no": revision.revision_no,
            "head_revision_no": document.head_revision_no,
            "title": revision.title,
            "filename": revision.filename,
            "format": revision.format,
            "source_format": revision.source_format.value,
            "options": revision.options,
            "outline": outline(revision.content) if is_markdown else [],
            "total_lines": total,
            "start_line": start,
            "end_line": end,
            "content": "\n".join(lines),
        },
        ensure_ascii=False,
    )

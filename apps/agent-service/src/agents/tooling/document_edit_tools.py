"""The revise tools: turn an existing draft into the next one.

``edit_document`` applies targeted find-and-replace edits; ``rewrite_document``
replaces the whole body. Both append a new draft to the same document — they
never create a new file — and share ``_revise`` for the head lookup and the
live stream lifecycle.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel, Field

from agents.tooling.document_tool_messages import describe_error, unexpected_failure
from agents.tooling.document_tool_support import (
    MissingUserError,
    StreamProgressSink,
    actor_from_config,
    document_service,
    emit_generation_failed,
    emit_rendering_started,
    parse_uuid,
    publish,
)
from core.exceptions import ApplicationError
from core.exceptions.authored_documents import DocumentNotFoundError
from core.types.authored_documents import (
    MAX_DOCUMENT_CONTENT_CHARS,
    MAX_EDIT_SNIPPET_CHARS,
    MAX_EDITS_PER_CALL,
    MAX_REVISION_SUMMARY_CHARS,
    Actor,
    EditOp,
    RevisionResult,
)
from service.authored_documents import AuthoredDocumentService


class EditInput(BaseModel):
    """One find-and-replace change, as the model writes it."""

    old_str: str = Field(
        max_length=MAX_EDIT_SNIPPET_CHARS,
        description="Exact text copied verbatim from the latest draft (no `NNNN | ` prefix).",
    )
    new_str: str = Field(
        max_length=MAX_EDIT_SNIPPET_CHARS,
        description=(
            "The replacement text. To delete, set old_str to the anchor plus the removed "
            "part and new_str to the anchor alone."
        ),
    )
    replace_all: bool = Field(default=False, description="Replace every occurrence instead of exactly one.")

    def to_edit_op(self) -> EditOp:
        return EditOp(old_str=self.old_str, new_str=self.new_str, replace_all=self.replace_all)


# Runs the service call once the head is known: (service, actor, id, sink) -> result.
_Revision = Callable[[AuthoredDocumentService, Actor, UUID, StreamProgressSink], Awaitable[RevisionResult]]


async def _revise(
    tool_name: str,
    operation: str,
    *,
    config: RunnableConfig,
    document_id: str,
    filename: str | None,
    format: str | None,
    chars: int,
    run: _Revision,
) -> str:
    """Look up the head, open the generation under its filename, run, publish.

    The lookup happens first so the progress card names the real file; a bad
    id or unknown document fails before anything is shown. After that, every
    failure closes the opened generation with exactly one error end.
    """
    try:
        actor = actor_from_config(config)
        service = document_service()
        parsed_id = parse_uuid(document_id)
        if parsed_id is None:
            raise DocumentNotFoundError(document_id)
        head = await service.get_document(actor.user_id, parsed_id)
    except (ApplicationError, MissingUserError) as exc:
        return describe_error(tool_name, exc)
    except Exception as exc:
        return unexpected_failure(tool_name, exc)

    shown_filename = filename or head.filename
    shown_format = format or head.format
    shown_id = str(parsed_id)
    try:
        emit_rendering_started(tool_name, operation, shown_filename, shown_format, chars, shown_id)
        sink = StreamProgressSink(tool_name, operation, shown_filename, shown_format, shown_id)
        return publish(tool_name, await run(service, actor, parsed_id, sink))
    except ApplicationError as exc:
        message = describe_error(tool_name, exc)
    except Exception as exc:
        message = unexpected_failure(tool_name, exc)
    emit_generation_failed(tool_name, operation, shown_filename, shown_format, message, shown_id)
    return message


@tool
async def edit_document(
    document_id: str,
    base_revision_no: int,
    edits: Annotated[list[EditInput], Field(max_length=MAX_EDITS_PER_CALL)],
    summary: Annotated[str, Field(max_length=MAX_REVISION_SUMMARY_CHARS)],
    config: Annotated[RunnableConfig, InjectedToolArg],
    title: str | None = None,
    options: dict[str, Any] | None = None,
    format: str | None = None,
    filename: str | None = None,
) -> str:
    """Change an existing document with targeted edits; saves the result as its next draft.

    Rules:
    - Copy each old_str verbatim from the latest draft — call read_document first
      when the exact current text is not already in this conversation (without the
      `NNNN | ` line prefix); whitespace and punctuation must match exactly.
    - Include enough surrounding text in old_str that it matches exactly one place,
      (a heading or the last paragraph is usually unique; a repeated separator like
      `---` is not). replace_all=true is only for renaming every occurrence; never
      use it to insert, it would paste the new text at every match.
    - Use one edit per distinct change; do not merge distant changes into one edit.
    - To insert, anchor on existing text: old_str is the anchor, new_str is the anchor
      plus the new text.
    - To delete, old_str is the anchor plus the removed part, new_str is the anchor
      without the removed part.
    - Always pass the latest base_revision_no (the head from list_documents or
      read_document); on a conflict, read the document again and redo the edits.
    - Never fall back to creating a new file with create_document — if an edit fails,
      fix it and call edit_document again.

    Args:
        document_id: The document to change (see list_documents).
        base_revision_no: The draft number the edits were written against — the latest.
        edits: The find-and-replace changes, applied in order; all or nothing.
        summary: One short line describing the change, shown in the draft history.
        title: A new document title; omit to keep the current one.
        options: a partial options object merged over the current options; set a key
            to null to reset it.
        format: A new output format, same kind and same source: pdf/docx/md/txt for a
            document, xlsx/csv for a spreadsheet (converting xlsx ↔ csv keeps the
            sheets and only re-renders the file). For json use rewrite_document.
            Omit to keep the current format.
        filename: A new file name; omit to keep the current one.
    """
    ops = [edit.to_edit_op() for edit in edits]

    def run(service: AuthoredDocumentService, actor: Actor, parsed_id: UUID, sink: StreamProgressSink):
        return service.edit(
            actor,
            parsed_id,
            base_revision_no=base_revision_no,
            edits=ops,
            summary=summary,
            title=title,
            options_patch=options,
            format=format,
            filename=filename,
            progress=sink,
        )

    return await _revise(
        "edit_document",
        "edit",
        config=config,
        document_id=document_id,
        filename=filename,
        format=format,
        chars=sum(len(op.new_str) for op in ops),
        run=run,
    )


@tool
async def rewrite_document(
    document_id: str,
    base_revision_no: int,
    content: Annotated[str, Field(max_length=MAX_DOCUMENT_CONTENT_CHARS)],
    summary: Annotated[str, Field(max_length=MAX_REVISION_SUMMARY_CHARS)],
    config: Annotated[RunnableConfig, InjectedToolArg],
    title: str | None = None,
    options: dict[str, Any] | str | None = None,
    format: str | None = None,
    filename: str | None = None,
) -> str:
    """Replace an existing document's whole body; saves the result as its next draft.

    Prefer edit_document for local changes; rewrite only when most of the text
    changes. Always pass the latest base_revision_no, and never fall back to
    creating a new file with create_document.

    Args:
        document_id: The document to replace (see list_documents).
        base_revision_no: The draft number the rewrite is based on — the latest.
        content: The complete new body: Markdown for pdf/docx/md/txt, a JSON string for
            json, and for a spreadsheet (xlsx/csv) the JSON sheets array
            `[{"name": ..., "rows": [[...], ...]}]`.
        summary: One short line describing the change, shown in the draft history.
        title: A new document title; omit to keep the current one.
        options: The complete options object for the new draft; omit to keep the current one.
        format: A new output format of the same kind; omit to keep it.
        filename: A new file name; omit to keep the current one.
    """

    def run(service: AuthoredDocumentService, actor: Actor, parsed_id: UUID, sink: StreamProgressSink):
        return service.rewrite(
            actor,
            parsed_id,
            base_revision_no=base_revision_no,
            content=content,
            summary=summary,
            title=title,
            options=options,
            format=format,
            filename=filename,
            progress=sink,
        )

    return await _revise(
        "rewrite_document",
        "rewrite",
        config=config,
        document_id=document_id,
        filename=filename,
        format=format,
        chars=len(content or ""),
        run=run,
    )

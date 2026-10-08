"""Shared plumbing for the document tools: who is writing, which service
handles it, and the live SSE packets that mirror a draft's lifecycle.

Every stream packet goes through ``_emit_stream_event`` and every service
lookup through ``document_service`` — the tool modules call both from here, so
tests patch this module to capture packets or stub the draft service.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from core.observability.logger import get_logger
from core.types.authored_documents import (
    Actor,
    AuthorType,
    BlockChange,
    GenerationPhase,
    RevisionResult,
)
from service.authored_documents import AuthoredDocumentService, get_authored_document_service
from service.storage.attachment_image_store import AttachmentImageStore

logger = get_logger(__name__)


class MissingUserError(Exception):
    """The run carries no user, so there is no owner to write or read as."""


def attachment_store() -> AttachmentImageStore:
    """The chat-attachment image lookup (resolved per call, patchable in tests)."""
    return AttachmentImageStore()


def document_service() -> AuthoredDocumentService:
    """The draft service the tools talk to (resolved per call, patchable in tests)."""
    return get_authored_document_service()


def _emit_stream_event(payload: dict[str, Any]) -> None:
    """Best-effort live SSE packet from inside a tool call.

    A node's updates only reach the stream once the whole node returns. The
    default chatbot graph runs its entire tool loop inside one node, so without
    these the UI learns the file exists only after the model has already
    written its closing answer. Failing here is never fatal — the ToolMessage
    still carries the same information at node end.
    """
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
        if writer:
            writer(payload)
    except Exception as exc:
        logger.debug("Could not emit document stream event: %s", exc)


def emit_rendering_started(
    tool_name: str, operation: str, filename: str, fmt: str, chars: int, document_id: str | None = None
) -> None:
    """Tell the UI the tool is running before the service reports a phase.

    Carries the live-packet contract fields so the tracker can adopt it when
    the model wrote its whole call inside a reasoning block.
    """
    _emit_stream_event(
        {
            "type": "document_generation_progress",
            "tool_name": tool_name,
            "operation": operation,
            "document_id": document_id,
            "filename": filename,
            "format": fmt,
            "phase": GenerationPhase.RENDERING.value,
            "applied": None,
            "total": None,
            "changes": [],
            "chars": chars,
        }
    )


def emit_generation_failed(
    tool_name: str, operation: str, filename: str, fmt: str, error: str, document_id: str | None = None
) -> None:
    """Close the generation the UI opened, so no skeleton outlives the call."""
    _emit_stream_event(
        {
            "type": "document_generation_end",
            "tool_name": tool_name,
            "operation": operation,
            "document_id": document_id,
            "filename": filename,
            "format": fmt,
            "status": "error",
            "error": error,
        }
    )


class StreamProgressSink:
    """``ProgressSink`` that forwards the service's phases as live SSE packets.

    Every packet names its tool: the progress tracker suppresses id-less
    repeats by tool name, so a nameless packet would open a second skeleton.
    """

    def __init__(self, tool_name: str, operation: str, filename: str, format: str, document_id: str | None) -> None:
        self._tool_name = tool_name
        self._operation = operation
        self._filename = filename
        self._format = format
        self._document_id = document_id

    def phase(
        self,
        phase: GenerationPhase,
        *,
        applied: int | None = None,
        total: int | None = None,
        changes: tuple[BlockChange, ...] = (),
    ) -> None:
        _emit_stream_event(
            {
                "type": "document_generation_progress",
                "tool_name": self._tool_name,
                "operation": self._operation,
                "document_id": self._document_id,
                "filename": self._filename,
                "format": self._format,
                "phase": phase.value,
                "applied": applied,
                "total": total,
                "changes": [change.to_dict() for change in changes],
            }
        )


def configurable_of(config: RunnableConfig | None) -> dict[str, Any]:
    return (config or {}).get("configurable", {}) or {}


def parse_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


def actor_from_config(config: RunnableConfig | None) -> Actor:
    """Who is writing: the run's user, authored by the running agent/persona.

    A thread id that is not a UUID cannot own a draft (the column is a FK to
    ``thread``), so it is dropped rather than failing the tool call. A run with
    no user is refused: drafts must never land on a shared owner.
    """
    configurable = configurable_of(config)
    user_id = configurable.get("user_id")
    if not user_id:
        raise MissingUserError("no user_id in the run configuration")
    run_id = (config or {}).get("run_id")
    return Actor(
        user_id=str(user_id),
        author_type=AuthorType.AGENT,
        author_id=str(configurable.get("_persona_id") or configurable.get("agent_id") or "agent"),
        thread_id=parse_uuid(configurable.get("thread_id")),
        run_id=str(run_id) if run_id is not None else None,
    )


def revision_payload(result: RevisionResult) -> dict[str, Any]:
    """The tool result and the live ``generated_file`` packet body — one dict,
    so the rebuilt chat history matches what streamed live."""
    return {
        "__generated_file__": True,
        "file_id": result.file.file_id,
        "filename": result.file.filename,
        "mime_type": result.file.mime_type,
        "size_bytes": result.file.size_bytes,
        "download_url": result.file.download_url,
        "document_id": str(result.document.id),
        "revision_no": result.revision.revision_no,
        # Drafts are numbered 1..head and never removed (restore appends).
        "revision_count": result.document.head_revision_no,
        "operation": result.revision.operation.value,
        "summary": result.revision.summary,
        "stats": result.revision.stats.to_dict(),
        "diagram_check": result.diagram_check.value,
    }


def publish(tool_name: str, result: RevisionResult) -> str:
    """Emit the finished draft to the live stream and return the tool result.

    Publishing straight away lets the UI swap its progress skeleton for the
    file card now, rather than when the graph node returns.
    """
    from service.storage.generated_file_packet import build_generated_file_packet_obj

    # Everything that can fail runs before the first packet, so a failure here
    # leaves the caller to emit the single error end — never success + error.
    payload = revision_payload(result)
    packet = build_generated_file_packet_obj(payload)
    text = json.dumps(payload)
    _emit_stream_event(packet)
    _emit_stream_event(
        {
            "type": "document_generation_end",
            "tool_name": tool_name,
            "operation": payload["operation"],
            "document_id": payload["document_id"],
            "filename": payload["filename"],
            "format": result.revision.format,
            "status": "success",
            "error": None,
        }
    )
    return text

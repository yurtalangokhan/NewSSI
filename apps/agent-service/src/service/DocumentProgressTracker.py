"""
Live progress packets for the document tools (create_document / create_spreadsheet).

Producing a file is slow in two ways the user cannot see:

1. **Writing** — the model streams the whole document body into the tool call's
   `content` argument. Those tokens are tool-call arguments, not answer text, so
   `remove_tool_calls()` strips them and nothing reaches the chat: the stream
   looks frozen for as long as the model takes to write the document.
2. **Rendering** — after the arguments are complete the tool still has to render
   the PDF/DOCX/XLSX bytes, upload them to MinIO and write the `document` row.

This tracker turns both phases into `document_generation_*` packets so the
frontend can show a skeleton instead of an apparently stalled stream:

    document_generation_start     -> the model started writing a document
    document_generation_progress  -> still writing (chars so far) / now rendering
    document_generation_end       -> file is ready (or the tool failed)

Every `start` is followed by exactly one `end` — `flush()` closes an in-flight
generation when the stream dies early, so the UI never keeps a skeleton up
forever.
"""

from __future__ import annotations

import json
import re
from typing import Any

from service.GeneratedFilePacket import parse_generated_file_payload

DOCUMENT_TOOL_NAMES = frozenset({"create_document", "create_spreadsheet"})

# Emit a progress packet every N accumulated argument characters. Small enough
# that the counter visibly moves, large enough not to flood the SSE stream.
PROGRESS_CHAR_STEP = 300

# How much text to keep while waiting for a tool name that may straddle two
# streamed chunks — longer than the longest tool name.
_NAME_LOOKBEHIND = 32

PHASE_WRITING = "writing"
PHASE_RENDERING = "rendering"

STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_INCOMPLETE = "incomplete"

# Arguments stream in as a partially built JSON object. `filename` and `format`
# are declared before the (long) `content` argument, so they can usually be read
# out of the buffer while the body is still being written.
_FILENAME_RE = re.compile(r'"filename"\s*:\s*"((?:[^"\\]|\\.)*)"')
_FORMAT_RE = re.compile(r'"format"\s*:\s*"((?:[^"\\]|\\.)*)"')


def is_document_tool(tool_name: str | None) -> bool:
    """True when `tool_name` is one of the always-on document output tools."""
    return bool(tool_name) and tool_name in DOCUMENT_TOOL_NAMES


class DocumentProgressTracker:
    """Turns document-tool activity into `document_generation_*` SSE packets.

    One tracker instance per stream. It follows a single generation at a time —
    the document tools are never fanned out in parallel by the graphs that use
    them, and a second concurrent call simply extends the current one rather
    than producing an unmatched start/end pair.
    """

    def __init__(self, char_step: int = PROGRESS_CHAR_STEP) -> None:
        self._char_step = char_step
        # Tool-call ids whose generation is already finished. A graph reports
        # its messages again in the `updates` event after the node returns, and
        # that replay must not look like a second generation.
        self._closed_call_ids: set[str] = set()
        self._closed_tools: set[str] = set()
        self._reset()

    # -- state ------------------------------------------------------------

    def _reset(self) -> None:
        self._tool_name: str | None = None
        self._call_id: str | None = None
        self._chunk_indexes: set[Any] = set()
        self._args_buffer = ""
        self._chars = 0
        self._chars_at_last_packet = 0
        self._filename: str | None = None
        self._format: str | None = None
        self._phase = PHASE_WRITING

    @property
    def active(self) -> bool:
        """True while a generation has been announced but not yet closed."""
        return self._tool_name is not None

    # -- event handlers ---------------------------------------------------

    def on_chunk(self, message: Any) -> list[dict[str, Any]]:
        """Feed one streamed `AIMessageChunk`; return packets to emit.

        Tool-call arguments arrive as `tool_call_chunks`, where only the first
        chunk of a call carries the tool `name` and the rest carry `args`
        fragments tagged with the same `index`.
        """
        packets: list[dict[str, Any]] = []

        for chunk in getattr(message, "tool_call_chunks", None) or []:
            if not isinstance(chunk, dict):
                continue

            name = chunk.get("name")
            index = chunk.get("index")

            if is_document_tool(name):
                call_id = chunk.get("id")
                if (call_id and call_id in self._closed_call_ids) or (not call_id and name in self._closed_tools):
                    continue
                if not self.active:
                    self._tool_name = name
                    self._call_id = call_id
                    packets.append(self._start_packet())
                self._chunk_indexes.add(index)
            elif name:
                continue  # another tool's call — its arguments are not ours
            elif not self.active or not self._belongs_to_current_call(index):
                continue

            args = chunk.get("args")
            if isinstance(args, str) and args:
                self._args_buffer += args
                self._chars = max(self._chars, len(self._args_buffer))
                self._read_metadata_from_buffer()

            progress = self._progress_packet_if_due()
            if progress is not None:
                packets.append(progress)

        return packets

    def on_tool_call_text(self, text: str) -> list[dict[str, Any]]:
        """Feed tool-call markup the model wrote as plain text.

        Models without native tool calling emit `<tool_call>{...}</tool_call>`
        into the token stream, so there are no `tool_call_chunks` to watch and
        the document body is written with no other outward sign at all. The
        payload is the same JSON, so the same buffer logic applies.
        """
        if not text:
            return []

        packets: list[dict[str, Any]] = []
        self._args_buffer += text

        if not self.active:
            tool_name = next(
                (name for name in DOCUMENT_TOOL_NAMES if name in self._args_buffer), None
            )
            if tool_name is None or tool_name in self._closed_tools:
                # Not a document tool call or already closed — keep only enough to catch a name
                # split across chunk boundaries.
                self._args_buffer = self._args_buffer[-_NAME_LOOKBEHIND:]
                return []
            self._tool_name = tool_name
            packets.append(self._start_packet())

        self._chars = max(self._chars, len(self._args_buffer))
        self._read_metadata_from_buffer()

        progress = self._progress_packet_if_due()
        if progress is not None:
            packets.append(progress)
        return packets

    def adopt_live_packet(self, packet: dict[str, Any]) -> list[dict[str, Any]]:
        """Announce a generation a tool reported without one being in flight.

        A model can produce its entire tool call inside a reasoning block, so
        nothing observable happens until the tool itself starts rendering. Its
        live packets would then describe a generation the client never saw
        start, and the UI has nothing to attach them to.
        """
        if self.active or packet.get("type") != "document_generation_progress":
            return []

        self._tool_name = packet.get("tool_name") or "create_document"
        self._filename = packet.get("filename")
        self._format = packet.get("format")
        self._phase = packet.get("phase") or PHASE_RENDERING
        return [self._start_packet()]

    def on_tool_calls(self, tool_calls: Any) -> list[dict[str, Any]]:
        """Handle a completed AI message's tool calls.

        Marks the switch from *writing* to *rendering*, and also covers models
        that never stream argument chunks — for those this is where the
        generation is announced.
        """
        packets: list[dict[str, Any]] = []

        for tool_call in tool_calls or []:
            name = _field(tool_call, "name")
            if not is_document_tool(name):
                continue

            call_id = _field(tool_call, "id")
            if (call_id and call_id in self._closed_call_ids) or (not call_id and name in self._closed_tools):
                continue  # replayed after the node returned; already reported

            if not self.active:
                self._tool_name = name
                self._call_id = call_id
                packets.append(self._start_packet())

            self._read_metadata_from_args(_field(tool_call, "args"))
            self._phase = PHASE_RENDERING
            packets.append(self._progress_packet())

        return packets

    def on_tool_result(self, tool_name: str | None, content: Any) -> list[dict[str, Any]]:
        """Close the generation when its tool result arrives."""
        payload = parse_generated_file_payload(content)

        if not self.active:
            return []
        if payload is None and tool_name and not is_document_tool(tool_name):
            return []  # some other tool finished while we were generating

        if payload is not None:
            self._filename = payload.get("filename") or self._filename
            return [self._end_packet(STATUS_SUCCESS)]

        error = content.strip() if isinstance(content, str) and content.strip() else None
        return [self._end_packet(STATUS_ERROR, error)]

    def flush(self) -> list[dict[str, Any]]:
        """Close an in-flight generation at end of stream (error / cancellation)."""
        if not self.active:
            return []
        return [self._end_packet(STATUS_INCOMPLETE)]

    def close(self) -> None:
        """Forget the in-flight generation without emitting anything.

        Used when the tool already published its own `document_generation_end`
        through the graph's stream writer, so this tracker must not add a
        second one — neither now nor when the node replays the call.
        """
        self._remember_closed()
        self._reset()

    # -- helpers ----------------------------------------------------------

    def _belongs_to_current_call(self, index: Any) -> bool:
        # Providers that omit `index` give us nothing to match on, so anything
        # streamed while a document call is open is treated as part of it.
        if index is None or not self._chunk_indexes or None in self._chunk_indexes:
            return True
        return index in self._chunk_indexes

    def _read_metadata_from_buffer(self) -> None:
        if self._filename is None:
            match = _FILENAME_RE.search(self._args_buffer)
            if match:
                self._filename = match.group(1)
        if self._format is None:
            match = _FORMAT_RE.search(self._args_buffer)
            if match:
                self._format = match.group(1)

    def _read_metadata_from_args(self, args: Any) -> None:
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                self._args_buffer = args
                self._chars = max(self._chars, len(args))
                self._read_metadata_from_buffer()
                return

        if not isinstance(args, dict):
            return

        self._filename = args.get("filename") or self._filename
        self._format = args.get("format") or self._format

        body = args.get("content")
        if not isinstance(body, str):
            body = json.dumps(args.get("sheets") or "", ensure_ascii=False)
        self._chars = max(self._chars, len(body))

    def _progress_packet_if_due(self) -> dict[str, Any] | None:
        if self._chars - self._chars_at_last_packet < self._char_step:
            return None
        return self._progress_packet()

    def _base_fields(self) -> dict[str, Any]:
        return {
            "tool_name": self._tool_name,
            "filename": self._filename,
            "format": self._format,
        }

    def _start_packet(self) -> dict[str, Any]:
        self._chars_at_last_packet = self._chars
        return {
            "type": "document_generation_start",
            "phase": self._phase,
            **self._base_fields(),
        }

    def _progress_packet(self) -> dict[str, Any]:
        self._chars_at_last_packet = self._chars
        return {
            "type": "document_generation_progress",
            "phase": self._phase,
            "chars": self._chars,
            **self._base_fields(),
        }

    def _remember_closed(self) -> None:
        if self._call_id:
            self._closed_call_ids.add(self._call_id)
        if self._tool_name:
            self._closed_tools.add(self._tool_name)

    def _end_packet(self, status: str, error: str | None = None) -> dict[str, Any]:
        packet = {
            "type": "document_generation_end",
            "status": status,
            "error": error,
            **self._base_fields(),
        }
        self._remember_closed()
        self._reset()
        return packet


def _field(tool_call: Any, key: str) -> Any:
    if isinstance(tool_call, dict):
        return tool_call.get(key)
    return getattr(tool_call, key, None)

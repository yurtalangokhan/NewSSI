"""
Shared helpers for the ``generated_file`` stream/history packet.

A document tool (create_document / create_spreadsheet) returns a JSON string
as its ToolMessage content. Both the live streaming path
(``api.routes.AgentsRoute.message_generator``) and the chat-history rebuild
path (``controller.chat_controller``) need to recognise that payload and turn
it into an identical ``generated_file`` packet — this module is the single
place that knows the wire format so the two paths cannot drift apart.
"""

from __future__ import annotations

import json
from typing import Any

_MARKER_KEY = "__generated_file__"


def parse_generated_file_payload(content: Any) -> dict[str, Any] | None:
    """Return the generated-file dict if `content` is a document-tool JSON payload.

    Returns None for anything else (plain tool output, malformed JSON, a JSON
    value that isn't an object, or an object missing the marker key) so
    callers can fall through to their normal handling.
    """
    if not isinstance(content, str):
        return None

    stripped = content.strip()
    if not stripped.startswith("{"):
        return None

    try:
        payload = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict) or payload.get(_MARKER_KEY) is not True:
        return None

    return payload


def build_generated_file_packet_obj(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the `generated_file` packet body from a parsed tool payload."""
    return {
        "type": "generated_file",
        "file_id": payload.get("file_id"),
        "filename": payload.get("filename"),
        "mime_type": payload.get("mime_type"),
        "size_bytes": payload.get("size_bytes"),
        "download_url": payload.get("download_url"),
    }

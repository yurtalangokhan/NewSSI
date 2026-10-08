"""Tests for the shared generated_file payload parsing/packet-building helpers.

Both the live streaming path (agents_route.message_generator) and the chat
history rebuild path (chat_service) must recognise a document tool's
ToolMessage content identically — this module is their single source of truth.
"""

import json

from service.storage.generated_file_packet import (
    build_generated_file_packet_obj,
    parse_generated_file_payload,
)

_VALID_PAYLOAD = {
    "__generated_file__": True,
    "file_id": "abc123",
    "filename": "rapor.pdf",
    "mime_type": "application/pdf",
    "size_bytes": 42,
    "download_url": "/api/chat/file/abc123?download=1",
}


def test_parse_generated_file_payload_accepts_valid_json_string():
    result = parse_generated_file_payload(json.dumps(_VALID_PAYLOAD))

    assert result == _VALID_PAYLOAD


def test_parse_generated_file_payload_rejects_plain_text():
    assert parse_generated_file_payload("Sonuç: 42") is None


def test_parse_generated_file_payload_rejects_malformed_json():
    assert parse_generated_file_payload("{not json") is None


def test_parse_generated_file_payload_rejects_json_without_marker():
    assert parse_generated_file_payload(json.dumps({"foo": "bar"})) is None


def test_parse_generated_file_payload_rejects_non_string_content():
    assert parse_generated_file_payload(_VALID_PAYLOAD) is None
    assert parse_generated_file_payload(None) is None
    assert parse_generated_file_payload(["not", "a", "string"]) is None


def test_parse_generated_file_payload_rejects_json_array():
    assert parse_generated_file_payload("[1, 2, 3]") is None


def test_build_generated_file_packet_obj_shapes_the_packet():
    packet = build_generated_file_packet_obj(_VALID_PAYLOAD)

    assert packet == {
        "type": "generated_file",
        "file_id": "abc123",
        "filename": "rapor.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 42,
        "download_url": "/api/chat/file/abc123?download=1",
    }


def test_revision_fields_pass_through_and_legacy_payload_is_unchanged() -> None:
    legacy = {"file_id": "f", "filename": "a.pdf", "mime_type": "application/pdf", "size_bytes": 1, "download_url": "/x"}
    assert build_generated_file_packet_obj(legacy) == {"type": "generated_file", **legacy}

    packet = build_generated_file_packet_obj(
        {
            **legacy,
            "document_id": "d",
            "revision_no": 2,
            "revision_count": 2,
            "operation": "edit",
            "summary": "s",
            "stats": {"added": 1},
            "diagram_check": "passed",
        }
    )

    assert packet["document_id"] == "d" and packet["revision_no"] == 2 and packet["stats"] == {"added": 1}
    assert packet["revision_count"] == 2
    assert packet["operation"] == "edit"
    assert packet["summary"] == "s"
    assert packet["diagram_check"] == "passed"

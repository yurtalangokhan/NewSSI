"""Tests for the shared generated_file payload parsing/packet-building helpers.

Both the live streaming path (AgentsRoute.message_generator) and the chat
history rebuild path (chat_controller) must recognise a document tool's
ToolMessage content identically — this module is their single source of truth.
"""

import json

from service.GeneratedFilePacket import (
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

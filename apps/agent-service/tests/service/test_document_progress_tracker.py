"""Tests for the document_generation_* progress packets.

The tracker exists so a slow document tool never looks like a frozen stream:
the model's document body is written into tool-call arguments, which produce no
visible tokens at all. Every announced generation must also be closed, or the
frontend keeps a skeleton up forever.
"""

import json

from service.DocumentProgressTracker import (
    PHASE_RENDERING,
    PHASE_WRITING,
    STATUS_ERROR,
    STATUS_INCOMPLETE,
    STATUS_SUCCESS,
    DocumentProgressTracker,
    is_document_tool,
)


class _Chunk:
    """Minimal stand-in for an AIMessageChunk carrying tool_call_chunks."""

    def __init__(self, tool_call_chunks):
        self.tool_call_chunks = tool_call_chunks


def _args_chunk(args: str, index: int = 0) -> _Chunk:
    return _Chunk([{"name": None, "args": args, "id": None, "index": index}])


def _start_chunk(name: str = "create_document", index: int = 0, call_id: str = "call-1") -> _Chunk:
    return _Chunk([{"name": name, "args": "", "id": call_id, "index": index}])


def _types(packets) -> list[str]:
    return [packet["type"] for packet in packets]


def test_is_document_tool_only_matches_the_document_tools():
    assert is_document_tool("create_document")
    assert is_document_tool("create_spreadsheet")
    assert not is_document_tool("Calculator")
    assert not is_document_tool(None)


def test_start_packet_emitted_on_first_document_tool_chunk():
    tracker = DocumentProgressTracker()

    packets = tracker.on_chunk(_start_chunk())

    assert _types(packets) == ["document_generation_start"]
    assert packets[0]["tool_name"] == "create_document"
    assert packets[0]["phase"] == PHASE_WRITING
    assert tracker.active


def test_no_packets_for_a_non_document_tool_call():
    tracker = DocumentProgressTracker()

    packets = tracker.on_chunk(_start_chunk(name="Calculator"))
    packets += tracker.on_chunk(_args_chunk("x" * 5000))

    assert packets == []
    assert not tracker.active


def test_progress_packets_report_growing_char_count():
    tracker = DocumentProgressTracker(char_step=100)
    tracker.on_chunk(_start_chunk())

    packets = []
    for _ in range(3):
        packets += tracker.on_chunk(_args_chunk("y" * 100))

    assert _types(packets) == ["document_generation_progress"] * 3
    assert [packet["chars"] for packet in packets] == [100, 200, 300]


def test_progress_packets_are_throttled_below_the_char_step():
    tracker = DocumentProgressTracker(char_step=500)
    tracker.on_chunk(_start_chunk())

    assert tracker.on_chunk(_args_chunk("y" * 100)) == []


def test_filename_and_format_are_read_out_of_partially_streamed_args():
    tracker = DocumentProgressTracker(char_step=10)
    tracker.on_chunk(_start_chunk())

    packets = tracker.on_chunk(
        _args_chunk('{"filename": "rapor", "format": "pdf", "content": "# Bas')
    )

    assert packets[-1]["filename"] == "rapor"
    assert packets[-1]["format"] == "pdf"


def test_completed_tool_call_switches_phase_to_rendering():
    tracker = DocumentProgressTracker()
    tracker.on_chunk(_start_chunk())

    packets = tracker.on_tool_calls(
        [
            {
                "name": "create_document",
                "args": {"filename": "rapor.pdf", "format": "pdf", "content": "gövde"},
            }
        ]
    )

    assert _types(packets) == ["document_generation_progress"]
    assert packets[0]["phase"] == PHASE_RENDERING
    assert packets[0]["filename"] == "rapor.pdf"


def test_non_streaming_model_still_gets_a_start_packet():
    """Providers that emit no argument chunks announce the call all at once."""
    tracker = DocumentProgressTracker()

    packets = tracker.on_tool_calls(
        [{"name": "create_spreadsheet", "args": {"filename": "veri.xlsx", "format": "xlsx"}}]
    )

    assert _types(packets) == [
        "document_generation_start",
        "document_generation_progress",
    ]


def test_tool_result_with_generated_file_closes_the_generation_as_success():
    tracker = DocumentProgressTracker()
    tracker.on_chunk(_start_chunk())

    payload = json.dumps(
        {
            "__generated_file__": True,
            "file_id": "abc123",
            "filename": "rapor.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 42,
            "download_url": "/api/chat/file/abc123?download=1",
        }
    )
    packets = tracker.on_tool_result("create_document", payload)

    assert _types(packets) == ["document_generation_end"]
    assert packets[0]["status"] == STATUS_SUCCESS
    assert packets[0]["filename"] == "rapor.pdf"
    assert not tracker.active


def test_tool_error_closes_the_generation_with_the_error_text():
    tracker = DocumentProgressTracker()
    tracker.on_chunk(_start_chunk())

    packets = tracker.on_tool_result("create_document", "Error: unsupported document format 'rtf'.")

    assert packets[0]["status"] == STATUS_ERROR
    assert packets[0]["error"] == "Error: unsupported document format 'rtf'."
    assert not tracker.active


def test_another_tool_finishing_mid_generation_does_not_close_it():
    tracker = DocumentProgressTracker()
    tracker.on_chunk(_start_chunk())

    assert tracker.on_tool_result("Calculator", "42") == []
    assert tracker.active


def test_flush_closes_an_in_flight_generation():
    tracker = DocumentProgressTracker()
    tracker.on_chunk(_start_chunk())

    packets = tracker.flush()

    assert _types(packets) == ["document_generation_end"]
    assert packets[0]["status"] == STATUS_INCOMPLETE
    assert tracker.flush() == []


def test_flush_is_a_no_op_when_nothing_is_being_generated():
    assert DocumentProgressTracker().flush() == []


def test_a_second_document_call_starts_a_fresh_generation():
    tracker = DocumentProgressTracker()
    tracker.on_chunk(_start_chunk())
    tracker.on_tool_result("create_document", "Error: boom")

    packets = tracker.on_chunk(_start_chunk(name="create_spreadsheet", index=1, call_id="call-2"))

    assert _types(packets) == ["document_generation_start"]
    assert packets[0]["tool_name"] == "create_spreadsheet"


def test_a_finished_call_is_not_reopened_when_the_node_replays_it():
    """Graph updates repeat the tool call after the node returns."""
    tracker = DocumentProgressTracker()
    tracker.on_chunk(_start_chunk())
    tracker.on_tool_result("create_document", "Error: boom")

    replayed = [{"name": "create_document", "args": {}, "id": "call-1"}]
    assert tracker.on_tool_calls(replayed) == []
    assert tracker.on_chunk(_start_chunk()) == []
    assert not tracker.active


def test_close_marks_the_call_finished_without_emitting():
    """The tool may publish its own end packet through the stream writer."""
    tracker = DocumentProgressTracker()
    tracker.on_chunk(_start_chunk())

    tracker.close()

    assert not tracker.active
    assert tracker.flush() == []
    assert tracker.on_tool_calls([{"name": "create_document", "args": {}, "id": "call-1"}]) == []
    assert tracker.on_tool_result("create_document", "Error: boom") == []


def test_tool_call_written_as_text_still_announces_a_generation():
    """Models without native tool calling emit the call into the token stream."""
    tracker = DocumentProgressTracker(char_step=100)

    packets = tracker.on_tool_call_text('{"name": "create_document", "arguments": ')
    packets += tracker.on_tool_call_text('{"filename": "rapor", "format": "pdf", ')
    packets += tracker.on_tool_call_text('"content": "' + "x" * 300)

    types = _types(packets)
    assert types[0] == "document_generation_start"
    assert "document_generation_progress" in types
    assert packets[-1]["filename"] == "rapor"
    assert packets[-1]["format"] == "pdf"
    assert packets[-1]["chars"] > 300


def test_tool_call_text_for_another_tool_is_ignored():
    tracker = DocumentProgressTracker(char_step=10)

    assert tracker.on_tool_call_text('{"name": "Calculator", "arguments": {"a": 1}}') == []
    assert not tracker.active


def test_tool_call_text_matches_a_name_split_across_chunks():
    tracker = DocumentProgressTracker()

    packets = tracker.on_tool_call_text('{"name": "create_')
    packets += tracker.on_tool_call_text('document", "arguments": {}')

    assert _types(packets) == ["document_generation_start"]


def test_live_progress_packet_opens_a_generation_that_was_never_announced():
    """A model can write its whole tool call inside a reasoning block."""
    tracker = DocumentProgressTracker()

    packets = tracker.adopt_live_packet(
        {
            "type": "document_generation_progress",
            "tool_name": "create_document",
            "filename": "rapor.pdf",
            "format": "pdf",
            "phase": "rendering",
            "chars": 900,
        }
    )

    assert _types(packets) == ["document_generation_start"]
    assert packets[0]["filename"] == "rapor.pdf"
    assert packets[0]["phase"] == "rendering"
    assert tracker.active


def test_live_progress_packet_is_not_adopted_twice():
    tracker = DocumentProgressTracker()
    tracker.on_chunk(_start_chunk())

    packet = {"type": "document_generation_progress", "tool_name": "create_document"}

    assert tracker.adopt_live_packet(packet) == []


def test_a_lone_file_packet_does_not_open_a_skeleton():
    """Nothing is being awaited once the file exists."""
    tracker = DocumentProgressTracker()

    assert tracker.adopt_live_packet({"type": "generated_file", "filename": "r.pdf"}) == []

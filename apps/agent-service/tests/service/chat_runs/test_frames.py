import json

from service.chat_runs.frames import (
    DONE_PAYLOAD,
    caught_up_payload,
    HEARTBEAT_FRAME,
    error_code_of,
    extract_payload,
    format_event,
    format_unsequenced,
    resync_payload,
    run_end_payload,
    run_started_payload,
)


def test_extract_payload_strips_the_data_prefix_and_frame_terminator():
    assert extract_payload('data: {"type": "token"}\n\n') == '{"type": "token"}'
    assert extract_payload("data: [DONE]\n\n") == DONE_PAYLOAD


def test_comments_and_blank_frames_carry_no_payload():
    assert extract_payload(": keep-alive\n\n") is None
    assert extract_payload(HEARTBEAT_FRAME) is None
    assert extract_payload("data: \n\n") is None
    assert extract_payload("event: x\n\n") is None


def test_format_event_puts_the_sequence_in_the_sse_id():
    assert format_event(7, '{"a": 1}') == 'id: 7\ndata: {"a": 1}\n\n'
    assert format_unsequenced('{"a": 1}') == 'data: {"a": 1}\n\n'


def test_caught_up_payload_is_a_bare_meta_packet():
    assert json.loads(caught_up_payload()) == {"type": "caught_up"}


def test_meta_payloads_have_the_documented_shape():
    assert json.loads(run_started_payload("r1", "t1")) == {
        "type": "run_started",
        "run_id": "r1",
        "thread_id": "t1",
    }
    assert json.loads(run_end_payload("cancelled", None)) == {
        "type": "run_end",
        "status": "cancelled",
        "error_code": None,
    }
    assert json.loads(resync_payload(12)) == {"type": "resync", "first_available_seq": 12}


def test_error_code_of_reads_only_error_packets():
    assert error_code_of('{"type": "error", "error_code": "provider_http_error"}') == (
        "provider_http_error"
    )
    assert error_code_of('{"type": "error", "content": "boom"}') == "stream_error"
    assert error_code_of('{"type": "token", "content": "error"}') is None
    assert error_code_of("[DONE]") is None
    assert error_code_of('{"type": "error"') is None

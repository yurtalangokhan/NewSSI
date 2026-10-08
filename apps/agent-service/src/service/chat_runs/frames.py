"""SSE framing for chat runs.

The event log stores bare ``data`` payloads; the wire adds ``id: <seq>`` so a
client can resume. Generator comments (``: keep-alive``) are never stored: each
reader emits its own heartbeat while idle.
"""

from __future__ import annotations

import json

DONE_PAYLOAD = "[DONE]"
HEARTBEAT_FRAME = ": keep-alive\n\n"
RUN_STARTED = "run_started"
RUN_END = "run_end"
RESYNC = "resync"
CAUGHT_UP = "caught_up"


def extract_payload(frame: str) -> str | None:
    if not frame.startswith("data:"):
        return None
    payload = frame[5:].strip()
    return payload or None


def format_event(seq: int, payload: str) -> str:
    return f"id: {seq}\ndata: {payload}\n\n"


def format_unsequenced(payload: str) -> str:
    return f"data: {payload}\n\n"


def run_started_payload(run_id: str, thread_id: str) -> str:
    return json.dumps({"type": RUN_STARTED, "run_id": run_id, "thread_id": thread_id})


def run_end_payload(status: str, error_code: str | None) -> str:
    return json.dumps({"type": RUN_END, "status": status, "error_code": error_code})


def resync_payload(first_seq: int) -> str:
    return json.dumps({"type": RESYNC, "first_available_seq": first_seq})


def caught_up_payload() -> str:
    """Marks where a stream stops replaying history and starts following the run live."""
    return json.dumps({"type": CAUGHT_UP})


# Streamed answer content: what a viewer sees being "typed".
_CONTENT_DELTA_TYPES = ('"token"', '"reasoning_delta"', '"flow_stage_output_delta"')


def is_content_delta(payload: str) -> bool:
    if not payload.startswith("{") or not any(kind in payload for kind in _CONTENT_DELTA_TYPES):
        return False
    try:
        packet = json.loads(payload)
    except ValueError:
        return False
    return isinstance(packet, dict) and f'"{packet.get("type")}"' in _CONTENT_DELTA_TYPES


def is_run_end(payload: str) -> bool:
    if not payload.startswith("{") or f'"{RUN_END}"' not in payload:
        return False
    try:
        packet = json.loads(payload)
    except ValueError:
        return False
    return isinstance(packet, dict) and packet.get("type") == RUN_END


def error_code_of(payload: str) -> str | None:
    # Cheap pre-check: token frames dominate and never need a JSON parse here.
    if '"error' not in payload:
        return None
    try:
        packet = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(packet, dict) or packet.get("type") != "error":
        return None
    return str(packet.get("error_code") or "stream_error")

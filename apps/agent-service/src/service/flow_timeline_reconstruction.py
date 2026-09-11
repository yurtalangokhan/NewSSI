"""Replay one persisted ``flow_timelines`` blob into timeline packets.

Read-time counterpart of the live ``flow_stage_*`` SSE packets. Pure — no
graph, no checkpoint access. ``ChatHistoryReconstruction`` calls this when a
FlowAgent run's trailing AI id has a ``flow_timelines`` entry, so a refreshed
page shows the same numbered per-stage timeline and the same single answer
bubble it showed live.
"""

from __future__ import annotations

from typing import Any

from service.WebSearchProgressTracker import replay_packets_for_call


def _packet(obj: dict[str, Any], stage: dict[str, Any], turn_index: int) -> dict[str, Any]:
    return {
        "placement": {
            "turn_index": turn_index,
            "sub_turn_index": None,
            "stage_key": stage["stage_key"],
            "stage_order": stage["order"],
            "iteration": stage["iteration"],
        },
        "obj": obj,
    }


def _legacy_steps(stage: dict[str, Any]) -> list[dict[str, Any]]:
    """The ordered step list a pre-``steps`` blob implies.

    Those blobs only kept per-stage buckets, so the true interleaving is gone;
    reasoning, then output, then tools is the best that can be recovered.
    """
    steps: list[dict[str, Any]] = []
    if stage.get("reasoning_text"):
        steps.append({"kind": "reasoning", "text": stage["reasoning_text"]})
    if stage.get("output_text"):
        steps.append({"kind": "output", "text": stage["output_text"]})
    # Tool entries in those blobs predate the `kind` discriminator.
    steps.extend({**tool, "kind": "tool"} for tool in stage.get("tools") or [])
    return steps


def repair_legacy_tools(
    blob: dict[str, Any], stage_events: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Restore what a pre-``steps`` blob lost about its tool calls, using the
    run's own ``flow_stage_timelines`` event log.

    Those blobs never recorded a web tool's result or end time (the live
    stream routed web tools past the recorder), so their searches replay as
    empty, never-finished rows. The event log kept every call's real
    timestamps and full result text, so the search widget and the true
    durations can be rebuilt from it. Only tools are recoverable: how a
    stage's thinking interleaved with them was never written down, and a run
    has to be replayed to get that back.

    A no-op for blobs that already carry ``steps``.
    """
    stages = blob.get("stages") or []
    if not stage_events or any(s.get("steps") is not None for s in stages):
        return blob

    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in stage_events:
        if not isinstance(event, dict):
            continue
        call_id = event.get("call_id")
        if not isinstance(call_id, str):
            continue
        if event.get("event") == "tool_start":
            if call_id not in calls:
                order.append(call_id)
                calls[call_id] = {
                    "kind": "tool",
                    "tool_name": event.get("tool_name", "tool"),
                    "call_id": call_id,
                    "args": event.get("args"),
                    "started_at": event.get("timestamp"),
                    "ended_at": None,
                    "result_preview": "",
                }
        elif event.get("event") == "tool_end" and call_id in calls:
            entry = calls[call_id]
            # The log repeats each end at every later node boundary; the
            # first one is the real one.
            if entry["ended_at"] is None:
                entry["ended_at"] = event.get("timestamp")
                entry["result_preview"] = event.get("data") or ""

    if not calls:
        return blob

    repaired = {**blob, "stages": [dict(s) for s in stages]}
    for stage in repaired["stages"]:
        started, ended = stage.get("started_at"), stage.get("ended_at")
        own = [
            calls[cid]
            for cid in order
            if isinstance(calls[cid]["started_at"], (int, float))
            and isinstance(started, (int, float))
            and isinstance(ended, (int, float))
            and started <= calls[cid]["started_at"] <= ended
        ]
        if not own:
            continue
        stage["tools"] = [_recovered_tool(tool) for tool in own]
    return repaired


def _recovered_tool(tool: dict[str, Any]) -> dict[str, Any]:
    out = dict(tool)
    packets = replay_packets_for_call(
        tool["tool_name"], tool.get("args"), tool.get("call_id"), tool["result_preview"]
    )
    if packets and any(p.get("documents") for p in packets):
        out["web_packets"] = packets
        out["result_preview"] = ""
    return out


def _tool_packets(step: dict[str, Any], stage: dict[str, Any]) -> list[dict[str, Any]]:
    """One tool call's packets: the search / open-url widget for web tools
    (rebuilt at write time so this matches the live stream exactly), or the
    generic tool row for everything else."""
    # The blob knows exactly which stage owns this step, so the chat-side
    # graph strip can attribute the tool badge to its parent stage by node
    # id rather than guessing from graph position / timing.
    stage_node_id = stage.get("node_id")

    web_packets = step.get("web_packets")
    if web_packets:
        out = [dict(p) for p in web_packets]
        # The widget's opening packets carry the call's start, its closing
        # ones the end, so the strip measures the same duration as live.
        for packet in out[:-1]:
            packet.setdefault("timestamp", step.get("started_at"))
        out[-1].setdefault("timestamp", step.get("ended_at") or step.get("started_at"))
        if stage_node_id:
            for packet in out:
                packet.setdefault("stage_node_id", stage_node_id)
        return out

    return [
        {
            "type": "custom_tool_start",
            "tool_name": step["tool_name"],
            "args": step.get("args"),
            "call_id": step.get("call_id"),
            "timestamp": step.get("started_at"),
            "stage_node_id": stage_node_id,
        },
        {
            "type": "custom_tool_delta",
            "tool_name": step["tool_name"],
            "response_type": "tool_result",
            "data": step.get("result_preview", ""),
            "call_id": step.get("call_id"),
            "timestamp": step.get("ended_at") or step.get("started_at"),
            "stage_node_id": stage_node_id,
        },
    ]


def flow_blob_duration_seconds(blob: dict[str, Any]) -> int | None:
    """Whole-run wall time implied by the blob's stage timestamps, in seconds.

    The live stream stamps the final answer with ``int(time.time() - run_start)``
    (floored to a 1s minimum); the blob keeps no run-level clock, but its stages
    span the same window, so ``last ended_at - first started_at`` reproduces that
    number on reload. ``None`` when no stage carries a usable timestamp pair —
    the header then keeps its "thought for a while" copy, as before.
    """
    stages = blob.get("stages") or []
    starts = [s["started_at"] for s in stages if isinstance(s.get("started_at"), (int, float))]
    ends = [s["ended_at"] for s in stages if isinstance(s.get("ended_at"), (int, float))]
    if not starts or not ends:
        return None
    span_ms = max(ends) - min(starts)
    if span_ms <= 0:
        return None
    return max(1, round(span_ms / 1000))


def emit_flow_timeline_packets(blob: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """Return ``(timeline_packets, final_output_text)``.

    ``timeline_packets`` is an ordered list of ``{"placement", "obj"}`` entries
    — a ``flow_stage_start`` … ``flow_stage_end`` bracket per stage, and inside
    it that stage's steps **in the order they happened**: each thinking block,
    each tool call, and the visible output, carrying the blob's real epoch-ms
    timestamps. ``final_output_text`` is the ``is_final`` stage's
    ``output_text`` (``""`` when none is marked final).
    """
    stages = blob.get("stages") or []
    packets: list[dict[str, Any]] = []
    final_text = ""
    # Each logical step (a thinking block, a tool call, the output) gets its
    # own turn_index so the timeline lays them out sequentially. All-zero would
    # make the frontend read them as parallel steps and open bogus tabs.
    turn = 0
    seen_stage_reasoning_texts: set[str] = set()

    for stage in stages:
        is_final = bool(stage.get("is_final"))
        if is_final:
            final_text = stage.get("output_text") or ""

        # Every stage — the final one included — gets a flow_stage_* bracket so
        # a reloaded page shows the same numbered sections as the live run.
        # The final stage's `is_final_stage` flag keeps the frontend from
        # turning it into a fold — its text becomes the answer bubble below.
        packets.append(
            _packet(
                {
                    "type": "flow_stage_start",
                    "stage_key": stage["stage_key"],
                    "node_id": stage["node_id"],
                    "label": stage["label"],
                    "iteration": stage["iteration"],
                    "stage_order": stage["order"],
                    "is_final_stage": is_final,
                    "timestamp": stage.get("started_at"),
                },
                stage,
                turn,
            )
        )

        steps = stage.get("steps")
        if steps is None:
            steps = _legacy_steps(stage)

        stage_seen_reasoning: set[str] = set()
        for step in steps:
            kind = step.get("kind")
            if kind == "reasoning":
                raw_text = step.get("text", "")
                text_clean = raw_text.strip()
                if not text_clean:
                    continue
                # Skip duplicate reasoning within the same stage
                if text_clean in stage_seen_reasoning:
                    continue
                # Skip reasoning leaked from preceding stages
                if text_clean in seen_stage_reasoning_texts:
                    continue
                stage_seen_reasoning.add(text_clean)

                packets.append(_packet({"type": "reasoning_start"}, stage, turn))
                packets.append(
                    _packet({"type": "reasoning_delta", "reasoning": raw_text}, stage, turn)
                )
                turn += 1
            elif kind == "output":
                # The final stage's text is the answer bubble below the
                # timeline, not a fold inside it.
                if is_final:
                    continue
                packets.append(
                    _packet(
                        {
                            "type": "flow_stage_output_delta",
                            "stage_key": stage["stage_key"],
                            "stage_order": stage["order"],
                            "iteration": stage["iteration"],
                            "content": step["text"],
                        },
                        stage,
                        turn,
                    )
                )
                turn += 1
            elif kind == "tool":
                for obj in _tool_packets(step, stage):
                    packets.append(_packet(obj, stage, turn))
                turn += 1

        packets.append(
            _packet(
                {
                    "type": "flow_stage_end",
                    "stage_key": stage["stage_key"],
                    "status": stage.get("status", "done"),
                    "duration_ms": (stage.get("ended_at") or 0) - (stage.get("started_at") or 0),
                    "timestamp": stage.get("ended_at"),
                },
                stage,
                turn,
            )
        )
        turn += 1
        seen_stage_reasoning_texts.update(stage_seen_reasoning)

    return packets, final_text

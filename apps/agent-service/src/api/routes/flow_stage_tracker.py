"""Live per-stage bookkeeping for a FlowAgent SSE run.

Pure / no I/O so it is unit-tested in isolation. ``AgentsRoute._message_generator``
feeds it every debug task boundary and every message delta; at stream end it
produces the blob persisted into ``thread_metadata["flow_timelines"][ai_id]``,
from which read-time reconstruction replays the identical timeline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from service.WebSearchProgressTracker import is_web_search_tool, replay_packets_for_call

_TEXT_CAP = 8 * 1024
_TOOL_PREVIEW_CAP = 2 * 1024
_MAX_STAGES = 200
# Hits kept per web search, so one long-running research stage cannot bloat
# the thread metadata. The widget shows a handful; the rest are never seen.
_MAX_SEARCH_DOCUMENTS = 10


def _truncate(text: str, cap: int) -> tuple[str, bool]:
    raw = text.encode()
    if len(raw) <= cap:
        return text, False
    return raw[:cap].decode(errors="ignore"), True


def _web_search_packets(
    tool_name: str, args: Any, call_id: str | None, result: str
) -> list[dict[str, Any]] | None:
    """This call's replay packets, capped so one long research stage cannot
    bloat the thread metadata it is stored in."""
    packets = replay_packets_for_call(tool_name, args, call_id, result)
    if packets is None:
        return None
    for packet in packets:
        documents = packet.get("documents")
        if isinstance(documents, list) and len(documents) > _MAX_SEARCH_DOCUMENTS:
            packet["documents"] = documents[:_MAX_SEARCH_DOCUMENTS]
    return packets


@dataclass
class _StageRef:
    node_id: str
    label: str
    order: int
    iteration: int
    key: str


@dataclass
class _StageRecord:
    ref: _StageRef
    started_at: int
    ended_at: int | None = None
    status: str = "running"
    # The stage's steps in the order they actually happened: reasoning
    # blocks, visible output, and tool calls interleaved. A stage that thinks,
    # searches, thinks again and then writes its output must replay in that
    # order after a refresh — bucketing the three kinds separately (what this
    # used to do) reordered every such stage into think → output → tools and
    # welded consecutive thinking blocks into one run-on paragraph.
    steps: list[dict[str, Any]] = field(default_factory=list)
    tool_by_call: dict[str, dict[str, Any]] = field(default_factory=dict)

    def _text_step(self, kind: str, text: str) -> None:
        """Append to the open block of this kind, or open a new one."""
        if self.steps and self.steps[-1]["kind"] == kind:
            self.steps[-1]["parts"].append(text)
        else:
            self.steps.append({"kind": kind, "parts": [text]})

    @property
    def tools(self) -> list[dict[str, Any]]:
        return [s for s in self.steps if s["kind"] == "tool"]

    def joined(self, kind: str) -> str:
        return "".join(part for s in self.steps if s["kind"] == kind for part in s["parts"])


class _LiveStageTracker:
    """Tracks the ordered stages of one FlowAgent run: their iteration index
    (per canvas node, so a loop body's re-entries number 1, 2, 3…), their
    reasoning / visible output / tool activity, and their timing."""

    def __init__(self, final_node_ids: set[str], label_fn: Callable[[str], str]) -> None:
        self._final_node_ids = set(final_node_ids)
        self._label_fn = label_fn
        self._order = 0
        self._iter_by_node: dict[str, int] = {}
        self._records: list[_StageRecord] = []
        # The most recently begun stage. Deliberately NOT cleared by
        # end_stage: the top-level `debug` task_result and the node's own
        # `updates`/`messages` events race, so a stage's trailing reasoning
        # or tool result often lands just after its end. Keeping `current`
        # pointed at that stage until the next begin_stage keeps those
        # packets attributed to the right stage.
        self.current: _StageRef | None = None
        self.stage_open = False

    # -- lifecycle ------------------------------------------------------------
    def begin_stage(self, node_id: str, ts_ms: int) -> _StageRef:
        self._order += 1
        self._iter_by_node[node_id] = self._iter_by_node.get(node_id, 0) + 1
        iteration = self._iter_by_node[node_id]
        ref = _StageRef(
            node_id=node_id,
            label=self._label_fn(node_id),
            order=self._order,
            iteration=iteration,
            key=f"{node_id}#{iteration}",
        )
        self._records.append(_StageRecord(ref=ref, started_at=ts_ms))
        self.current = ref
        self.stage_open = True
        return ref

    def end_stage(self, node_id: str, ts_ms: int, status: str = "done") -> _StageRecord | None:
        # Close the record for `node_id` (usually the current one, but a
        # late task_result for an earlier stage is tolerated).
        rec = None
        if self.current is not None and self.current.node_id == node_id:
            rec = self._records[-1] if self._records else None
        else:
            for candidate in reversed(self._records):
                if candidate.ref.node_id == node_id and candidate.ended_at is None:
                    rec = candidate
                    break
        if rec is None:
            return None
        rec.ended_at = ts_ms
        rec.status = status
        self.stage_open = False
        return rec

    # -- content ------------------------------------------------------------
    def begin_reasoning(self) -> None:
        """A `reasoning_start` was emitted: the deltas that follow open a new
        thinking block. Only needed when a block is already open — otherwise
        the next delta starts one by itself."""
        rec = self._current_record()
        if rec is not None and rec.steps and rec.steps[-1]["kind"] == "reasoning":
            rec.steps.append({"kind": "reasoning", "parts": []})

    def add_reasoning(self, text: str) -> None:
        rec = self._current_record()
        if rec is not None and text:
            rec._text_step("reasoning", text)

    def add_output(self, text: str) -> None:
        rec = self._current_record()
        if rec is not None and text:
            rec._text_step("output", text)

    def add_tool(self, tool_name: str, call_id: str | None, args: Any, ts_ms: int) -> None:
        rec = self._current_record()
        if rec is None:
            return
        entry: dict[str, Any] = {
            "kind": "tool",
            "tool_name": tool_name,
            "call_id": call_id,
            "args": args,
            "started_at": ts_ms,
            "ended_at": None,
            "result_preview": "",
        }
        rec.steps.append(entry)
        if call_id:
            rec.tool_by_call[call_id] = entry

    def add_tool_result(self, call_id: str | None, data: str, ts_ms: int) -> None:
        # A result is matched against the stage that opened the call, not just
        # the running one: a tool started in a stage whose `debug` task_result
        # already landed still reports back afterwards, and closing it on the
        # wrong record would overwrite an unrelated tool's timing.
        rec = self._current_record()
        entry = None
        if call_id:
            for candidate in reversed(self._records):
                if call_id in candidate.tool_by_call:
                    entry = candidate.tool_by_call[call_id]
                    break
        elif rec is not None and rec.tools:
            entry = rec.tools[-1]
        if entry is not None and entry["ended_at"] is None:
            entry["ended_at"] = ts_ms
            entry["result_preview"] = data or ""

    # -- queries ------------------------------------------------------------
    def current_is_known_nonfinal(self) -> bool:
        return self.current is not None and self.current.node_id not in self._final_node_ids

    def resolve_final_stage_key(self) -> str | None:
        for rec in reversed(self._records):
            if rec.joined("output").strip():
                return rec.ref.key
        return None

    # -- serialisation ----------------------------------------------------
    def _serialise_tool(self, tool: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        raw = str(tool.get("result_preview") or "")
        preview, truncated = _truncate(raw, _TOOL_PREVIEW_CAP)
        out = {
            "kind": "tool",
            "tool_name": tool["tool_name"],
            "call_id": tool["call_id"],
            "args": tool["args"],
            "started_at": tool["started_at"],
            "ended_at": tool["ended_at"],
            "result_preview": preview,
        }
        # Web tools render as the search / open-url widget rather than a
        # generic tool row. Their packets are derived from the untruncated
        # result here, at write time, so read-time replay is an exact copy of
        # what the live stream sent instead of a re-parse of a clipped string.
        if is_web_search_tool(tool["tool_name"]):
            packets = _web_search_packets(tool["tool_name"], tool["args"], tool["call_id"], raw)
            if packets is not None:
                out["web_packets"] = packets
                if any(p.get("documents") for p in packets):
                    # The widget renders those hits, never the raw text, so
                    # keeping both would only double the metadata weight.
                    # Anything that yielded no hits keeps its preview instead
                    # — better a plain tool row than a silently empty one.
                    out["result_preview"] = ""
                    truncated = False
        return out, truncated

    def build_blob(self, final_stage_key: str | None) -> dict[str, Any]:
        truncated = len(self._records) > _MAX_STAGES
        stages: list[dict[str, Any]] = []
        seen_stage_reasoning: set[str] = set()
        for rec in self._records[:_MAX_STAGES]:
            steps_out: list[dict[str, Any]] = []
            tools_out: list[dict[str, Any]] = []
            stage_seen_reasoning: set[str] = set()
            stage_reasoning_parts: list[str] = []

            for step in rec.steps:
                if step["kind"] == "tool":
                    tool_out, t_tr = self._serialise_tool(step)
                    truncated = truncated or t_tr
                    tools_out.append(tool_out)
                    steps_out.append(tool_out)
                    continue
                text, s_tr = _truncate("".join(step["parts"]), _TEXT_CAP)
                truncated = truncated or s_tr
                if not text:
                    continue

                if step["kind"] == "reasoning":
                    text_clean = text.strip()
                    if not text_clean:
                        continue
                    if text_clean in stage_seen_reasoning or text_clean in seen_stage_reasoning:
                        continue
                    stage_seen_reasoning.add(text_clean)
                    stage_reasoning_parts.append(text)
                    steps_out.append({"kind": "reasoning", "text": text})
                else:
                    steps_out.append({"kind": step["kind"], "text": text})

            seen_stage_reasoning.update(stage_seen_reasoning)
            reasoning_text, r_tr = _truncate("".join(stage_reasoning_parts), _TEXT_CAP)
            output_text, o_tr = _truncate(rec.joined("output"), _TEXT_CAP)
            truncated = truncated or r_tr or o_tr

            stages.append(
                {
                    "stage_key": rec.ref.key,
                    "node_id": rec.ref.node_id,
                    "label": rec.ref.label,
                    "order": rec.ref.order,
                    "iteration": rec.ref.iteration,
                    "started_at": rec.started_at,
                    "ended_at": rec.ended_at,
                    "status": rec.status,
                    "is_final": rec.ref.key == final_stage_key,
                    # `steps` is what read-time replay uses. The three
                    # aggregate fields below are kept so blobs written before
                    # `steps` existed still replay (in their old, bucketed
                    # order) rather than coming back blank.
                    "steps": steps_out,
                    "reasoning_text": reasoning_text,
                    "output_text": output_text,
                    "tools": tools_out,
                }
            )
        return {"stages": stages, "final_stage_key": final_stage_key, "truncated": truncated}

    # -- internal ------------------------------------------------------------
    def _current_record(self) -> _StageRecord | None:
        if self.current is None or not self._records:
            return None
        return self._records[-1]

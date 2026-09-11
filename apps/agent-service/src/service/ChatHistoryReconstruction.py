"""Reconstructs chat messages/packets from raw LangGraph checkpoint state.

Two entry points:
- `reconstruct_messages` — a single flat message list (one checkpoint's
  full accumulated `messages`), used by `CheckpointBranchService` to probe
  historical checkpoints and by `ChatController` as a fallback when only
  one checkpoint is available.
- `reconstruct_message_tree` — a thread's full checkpoint history (possibly
  branching, e.g. after a retry forks a new checkpoint chain), used by
  `ChatController.get_chat_session` so a retried-away-from response stays
  reachable instead of disappearing once it's no longer the latest
  checkpoint. See .tmp/2026-08-21-retry-checkpoint-branching-design.md.

Both share one per-message state machine (`ReconstructionState` +
`_process_raw_message`) so a message is handled identically whether it
arrives as part of one flat list or as one checkpoint's incremental delta
in a tree walk — this is what keeps `message_id` assignment collision-free
across branches: ids come from one counter, incremented once per distinct
message the whole tree over, never recomputed per branch.
"""

from dataclasses import dataclass, field
from typing import Any

from agents.clarification import is_clarification_tool
from core.logger import get_logger
from service.DocumentProgressTracker import is_document_tool
from service.GeneratedFilePacket import (
    build_generated_file_packet_obj,
    parse_generated_file_payload,
)
from service.reconstruction_helpers import (
    compute_latest_children,
    extract_content,
    reindex_tool_packets,
    strip_think_tags,
)
from service.reconstruction_helpers import (
    extract_content as _extract_content,
)
from service.reconstruction_helpers import (
    extract_reasoning_from_metadata as _extract_reasoning_from_metadata,
)
from service.reconstruction_helpers import (
    extract_visible_and_reasoning as _extract_visible_and_reasoning,
)
from service.reconstruction_helpers import (
    reindex_tool_packets as _reindex_tool_packets,
)
from service.WebSearchProgressTracker import WebSearchProgressTracker, is_web_search_tool

logger = get_logger(__name__)


# =============================================================================
# Reconstruction state — mutated message-by-message, clonable so multiple
# checkpoint-tree children can each inherit an independent copy of their
# parent's state instead of sharing (and corrupting) one instance.
# =============================================================================


@dataclass
class _IdCounter:
    """A monotonic message_id allocator, shared by reference (never copied)
    across every clone of a `ReconstructionState`. This is what keeps ids
    collision-free across branches: two siblings cloned from the same
    parent state still draw from the SAME counter, so whichever is walked
    first claims the lower id — they can never independently land on the
    same number the way two separately-owned counters would. Deliberately
    NOT used as a parent pointer (see `ReconstructionState.last_message_id`
    for that) — a shared counter's current value reflects whichever branch
    was processed most recently, not "where this specific branch left off".
    """

    value: int = 0

    def next_id(self) -> int:
        self.value += 1
        return self.value


@dataclass
class ReconstructionState:
    pending_tool_packets: list[dict[str, Any]] = field(default_factory=list)
    # tool_call_id -> index of that call's `custom_tool_start` in
    # pending_tool_packets, so its `custom_tool_delta` can be inserted right
    # after it instead of landing wherever the ToolMessage happened to
    # arrive (a batch of parallel calls appends all of its starts before
    # any of their results come back).
    open_tool_call_positions: dict[str, int] = field(default_factory=dict)
    # tool_call_id -> that `ask_user` call's raw args. The questions live on
    # the AI message and the answers on the ToolMessage, and the card needs
    # both, so the call is parked here until its result arrives.
    open_clarification_args: dict[str, Any] = field(default_factory=dict)
    web_search_progress: WebSearchProgressTracker = field(default_factory=WebSearchProgressTracker)
    pending_ltm_recalled_from_system: int = 0
    pending_ltm_recalled_from_user: int = 0
    ids: _IdCounter = field(default_factory=_IdCounter)
    # The id of the most recently added message in THIS branch's own
    # lineage — i.e. the parent pointer for whatever message comes next
    # here. Per-branch (cloned normally, NOT shared like `ids`): two
    # siblings forked from the same parent must both point new messages
    # at that shared parent, regardless of how far the global `ids`
    # counter has since moved due to a sibling being walked first.
    last_message_id: int | None = None
    # Per-message persona_id/model (set on the human message that triggered
    # a turn) take priority over thread-level metadata, which only ever
    # reflects the most recently sent value and goes stale the moment a
    # later turn switches agent/model (e.g. via retry). Seeded from thread
    # metadata so messages predating this tracking still resolve correctly.
    current_persona_id: Any = None
    current_model: str | None = None
    # Legacy support: a retry recorded under the OLD mechanism (before
    # true checkpoint branching) resends the user's message as a brand new
    # HumanMessage flagged is_regenerate=True, inline in the SAME flat
    # checkpoint. That duplicate must not surface as its own turn; the
    # response that follows it becomes a sibling of the previous response
    # under the ORIGINAL user message instead of a new sequential child.
    # last_real_user_msg_id tracks that original parent; pending_parent_override
    # carries it forward to the next response exactly once. New (post
    # checkpoint-branching) retries never produce this shape — each branch
    # is walked with its own state, so no override is ever needed for them.
    last_real_user_msg_id: int | None = None
    pending_parent_override: int | None = None
    # Per-thread lookup: LangChain AI-message id -> that turn's ordered flow
    # stage start/end events (persisted by AgentsRoute after a FlowAgent run,
    # since graph_stage_* SSE events are otherwise live-only and vanish on
    # refresh). Read-only; shared by reference across every clone like
    # `ids`, never mutated here.
    flow_stage_timelines: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Per-thread lookup: LangChain AI-message id -> that run's structured
    # per-stage timeline blob (AgentsRoute._persist_run_timeline). When a
    # run's trailing visible-AI id is a key here, the run is rebuilt from the
    # blob (emit_flow_timeline_packets) — numbered per-stage timeline groups
    # + one final answer bubble — instead of the _compute_flow_run_layout
    # heuristic. Read-only, shared by reference like `flow_stage_timelines`.
    flow_timelines: dict[str, Any] = field(default_factory=dict)
    # Per-thread lookup: LangChain AI-message id -> the published flow
    # version_no that run executed (AgentsRoute._persist_flow_stage_timeline).
    # Replayed as a `flow_version` packet on the run's turn so the chat-side
    # flow strip pins to the version that ran, not the current published one.
    # Read-only, shared by reference like the two tables above.
    flow_versions: dict[str, int] = field(default_factory=dict)
    # Set by reconstruct_message_tree while it processes a checkpoint delta
    # that belongs to a NON-terminal stage of a multi-stage FlowAgent run
    # (there is a later stage in the same run that produces the visible
    # answer). Its plain AI text then folds into the terminal turn's
    # collapsible reasoning region instead of opening its own chat bubble;
    # its tool activity still buffers and attaches to that one turn. False
    # everywhere else — the flat path and every non-flow reconstruction.
    flow_fold_stage: bool = False
    # Companion to flow_fold_stage: the current checkpoint delta is a
    # *final-answer* stage of the same run (no later stage calls a tool).
    # The first such delta opens the turn; later ones append their text to
    # it instead of opening sibling bubbles, so the answer stays whole.
    flow_answer_member: bool = False
    # True once a flow-run answer turn has been opened and no HumanMessage
    # has been seen since — the signal that the next answer-member delta
    # should append rather than open a new bubble.
    flow_answer_turn_open: bool = False
    # Set by reconstruct_message_tree for a checkpoint that is a non-terminal
    # member of a blob-backed FlowAgent run: its AI/tool messages produce
    # nothing (the blob, replayed on the terminal checkpoint, is the sole
    # source of that run's timeline + answer).
    flow_blob_skip: bool = False
    # Set for the terminal checkpoint of a blob-backed run: its closing
    # visible AI message triggers a full replay of the run's flow_timelines
    # blob (numbered per-stage groups + one final answer bubble).
    flow_blob_active: bool = False
    # Generated-file cards pulled out of a blob-backed run's folded stages.
    # The blob keeps only a truncated `result_preview` of a document tool's
    # output, so the payload has to be carried here and re-emitted on the
    # run's turn or the file is lost on reload. Kept apart from
    # pending_tool_packets, which the blob replay deliberately clears.
    pending_blob_generated_files: list[dict[str, Any]] = field(default_factory=list)
    # True once a HumanMessage stamped with ``persona_id`` has been walked past.
    # From that point on the *absence* of the stamp is evidence a flow node
    # emitted the message. Tracked as we go rather than precomputed for the
    # whole thread so a thread that straddles the introduction of stamping
    # keeps rendering its older, unstamped user messages.
    seen_persona_stamp: bool = False
    # True between rendering a user bubble and the next AI message. A second
    # HumanMessage arriving inside that window did not come from the user: a
    # flow node emitted it (Prompt Template / Text Input render their text as
    # a message so it can feed an agent). See _is_flow_internal_human.
    user_turn_open: bool = False

    def clone(self) -> "ReconstructionState":
        return ReconstructionState(
            pending_tool_packets=list(self.pending_tool_packets),
            open_tool_call_positions=dict(self.open_tool_call_positions),
            # An `ask_user` call and its answer land in DIFFERENT checkpoints
            # (`model` then `clarify`), so the parked question args have to
            # survive the per-checkpoint clone or the answered card is lost on
            # a tree-walk reload.
            open_clarification_args=dict(self.open_clarification_args),
            web_search_progress=self.web_search_progress.clone(),
            pending_ltm_recalled_from_system=self.pending_ltm_recalled_from_system,
            pending_ltm_recalled_from_user=self.pending_ltm_recalled_from_user,
            ids=self.ids,  # shared reference, deliberately not copied — see _IdCounter
            last_message_id=self.last_message_id,
            current_persona_id=self.current_persona_id,
            current_model=self.current_model,
            last_real_user_msg_id=self.last_real_user_msg_id,
            pending_parent_override=self.pending_parent_override,
            flow_stage_timelines=self.flow_stage_timelines,  # shared read-only table
            flow_timelines=self.flow_timelines,  # shared read-only table
            flow_versions=self.flow_versions,  # shared read-only table
            flow_fold_stage=self.flow_fold_stage,
            flow_answer_member=self.flow_answer_member,
            flow_answer_turn_open=self.flow_answer_turn_open,
            pending_blob_generated_files=list(self.pending_blob_generated_files),
            flow_blob_skip=self.flow_blob_skip,
            flow_blob_active=self.flow_blob_active,
            seen_persona_stamp=self.seen_persona_stamp,
            user_turn_open=self.user_turn_open,
        )


def _is_flow_internal_human(raw_msg: Any, state: "ReconstructionState") -> bool:
    """Whether this HumanMessage was emitted by a flow node, not sent by the user.

    Since Phase 1 a ``Prompt Template`` (and ``Text Input``) writes its rendered
    text into ``messages`` so it can feed a downstream agent — Langflow passes
    that value along the edge, but our agents read the shared message channel.
    On reload it would otherwise render as a second user bubble containing the
    internal prompt.

    Two signals must both hold, so nothing that a user actually typed is ever
    hidden:

    - ``AgentHelpers`` stamps every message it builds from a real send with
      ``additional_kwargs["persona_id"]``; a node-emitted message has none;
    - a user turn is already open with no assistant answer since. The first
      human message of a run therefore always renders, including on threads
      that predate persona_id stamping.

    Read-time only, deliberately: attributing messages inside the compiled
    graph was tried twice and broke real runs (see the flow single-turn notes).
    """
    if _human_is_persona_stamped(raw_msg):
        return False
    # On a stamped thread the missing stamp settles it on its own. Requiring an
    # open user turn as well used to be the second signal, but a Loop emits one
    # HumanMessage per item and the body answers between them: only item 1
    # arrived while the turn was open, so items 2..N leaked as bubbles the user
    # never sent. Keep that weaker rule only where the stamp cannot be trusted.
    return state.seen_persona_stamp or state.user_turn_open


def _human_is_persona_stamped(raw_msg: Any) -> bool:
    """Whether a human message carries AgentHelpers' ``persona_id`` marker —
    the one signal that positively identifies a real user send."""
    if isinstance(raw_msg, dict):
        extra = raw_msg.get("additional_kwargs", {}) or {}
    else:
        extra = getattr(raw_msg, "additional_kwargs", {}) or {}
    return "persona_id" in extra


def _thread_has_persona_stamp(checkpoints: list[dict[str, Any]]) -> bool:
    """Whether any human message anywhere in the thread carries the stamp."""
    for checkpoint in checkpoints:
        for raw_msg in checkpoint.get("messages", []):
            if _raw_message_type(raw_msg) in ("human", "user") and _human_is_persona_stamped(
                raw_msg
            ):
                return True
    return False


def _raw_message_id(raw_msg: Any) -> str | None:
    """The LangChain id of a raw checkpoint message, dict or object form."""
    raw_id = getattr(raw_msg, "id", None)
    if raw_id is None and isinstance(raw_msg, dict):
        raw_id = raw_msg.get("id")
    return raw_id if isinstance(raw_id, str) and raw_id else None


def _flow_version_packet(version_no: int) -> dict[str, Any]:
    """Run-level metadata packet mirroring AgentsRoute's live `flow_version`
    SSE frame: it pins the chat flow strip to the version that ran. Carries
    no stage_key, so it stays out of per-stage grouping on the client."""
    return {
        "placement": {"turn_index": 0, "sub_turn_index": None},
        "obj": {"type": "flow_version", "version_no": version_no},
    }


def _stage_timeline_packets(
    events: list[dict[str, Any]],
    known_tool_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Replay persisted flow stage start/end events and tool invocations as
    chronological packets carrying real epoch-ms `timestamp`s, so GraphStageStrip
    shows accurate per-stage and per-tool durations and placements after a
    refresh instead of losing tool calls or collapsing durations."""
    if not events:
        return []

    # Check if events already carry explicit tool_start / tool_end
    has_tools = any(
        e.get("event") in ("tool_start", "tool_end") for e in events if isinstance(e, dict)
    )

    processed_events = events
    if not has_tools and any(e.get("stage_name") == "model" for e in events if isinstance(e, dict)):
        # Backwards compatibility for legacy flow timelines: synthesize tool events from model gaps
        enriched: list[dict[str, Any]] = []
        current_stage: str | None = None
        last_model_end: int | float | None = None
        tool_idx = 0
        known_tools = list(known_tool_names or [])

        for ev in events:
            if not isinstance(ev, dict):
                continue
            name = ev.get("stage_name")
            kind = ev.get("event")
            ts = ev.get("timestamp")
            if name not in ("model", "__start__", "__end__", "tools"):
                if kind == "start":
                    current_stage = name
                    last_model_end = None
                    enriched.append(ev)
                elif kind == "end":
                    enriched.append(ev)
                    current_stage = None
                    last_model_end = None
            else:
                if kind == "end":
                    last_model_end = ts
                elif kind == "start" and last_model_end is not None:
                    gap_duration = (
                        (ts - last_model_end)
                        if isinstance(ts, (int, float)) and isinstance(last_model_end, (int, float))
                        else 0
                    )
                    if gap_duration > 100 and current_stage:
                        if tool_idx < len(known_tools):
                            tool_name = known_tools[tool_idx]
                            tool_idx += 1
                        else:
                            tool_name = (
                                "web_search"
                                if "research" in current_stage.lower()
                                else (
                                    "run_python"
                                    if "analysis" in current_stage.lower()
                                    or "react" in current_stage.lower()
                                    or "kod" in current_stage.lower()
                                    else "tool"
                                )
                            )
                        enriched.append(
                            {
                                "event": "tool_start",
                                "tool_name": tool_name,
                                "timestamp": last_model_end,
                            }
                        )
                        enriched.append(
                            {
                                "event": "tool_end",
                                "tool_name": tool_name,
                                "timestamp": ts,
                            }
                        )
                    last_model_end = None
        processed_events = enriched

    replayed: list[dict[str, Any]] = []
    _NON_GRAPH_NODES = ("model", "__start__", "__end__", "tools")
    # Runs recorded before tool results were deduplicated on the write side
    # have every finished tool re-reported at each later node boundary. Left
    # in, those repeats stretch a tool's duration to the end of a stage that
    # never called it and hang phantom tool badges off that stage. Only the
    # first end for a call is real.
    ended_call_ids: set[str] = set()

    for event in processed_events or []:
        if not isinstance(event, dict):
            continue
        kind = event.get("event")
        timestamp = event.get("timestamp")

        if kind == "tool_end":
            call_id = event.get("call_id")
            if isinstance(call_id, str):
                if call_id in ended_call_ids:
                    continue
                ended_call_ids.add(call_id)

        if kind in ("start", "end"):
            stage_name = event.get("stage_name")
            if not isinstance(stage_name, str) or stage_name in _NON_GRAPH_NODES:
                continue
            obj: dict[str, Any] = {
                "type": "graph_stage_start" if kind == "start" else "graph_stage_end",
                "stage_name": stage_name,
            }
            if isinstance(timestamp, (int, float)):
                obj["timestamp"] = timestamp
            replayed.append({"placement": {"turn_index": 0, "sub_turn_index": None}, "obj": obj})
        elif kind == "tool_start":
            tool_name = event.get("tool_name", "tool")
            obj = {
                "type": "custom_tool_start",
                "tool_name": tool_name,
                "args": event.get("args"),
                "call_id": event.get("call_id"),
            }
            stage_node_id = event.get("stage_node_id")
            if isinstance(stage_node_id, str):
                obj["stage_node_id"] = stage_node_id
            if isinstance(timestamp, (int, float)):
                obj["timestamp"] = timestamp
            replayed.append({"placement": {"turn_index": 0, "sub_turn_index": None}, "obj": obj})
        elif kind == "tool_end":
            tool_name = event.get("tool_name", "tool")
            obj = {
                "type": "custom_tool_delta",
                "tool_name": tool_name,
                "response_type": "tool_result",
                "data": event.get("data", ""),
                "call_id": event.get("call_id"),
            }
            stage_node_id = event.get("stage_node_id")
            if isinstance(stage_node_id, str):
                obj["stage_node_id"] = stage_node_id
            if isinstance(timestamp, (int, float)):
                obj["timestamp"] = timestamp
            replayed.append({"placement": {"turn_index": 0, "sub_turn_index": None}, "obj": obj})
    return replayed


def _emit_clarification_packets(
    raw_msg: Any,
    state: ReconstructionState,
    tool_call_id: str | None,
) -> None:
    """An answered `ask_user` call, redrawn as the card the user answered.

    Nothing here parses text. The questions come from the AI message's
    `tool_call.args` and the answers from `ToolMessage.artifact` — both are
    the checkpoint's own structured data (design 3.5). A design that read the
    tool's prose instead would break silently the first day the model worded
    it differently.
    """
    from agents.clarification.packets import packets_for_history

    args = state.open_clarification_args.pop(tool_call_id, None) if tool_call_id else None
    artifact = getattr(raw_msg, "artifact", None) or (
        raw_msg.get("artifact") if isinstance(raw_msg, dict) else None
    )
    packets = packets_for_history(tool_call_id or "", args, artifact)
    if not packets:
        return
    for packet in packets:
        state.pending_tool_packets.append(
            {"placement": {"turn_index": 0, "sub_turn_index": None}, "obj": packet}
        )


def _process_tool_message(
    raw_msg: Any,
    state: ReconstructionState,
    messages: list[dict[str, Any]],
    packets_2d: list[list[dict[str, Any]]],
    chat_session_id: str,
) -> None:
    """A ToolMessage: its result becomes a timeline packet on the turn it
    belongs to, not the turn LangGraph re-delivered it on."""
    tool_name = (
        getattr(raw_msg, "name", None)
        or (raw_msg.get("name", "") if isinstance(raw_msg, dict) else "")
        or "tool"
    )
    tool_call_id = getattr(raw_msg, "tool_call_id", None) or (
        raw_msg.get("tool_call_id") if isinstance(raw_msg, dict) else None
    )
    if is_clarification_tool(tool_name):
        _emit_clarification_packets(raw_msg, state, tool_call_id)
        return
    tool_content = _extract_content(raw_msg)
    generated_file = parse_generated_file_payload(tool_content)
    # Document tools are represented by their generated_file card
    # alone — same as the live stream, which replaces their timeline
    # step with the document_generation_* packets.
    web_search_packets = (
        state.web_search_progress.on_tool_result(tool_name, tool_content, tool_call_id)
        if generated_file is None and is_web_search_tool(tool_name)
        else None
    )
    if generated_file is None and web_search_packets is None:
        delta_packet = {
            "placement": {"turn_index": 0, "sub_turn_index": None},
            "obj": {
                "type": "custom_tool_delta",
                "tool_name": tool_name,
                "response_type": "tool_result",
                "data": tool_content,
            },
        }
        if tool_call_id and tool_call_id in state.open_tool_call_positions:
            insert_pos = state.open_tool_call_positions.pop(tool_call_id) + 1
            state.pending_tool_packets.insert(insert_pos, delta_packet)
            for call_id, pos in state.open_tool_call_positions.items():
                if pos >= insert_pos:
                    state.open_tool_call_positions[call_id] = pos + 1
        else:
            state.pending_tool_packets.append(delta_packet)
    if web_search_packets is not None:
        delta_packets = [
            {"placement": {"turn_index": 0, "sub_turn_index": None}, "obj": packet}
            for packet in web_search_packets
        ]
        if tool_call_id and tool_call_id in state.open_tool_call_positions:
            insert_pos = state.open_tool_call_positions.pop(tool_call_id) + 1
            state.pending_tool_packets[insert_pos:insert_pos] = delta_packets
            shift = len(delta_packets)
            for call_id, pos in state.open_tool_call_positions.items():
                if pos >= insert_pos:
                    state.open_tool_call_positions[call_id] = pos + shift
        else:
            state.pending_tool_packets.extend(delta_packets)
    if generated_file is not None:
        state.pending_tool_packets.append(
            {
                "placement": {"turn_index": 0, "sub_turn_index": None},
                "obj": build_generated_file_packet_obj(generated_file),
            }
        )
    return


def _process_system_message(
    raw_msg: Any,
    state: ReconstructionState,
    messages: list[dict[str, Any]],
    packets_2d: list[list[dict[str, Any]]],
    chat_session_id: str,
) -> None:
    """A SystemMessage: never rendered, but it can carry run-level state."""
    system_text = _extract_content(raw_msg)
    if "[Long-Term Memory — Previously learned facts about this user]" in system_text:
        facts = [line for line in system_text.splitlines() if line.strip().startswith("- ")]
        if facts:
            state.pending_ltm_recalled_from_system = len(facts)
    return


def _append_flow_version_packet(
    raw_msg: Any,
    state: ReconstructionState,
    turn_packets: list[dict[str, Any]],
) -> None:
    """Pin the flow strip to the version this run actually executed.

    Persisted by the stream service, keyed by the AI message's LangChain id,
    and emitted ahead of the stage strip so it is the first thing the client
    sees for the turn.
    """
    _flow_version_no = (
        state.flow_versions.get(_raw_message_id(raw_msg)) if state.flow_versions else None
    )
    if _flow_version_no is not None:
        turn_packets.append(_flow_version_packet(_flow_version_no))


def _append_stage_strip_packets(
    raw_msg: Any,
    state: ReconstructionState,
    messages: list[dict[str, Any]],
    turn_packets: list[dict[str, Any]],
) -> None:
    """Replay this turn's persisted graph_stage_* events.

    Absent for non-flow turns and for flow turns that predate the tracking.
    When the strip already carries the run's tool activity, the live-path
    copies buffered in ``pending_tool_packets`` are dropped so a badge is not
    shown twice.
    """
    _stage_events = (
        state.flow_stage_timelines.get(_raw_message_id(raw_msg))
        if state.flow_stage_timelines
        else None
    )
    if _stage_events:
        turn_packets.extend(
            _stage_timeline_packets(
                _stage_events,
                known_tool_names=[
                    tc.get("name")
                    for m in (messages or [])
                    for tc in _msg_tool_calls(m)
                    if isinstance(tc, dict)
                    and tc.get("name")
                    and not is_document_tool(tc.get("name"))
                ],
            )
        )
        has_replayed_tools = any(
            e.get("event") in ("tool_start", "tool_end") for e in _stage_events
        ) or any(e.get("stage_name") == "model" for e in _stage_events)
        if has_replayed_tools:
            state.pending_tool_packets = [
                p
                for p in state.pending_tool_packets
                if p.get("obj", {}).get("type") not in ("custom_tool_start", "custom_tool_delta")
                and not str(p.get("obj", {}).get("type", "")).startswith("search_tool_")
            ]


def _append_ltm_packets(
    state: ReconstructionState,
    extra: dict[str, Any],
    turn_packets: list[dict[str, Any]],
    turn_counter: int,
    new_id: int,
) -> int:
    """Emit the long-term-memory recall packet, returning the next turn index.

    Placed before the tool packets to match the streaming order, where recall
    is reported before the agent starts calling tools.
    """
    _extra = extra
    ltm_recalled = _extra.get("_ltm_recalled", 0)
    if not ltm_recalled and state.pending_ltm_recalled_from_system:
        ltm_recalled = state.pending_ltm_recalled_from_system
    if not ltm_recalled and state.pending_ltm_recalled_from_user:
        ltm_recalled = state.pending_ltm_recalled_from_user
    state.pending_ltm_recalled_from_system = 0
    state.pending_ltm_recalled_from_user = 0
    if ltm_recalled:
        ltm_memories = _extra.get("_ltm_memories", [])
        logger.debug(
            "[LTM-history] ai msg %d: extra_keys=%s ltm_recalled=%s",
            new_id,
            list(_extra.keys()),
            ltm_recalled,
        )
        turn_packets.append(
            {
                "placement": {"turn_index": turn_counter, "sub_turn_index": None},
                "obj": {
                    "type": "long_term_memory_recall",
                    "fact_count": ltm_recalled,
                    "memories": ltm_memories,
                },
            }
        )
        turn_counter += 1
    return turn_counter


def _append_buffered_tool_packets(
    state: ReconstructionState,
    turn_packets: list[dict[str, Any]],
    turn_counter: int,
) -> int:
    """Flush the tool packets buffered while the model was mid-turn."""
    if state.pending_tool_packets:
        reindexed_tools, next_turn = _reindex_tool_packets(
            state.pending_tool_packets,
            turn_counter,
        )
        turn_packets.extend(reindexed_tools)
        state.pending_tool_packets = []
        state.open_tool_call_positions = {}
        state.open_clarification_args = {}
        turn_counter = next_turn
    return turn_counter


def _append_reasoning_packets(
    reasoning_text: str,
    turn_packets: list[dict[str, Any]],
    turn_counter: int,
) -> int:
    """Emit the turn's collapsible reasoning block."""
    if reasoning_text:
        turn_packets.append(
            {
                "placement": {"turn_index": turn_counter, "sub_turn_index": None},
                "obj": {"type": "reasoning_start"},
            }
        )
        turn_packets.append(
            {
                "placement": {"turn_index": turn_counter, "sub_turn_index": None},
                "obj": {
                    "type": "reasoning_delta",
                    "reasoning": reasoning_text,
                },
            }
        )
        turn_counter += 1
    return turn_counter


def _buffer_tool_call_turn(
    raw_msg: Any,
    state: ReconstructionState,
    tool_calls: list[Any],
    msg_content: str,
    reasoning_text: str,
) -> None:
    """Buffer an AI message that called tools instead of answering.

    Nothing is emitted yet: the packets wait in ``pending_tool_packets`` until
    the turn's real answer arrives, so a model that reasons, calls tools and
    then answers renders as one bubble rather than three.
    """
    # Preserve intermediate reasoning emitted before this tool call
    if reasoning_text:
        state.pending_tool_packets.append(
            {
                "placement": {"turn_index": 0, "sub_turn_index": None},
                "obj": {"type": "reasoning_start"},
            }
        )
        state.pending_tool_packets.append(
            {
                "placement": {"turn_index": 0, "sub_turn_index": None},
                "obj": {"type": "reasoning_delta", "reasoning": reasoning_text},
            }
        )
    # A model often writes a sentence before calling its tools
    # ("let me look at these pages"). That text streams live as
    # part of the answer, so dropping it here made a reloaded
    # conversation start abruptly at the tool results instead.
    if msg_content:
        state.pending_tool_packets.append(
            {
                "placement": {"turn_index": 0, "sub_turn_index": None},
                "obj": {
                    "type": "message_start",
                    "content": msg_content,
                    "final_documents": None,
                },
            }
        )
    for tool_call in tool_calls:
        tool_name = (
            tool_call.get("name", "tool")
            if isinstance(tool_call, dict)
            else getattr(tool_call, "name", "tool")
        )
        tool_args = (
            tool_call.get("args")
            if isinstance(tool_call, dict)
            else getattr(tool_call, "args", None)
        )
        call_id = (
            tool_call.get("id") if isinstance(tool_call, dict) else getattr(tool_call, "id", None)
        )
        # A document tool is shown by its generated_file card
        # alone, exactly as the live stream does it. Adding a
        # generic tool step here made a reloaded conversation grow
        # an extra timeline entry the user never saw while it was
        # streaming.
        if is_document_tool(tool_name):
            continue
        # An `ask_user` call draws NOTHING here. Its card is emitted with the
        # ToolMessage instead, which is what makes the two cases come out
        # right with one rule: an ANSWERED call draws the card plus its lock
        # (E5), and an UNANSWERED one draws nothing at all — the run is still
        # paused, so the live card comes from the pending interrupt, and
        # drawing a second one here would show the same question twice (E4).
        if is_clarification_tool(tool_name):
            if call_id:
                state.open_clarification_args[call_id] = tool_args
            continue
        web_search_packets = (
            state.web_search_progress.on_tool_call(tool_name, tool_args, call_id)
            if is_web_search_tool(tool_name)
            else None
        )
        if web_search_packets is not None:
            for packet in web_search_packets:
                state.pending_tool_packets.append(
                    {
                        "placement": {"turn_index": 0, "sub_turn_index": None},
                        "obj": packet,
                    }
                )
            if call_id:
                # Point at the LAST of this call's packets, so a
                # later result is inserted right after both instead
                # of wedging between them.
                state.open_tool_call_positions[call_id] = len(state.pending_tool_packets) - 1
            continue
        state.pending_tool_packets.append(
            {
                "placement": {"turn_index": 0, "sub_turn_index": None},
                "obj": {
                    "type": "custom_tool_start",
                    "tool_name": tool_name,
                    "args": tool_args,
                },
            }
        )
        if call_id:
            state.open_tool_call_positions[call_id] = len(state.pending_tool_packets) - 1


def _fold_stage_into_reasoning(
    state: ReconstructionState,
    msg_content: str,
    reasoning_text: str,
) -> None:
    """Fold a non-terminal FlowAgent stage into the terminal turn's reasoning.

    Such a stage produced text but is not the run's answer, so it belongs in
    the collapsible region rather than opening a bubble of its own. Its tool
    activity is already buffered and attaches to the same turn.
    """
    # Non-terminal stage of a multi-stage FlowAgent run: its plain
    # text folds into the terminal turn's collapsible reasoning
    # region rather than opening a bubble. Its tool activity has
    # already buffered in `pending_tool_packets` (handled above /
    # in the tool branch) and attaches to that same one turn.
    note = "\n\n".join(t for t in (reasoning_text, msg_content) if t)
    if note:
        state.pending_tool_packets.append(
            {
                "placement": {"turn_index": 0, "sub_turn_index": None},
                "obj": {"type": "reasoning_start"},
            }
        )
        state.pending_tool_packets.append(
            {
                "placement": {"turn_index": 0, "sub_turn_index": None},
                "obj": {"type": "reasoning_delta", "reasoning": note},
            }
        )


def _emit_blob_backed_ai_turn(
    raw_msg: Any,
    state: ReconstructionState,
    messages: list[dict[str, Any]],
    packets_2d: list[list[dict[str, Any]]],
    chat_session_id: str,
    tool_calls: list[Any],
) -> bool:
    """Replay a FlowAgent run from its persisted blob instead of its messages.

    Returns True when the blob owned this turn's narration, in which case the
    caller must not also render the message.
    """

    _flow_blob = (
        state.flow_timelines.get(_raw_message_id(raw_msg))
        if state.flow_blob_active and state.flow_timelines and not tool_calls
        else None
    )
    if _flow_blob:
        _blob_extra = (
            raw_msg.get("additional_kwargs", {}) or {}
            if isinstance(raw_msg, dict)
            else getattr(raw_msg, "additional_kwargs", {}) or {}
        )
        _persisted_dur = _blob_extra.get("processing_duration_seconds")
        _emit_flow_blob_turn(
            state,
            _flow_blob,
            messages,
            packets_2d,
            chat_session_id,
            flow_version_no=(
                state.flow_versions.get(_raw_message_id(raw_msg)) if state.flow_versions else None
            ),
            stage_events=(
                state.flow_stage_timelines.get(_raw_message_id(raw_msg))
                if state.flow_stage_timelines
                else None
            ),
            processing_duration_seconds=(
                int(_persisted_dur) if isinstance(_persisted_dur, (int, float)) else None
            ),
        )
        return True
    return False


def _merge_into_open_flow_answer(
    raw_msg: Any,
    state: ReconstructionState,
    messages: list[dict[str, Any]],
    packets_2d: list[list[dict[str, Any]]],
    msg_content: str,
) -> bool:
    """Append a later final-answer stage to the bubble the first stage opened.

    A flow can split one answer across stages (a summary, then a references
    footer). Returns True when the text was merged, so the caller does not
    open a second bubble for it.
    """
    if (
        state.flow_answer_member
        and state.flow_answer_turn_open
        and messages
        and messages[-1]["message_type"] == "assistant"
        and packets_2d
    ):
        # A later final-answer stage of the same flow run: the model
        # split its answer across stages (e.g. calc summary, then a
        # references footer). Append to the turn the first stage opened
        # so the answer stays one bubble.
        prev = messages[-1]
        prev["message"] = (
            (prev["message"] + "\n\n" + msg_content).strip() if prev["message"] else msg_content
        )
        turn = packets_2d[-1]
        for pkt in reversed(turn):
            if pkt["obj"].get("type") == "message_start":
                pkt["obj"]["content"] = prev["message"]
                break
        # The flow stage strip is keyed to the run's LAST message id,
        # which may be an appended stage rather than the one that opened
        # the turn — replay it here so the one turn still gets its strip.
        _strip = (
            state.flow_stage_timelines.get(_raw_message_id(raw_msg))
            if state.flow_stage_timelines
            else None
        )
        if _strip and not any(p["obj"].get("type") == "graph_stage_start" for p in turn):
            replayed_strip = _stage_timeline_packets(
                _strip,
                known_tool_names=[
                    tc.get("name")
                    for m in (messages or [])
                    for tc in _msg_tool_calls(m)
                    if isinstance(tc, dict)
                    and tc.get("name")
                    and not is_document_tool(tc.get("name"))
                ],
            )
            has_strip_tools = any(
                p["obj"].get("type") in ("custom_tool_start", "custom_tool_delta")
                for p in replayed_strip
            )
            if has_strip_tools:
                turn[:] = [
                    p
                    for p in turn
                    if not str(p.get("obj", {}).get("type", "")).startswith("search_tool_")
                    and p.get("obj", {}).get("type")
                    not in ("custom_tool_start", "custom_tool_delta")
                ]
            turn[:0] = replayed_strip
        return True
    return False


def _process_ai_message(
    raw_msg: Any,
    state: ReconstructionState,
    messages: list[dict[str, Any]],
    packets_2d: list[list[dict[str, Any]]],
    chat_session_id: str,
) -> None:
    """An AIMessage: the answer bubble, its reasoning, its tool badges and,
    for a FlowAgent, its stage grouping."""
    # The assistant answered, so the user's turn is closed: a later human
    # message is a real new turn again, not a flow node's own message.
    state.user_turn_open = False
    tool_calls = getattr(raw_msg, "tool_calls", None) or (
        raw_msg.get("tool_calls", []) if isinstance(raw_msg, dict) else []
    )
    msg_content, reasoning_text = _extract_visible_and_reasoning(raw_msg)
    if not reasoning_text:
        reasoning_text = _extract_reasoning_from_metadata(raw_msg)
    if _emit_blob_backed_ai_turn(raw_msg, state, messages, packets_2d, chat_session_id, tool_calls):
        return

    if tool_calls:
        _buffer_tool_call_turn(raw_msg, state, tool_calls, msg_content, reasoning_text)
        return

    if state.flow_fold_stage:
        _fold_stage_into_reasoning(state, msg_content, reasoning_text)
        return

    if not msg_content:
        # A turn that ends here with no visible text (e.g. the model's
        # only action was calling a document tool, so the graph's
        # closing AI message is empty) still completed real, visible
        # work — any packets already buffered for it (e.g. a generated
        # file card) must become their own turn now. Otherwise they sit
        # in `pending_tool_packets` and silently get swept into
        # whichever LATER message happens to flush them, merging two
        # unrelated turns into one chat bubble.
        _flush_trailing_tool_packets(state, messages, packets_2d, chat_session_id)
        return

    if _merge_into_open_flow_answer(raw_msg, state, messages, packets_2d, msg_content):
        return

    if state.pending_parent_override is not None:
        parent_msg_id = state.pending_parent_override
        state.pending_parent_override = None
    else:
        parent_msg_id = state.last_message_id
    new_id = state.ids.next_id()
    state.last_message_id = new_id

    turn_packets: list[dict[str, Any]] = []
    turn_counter = 0

    _append_flow_version_packet(raw_msg, state, turn_packets)
    _append_stage_strip_packets(raw_msg, state, messages, turn_packets)

    _extra = (
        raw_msg.get("additional_kwargs", {}) or {}
        if isinstance(raw_msg, dict)
        else getattr(raw_msg, "additional_kwargs", {}) or {}
    )
    turn_counter = _append_ltm_packets(state, _extra, turn_packets, turn_counter, new_id)
    turn_counter = _append_buffered_tool_packets(state, turn_packets, turn_counter)
    turn_counter = _append_reasoning_packets(reasoning_text, turn_packets, turn_counter)

    duration_sec = _extra.get("processing_duration_seconds") or _extra.get("duration_seconds")
    if duration_sec is None and reasoning_text:
        duration_sec = max(5, min(300, int(len(reasoning_text) / 25)))
    elif duration_sec is None and turn_packets:
        duration_sec = max(3, len(turn_packets) * 2)

    display_turn = turn_counter
    turn_packets.append(
        {
            "placement": {"turn_index": display_turn, "sub_turn_index": None},
            "obj": {
                "type": "message_start",
                "content": msg_content,
                "final_documents": None,
                "pre_answer_processing_seconds": duration_sec,
            },
        }
    )
    turn_packets.append(
        {
            "placement": {"turn_index": display_turn, "sub_turn_index": None},
            "obj": {
                "type": "stop",
                "stop_reason": "finished",
            },
        }
    )
    packets_2d.append(turn_packets)

    messages.append(
        {
            "message_id": new_id,
            "message_type": "assistant",
            "research_type": None,
            "parent_message": parent_msg_id,
            "latest_child_message": None,
            "message": msg_content,
            "rephrased_query": None,
            "context_docs": None,
            "time_sent": None,
            "overridden_model": state.current_model,
            "alternate_assistant_id": state.current_persona_id,
            "chat_session_id": chat_session_id,
            "citations": None,
            "files": [],
            "tool_call": None,
            "current_feedback": None,
            "processing_duration_seconds": duration_sec,
            "sub_questions": [],
            "comments": None,
            "parentMessageId": parent_msg_id,
            "refined_answer_improvement": None,
            "is_agentic": None,
        }
    )
    if state.flow_answer_member:
        state.flow_answer_turn_open = True
    return


def _process_human_message(
    raw_msg: Any,
    state: ReconstructionState,
    messages: list[dict[str, Any]],
    packets_2d: list[list[dict[str, Any]]],
    chat_session_id: str,
) -> None:
    """A HumanMessage: a real user turn, or one of the synthetic ones a flow
    node emits and the timeline must not show as the user speaking."""

    if _human_is_persona_stamped(raw_msg):
        state.seen_persona_stamp = True

    if _is_flow_internal_human(raw_msg, state):
        # A flow node's own message (rendered prompt / text input), not a user
        # turn. Skip it entirely: it must not open a bubble, and it must not
        # reset the turn bookkeeping around it.
        return

    # Restore file badges from additional_kwargs set at send time. raw_msg
    # may be a LangChain object or a plain dict depending on checkpointer
    # deserialization.
    if isinstance(raw_msg, dict):
        _extra = raw_msg.get("additional_kwargs", {}) or {}
    else:
        _extra = getattr(raw_msg, "additional_kwargs", {}) or {}

    # A message carrying its own persona_id/model means this turn was sent
    # with that agent/model — adopt it as the current value for this and
    # subsequent messages until the next one overrides it. Messages
    # predating this tracking have neither key, so current_persona_id/
    # current_model keep whatever they were seeded/last set to (thread
    # metadata, by default).
    if "persona_id" in _extra:
        state.current_persona_id = _extra.get("persona_id")
    if _extra.get("model"):
        state.current_model = _extra.get("model")

    if _extra.get("is_regenerate"):
        # Legacy shape only (see ReconstructionState docstring): the user
        # never sent this — it's a duplicate created so the agent graph
        # would replay with new input. Skip the turn entirely; the
        # response that follows becomes a sibling of the previous response
        # under the original user message (last_real_user_msg_id), not a
        # new turn.
        state.pending_parent_override = state.last_real_user_msg_id
        return

    msg_content = strip_think_tags(extract_content(raw_msg))
    parent_msg_id = state.last_message_id
    new_id = state.ids.next_id()
    state.last_message_id = new_id
    state.last_real_user_msg_id = new_id
    state.flow_answer_turn_open = False
    state.user_turn_open = True

    if not state.pending_ltm_recalled_from_user:
        recalled_from_user = _extra.get("_ltm_recalled", 0)
        if isinstance(recalled_from_user, int) and recalled_from_user > 0:
            state.pending_ltm_recalled_from_user = recalled_from_user
    raw_files_meta = _extra.get("files_metadata", [])
    history_files = [
        {
            "id": f.get("id", ""),
            "type": f.get("type", "document"),
            "name": f.get("name"),
        }
        for f in (raw_files_meta or [])
        if isinstance(f, dict) and f.get("id")
    ]

    messages.append(
        {
            "message_id": new_id,
            "message_type": "user",
            "research_type": None,
            "parent_message": parent_msg_id,
            "latest_child_message": None,
            "message": msg_content,
            "rephrased_query": None,
            "context_docs": None,
            "time_sent": None,
            "overridden_model": state.current_model,
            "alternate_assistant_id": state.current_persona_id,
            "chat_session_id": chat_session_id,
            "citations": None,
            "files": history_files,
            "tool_call": None,
            "current_feedback": None,
            "processing_duration_seconds": None,
            "sub_questions": [],
            "comments": None,
            "parentMessageId": parent_msg_id,
            "refined_answer_improvement": None,
            "is_agentic": None,
        }
    )


def _process_raw_message(
    raw_msg: Any,
    state: ReconstructionState,
    messages: list[dict[str, Any]],
    packets_2d: list[list[dict[str, Any]]],
    chat_session_id: str,
) -> None:
    """Processes exactly one raw LangGraph message, mutating `state` and
    appending to `messages`/`packets_2d` as needed. Shared by both
    `reconstruct_messages` (one flat list) and `reconstruct_message_tree`
    (one checkpoint's incremental delta at a time) — this is what keeps
    message_id assignment (via `state.msg_idx`) collision-free across
    branches: whichever caller drives it, ids come from the same counter.

    Dispatch only — one handler per message type, below.
    """
    raw_type = getattr(raw_msg, "type", None)
    if raw_type is None and isinstance(raw_msg, dict):
        raw_type = raw_msg.get("type", "")

    if state.flow_blob_skip and raw_type in ("ai", "tool", "system"):
        # Non-terminal member of a blob-backed FlowAgent run — the blob
        # replayed on the terminal checkpoint is the only source of this
        # run's narration. A generated file is not narration: the blob keeps
        # only a truncated `result_preview` of a document tool's JSON, so
        # dropping the message outright is what made a file produced inside a
        # flow stage vanish on reload. Carry the payload to the blob turn.
        if raw_type == "tool":
            generated_file = parse_generated_file_payload(_extract_content(raw_msg))
            if generated_file is not None:
                state.pending_blob_generated_files.append(
                    build_generated_file_packet_obj(generated_file)
                )
        return

    if raw_type == "tool":
        _process_tool_message(raw_msg, state, messages, packets_2d, chat_session_id)
    elif raw_type == "system":
        _process_system_message(raw_msg, state, messages, packets_2d, chat_session_id)
    elif raw_type == "ai":
        _process_ai_message(raw_msg, state, messages, packets_2d, chat_session_id)
    elif raw_type in ("human", "user"):
        _process_human_message(raw_msg, state, messages, packets_2d, chat_session_id)
    # Any other type is not part of the rendered transcript and is ignored,
    # exactly as the original guard did.


def _flush_trailing_tool_packets(
    state: ReconstructionState,
    messages: list[dict[str, Any]],
    packets_2d: list[list[dict[str, Any]]],
    chat_session_id: str,
) -> None:
    """If a message list/branch ends without a visible AI message after
    tool calls (e.g. the model's final generation was interrupted and
    produced no content), preserve those tool steps as their own history
    turn instead of dropping them. A `packets_2d` entry with no matching
    `messages` entry never rendered — the chat bubble that would show it
    doesn't exist — so a `messages` entry is added here too. Only call
    this once per branch END (a leaf checkpoint in a tree walk, or once
    for a flat list) — mid-branch checkpoints must not flush.
    """
    if not state.pending_tool_packets:
        return

    reindexed_tools, next_turn = reindex_tool_packets(state.pending_tool_packets, 0)
    # Without a message_start/stop pair, the client has no signal that this
    # turn ever finished (no `stop` packet == "still streaming" as far as
    # the timeline pacing/completion logic is concerned), so only the
    # first step ever gets revealed.
    reindexed_tools.append(
        {
            "placement": {"turn_index": next_turn, "sub_turn_index": None},
            "obj": {
                "type": "message_start",
                "content": "",
                "final_documents": None,
            },
        }
    )
    reindexed_tools.append(
        {
            "placement": {"turn_index": next_turn, "sub_turn_index": None},
            "obj": {"type": "stop", "stop_reason": "finished"},
        }
    )
    packets_2d.append(reindexed_tools)
    state.pending_tool_packets = []

    if state.pending_parent_override is not None:
        parent_msg_id = state.pending_parent_override
        state.pending_parent_override = None
    else:
        parent_msg_id = state.last_message_id
    new_id = state.ids.next_id()
    state.last_message_id = new_id
    messages.append(
        {
            "message_id": new_id,
            "message_type": "assistant",
            "research_type": None,
            "parent_message": parent_msg_id,
            "latest_child_message": None,
            "message": "",
            "rephrased_query": None,
            "context_docs": None,
            "time_sent": None,
            "overridden_model": state.current_model,
            "alternate_assistant_id": state.current_persona_id,
            "chat_session_id": chat_session_id,
            "citations": None,
            "files": [],
            "tool_call": None,
            "current_feedback": None,
            "processing_duration_seconds": None,
            "sub_questions": [],
            "comments": None,
            "parentMessageId": parent_msg_id,
            "refined_answer_improvement": None,
            "is_agentic": None,
        }
    )


# =============================================================================
# Public entry points
# =============================================================================


def reconstruct_messages(
    langgraph_messages: list[Any],
    thread_metadata: dict[str, Any],
    chat_session_id: str,
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    """Walks one flat, already-accumulated LangGraph message list (a single
    checkpoint's full history) into the `messages`/`packets` shape
    `ChatController.get_chat_session` returns. Never raises — on internal
    failure, logs and returns whatever turns were parsed before the failing
    message, so one bad message doesn't wipe an otherwise-good history.
    """
    messages: list[dict[str, Any]] = []
    packets_2d: list[list[dict[str, Any]]] = []
    state = ReconstructionState(
        current_persona_id=thread_metadata.get("persona_id"),
        flow_stage_timelines=thread_metadata.get("flow_stage_timelines") or {},
        flow_timelines=thread_metadata.get("flow_timelines") or {},
        flow_versions=thread_metadata.get("flow_versions") or {},
    )

    try:
        for raw_msg in langgraph_messages:
            _process_raw_message(raw_msg, state, messages, packets_2d, chat_session_id)
        _flush_trailing_tool_packets(state, messages, packets_2d, chat_session_id)
        compute_latest_children(messages)
    except Exception:
        import traceback as _traceback

        logger.error(
            "Failed to reconstruct chat history for session %s (returning the %d "
            "turn(s) parsed before the failure):\n%s",
            chat_session_id,
            len(messages),
            _traceback.format_exc(),
        )
        # `messages`/`packets_2d` already hold whatever was parsed before
        # the failing turn — a long tool-heavy conversation has one bad
        # message wipe the entire visible history otherwise, discarding
        # turns that parsed fine.

    return messages, packets_2d


def _raw_message_type(raw_msg: Any) -> str:
    t = getattr(raw_msg, "type", None)
    if t is None and isinstance(raw_msg, dict):
        t = raw_msg.get("type", "")
    return t or ""


def _delta_for(checkpoint: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[Any]:
    """The messages a checkpoint added over its parent — the same slice
    reconstruct_message_tree feeds to _process_raw_message."""
    parent_id = checkpoint.get("parent_checkpoint_id")
    parent_len = len(by_id[parent_id]["messages"]) if parent_id in by_id else 0
    return checkpoint.get("messages", [])[parent_len:]


def _delta_starts_new_run(delta: list[Any], *, stamped: bool = False) -> bool:
    """A checkpoint whose delta contains a message the *user* sent opens a new
    conversation turn — a run boundary the fold walk must not cross.

    A flow node's own HumanMessage (a Prompt Template's rendered text, a Loop's
    current item) is not such a boundary: counting it split a single run into
    one turn per loop iteration, each with its own stage strip. On a stamped
    thread the ``persona_id`` marker tells the two apart; on an older thread
    every human message still counts, exactly as before.
    """
    return any(
        _raw_message_type(m) in ("human", "user") and (not stamped or _human_is_persona_stamped(m))
        for m in delta
    )


def _delta_visible_ai_ids(delta: list[Any]) -> list[str]:
    """Ids of AI messages in a delta that carry visible answer text and are
    not tool-call messages — i.e. the ones that would render as a chat
    bubble headline."""
    ids: list[str] = []
    for m in delta:
        if _raw_message_type(m) != "ai":
            continue
        if _msg_tool_calls(m):
            continue
        visible, _ = _extract_visible_and_reasoning(m)
        if visible:
            ids.append(_raw_message_id(m) or "")
    return ids


def _msg_tool_calls(m: Any) -> list[Any]:
    return getattr(m, "tool_calls", None) or (
        m.get("tool_calls", []) if isinstance(m, dict) else []
    )


def _delta_has_ai_tool_calls(delta: list[Any]) -> bool:
    return any(_raw_message_type(m) == "ai" and _msg_tool_calls(m) for m in delta)


def _emit_flow_blob_turn(
    state: "ReconstructionState",
    blob: dict[str, Any],
    messages: list[dict[str, Any]],
    packets_2d: list[list[dict[str, Any]]],
    chat_session_id: str,
    flow_version_no: int | None = None,
    stage_events: list[dict[str, Any]] | None = None,
    processing_duration_seconds: int | None = None,
) -> None:
    """Rebuild one FlowAgent run's turn from its persisted flow_timelines
    blob: the graph stage strip, then the numbered per-stage timeline groups,
    then the single final answer bubble. Replaces the _compute_flow_run_layout
    heuristic entirely for a blob-backed run."""
    from service.flow_timeline_reconstruction import (
        emit_flow_timeline_packets,
        flow_blob_duration_seconds,
        repair_legacy_tools,
    )

    stage_packets, final_text = emit_flow_timeline_packets(repair_legacy_tools(blob, stage_events))

    # The "thought for X" number the completed-timeline header shows. The live
    # run stamps it on the final AI message (additional_kwargs); reload uses
    # that when it survived the checkpoint, else the blob's stage span. Without
    # either the header falls back to a bare "thought for a while".
    duration_sec = processing_duration_seconds
    if duration_sec is None:
        duration_sec = flow_blob_duration_seconds(blob)

    # A blob run's intermediate stages produced nothing (flow_blob_skip), so
    # nothing should be buffered — but clear defensively so a stray packet
    # never leaks into this or a later turn.
    state.pending_tool_packets = []
    state.open_tool_call_positions = {}
    state.open_clarification_args = {}

    if state.pending_parent_override is not None:
        parent_msg_id = state.pending_parent_override
        state.pending_parent_override = None
    else:
        parent_msg_id = state.last_message_id
    new_id = state.ids.next_id()
    state.last_message_id = new_id

    turn_packets: list[dict[str, Any]] = list(stage_packets)

    # The graph stage strip. Its start/end events live in flow_stage_timelines,
    # not in the blob, so replaying only the blob left the strip with no stage
    # timings at all: it fell back to the flow definition and drew every stage
    # as pending, while the blob's tool packets — attached to no stage — were
    # promoted to top-level entries of their own. Only the stage brackets are
    # taken; the tool events there would double the blob's own tool packets.
    if stage_events:
        turn_packets[:0] = [
            p
            for p in _stage_timeline_packets(stage_events)
            if p["obj"].get("type") in ("graph_stage_start", "graph_stage_end")
        ]

    if flow_version_no is not None:
        turn_packets.insert(0, _flow_version_packet(flow_version_no))
    display_turn = max((p["placement"].get("turn_index", 0) for p in stage_packets), default=-1) + 1

    # Files the folded stages produced, on a display group of their own: put
    # one on the answer's turn and the chat renderer wins the group, hiding
    # the card exactly the way the fold did.
    if state.pending_blob_generated_files:
        turn_packets.extend(
            {"placement": {"turn_index": display_turn, "sub_turn_index": None}, "obj": obj}
            for obj in state.pending_blob_generated_files
        )
        state.pending_blob_generated_files = []
        display_turn += 1
    turn_packets.append(
        {
            "placement": {"turn_index": display_turn, "sub_turn_index": None},
            "obj": {
                "type": "message_start",
                "content": final_text,
                "final_documents": None,
                "pre_answer_processing_seconds": duration_sec,
            },
        }
    )
    turn_packets.append(
        {
            "placement": {"turn_index": display_turn, "sub_turn_index": None},
            "obj": {"type": "stop", "stop_reason": "finished"},
        }
    )
    packets_2d.append(turn_packets)

    messages.append(
        {
            "message_id": new_id,
            "message_type": "assistant",
            "research_type": None,
            "parent_message": parent_msg_id,
            "latest_child_message": None,
            "message": final_text,
            "rephrased_query": None,
            "context_docs": None,
            "time_sent": None,
            "overridden_model": state.current_model,
            "alternate_assistant_id": state.current_persona_id,
            "chat_session_id": chat_session_id,
            "citations": None,
            "files": [],
            "tool_call": None,
            "current_feedback": None,
            "processing_duration_seconds": duration_sec,
            "sub_questions": [],
            "comments": None,
            "parentMessageId": parent_msg_id,
            "refined_answer_improvement": None,
            "is_agentic": None,
        }
    )


def _compute_flow_blob_layout(
    by_id: dict[str, dict[str, Any]],
    children_by_parent: dict[str | None, list[str]],
    flow_timelines: dict[str, Any],
    stamped: bool = False,
) -> tuple[set[str], set[str]]:
    """Classify each checkpoint of a blob-backed FlowAgent run.

    Returns ``(terminal_ids, skip_ids)``:

    - **terminal_ids** — a checkpoint whose own delta carries the run's
      trailing visible-AI id, and that id has a flow_timelines blob. Its
      closing AI message triggers the full blob replay.
    - **skip_ids** — every earlier checkpoint of that same run. Its AI/tool
      messages produce nothing.

    A mid-run branch fork (the forward walk sees >1 non-run-starting child)
    breaks the walk; if the resulting trailing id is not a blob key the run
    is left unclassified and the legacy `_compute_flow_run_layout` path
    handles it.
    """
    if not flow_timelines:
        return set(), set()

    parent_of = {cid: cp.get("parent_checkpoint_id") for cid, cp in by_id.items()}

    def _has_visible_ai(cid: str) -> bool:
        return bool(_delta_visible_ai_ids(_delta_for(by_id[cid], by_id)))

    def _members_back(terminal_cid: str) -> list[str]:
        """Checkpoints from `terminal_cid` back to (and including) the one whose
        delta opens the run (has the human message). The parent chain is
        unique so this is always well-defined — a ConditionalRouter / Loop
        makes the message chain longer, never branched."""
        members = [terminal_cid]
        cur = terminal_cid
        while not _delta_starts_new_run(_delta_for(by_id[cur], by_id), stamped=stamped):
            pid = parent_of.get(cur)
            if pid is None or pid not in by_id:
                break
            cur = pid
            members.append(cur)
        return members

    # Candidate terminals: a checkpoint whose own delta carries a blob-keyed
    # trailing visible-AI id and that nothing *visible* continues past in the
    # same run (a bare `__end__` child does not count).
    runs: list[tuple[str, list[str]]] = []
    for cid, cp in by_id.items():
        own_ids = _delta_visible_ai_ids(_delta_for(cp, by_id))
        if not own_ids or own_ids[-1] not in flow_timelines:
            continue
        continues = any(
            _has_visible_ai(k)
            and not _delta_starts_new_run(_delta_for(by_id[k], by_id), stamped=stamped)
            for k in children_by_parent.get(cid, [])
        )
        if continues:
            continue
        runs.append((cid, _members_back(cid)))

    # A checkpoint shared by two runs, or one whose sibling carries its own
    # visible AI response, means a retry forked the chain — hand those runs to
    # the legacy path rather than guessing.
    seen: dict[str, int] = {}
    for _, members in runs:
        for m in members:
            seen[m] = seen.get(m, 0) + 1
    contested = {m for m, n in seen.items() if n > 1}
    for _, members in runs:
        for m in members:
            pid = parent_of.get(m)
            if pid is None:
                continue
            if any(k != m and _has_visible_ai(k) for k in children_by_parent.get(pid, [])):
                contested.add(m)

    terminal_ids: set[str] = set()
    skip_ids: set[str] = set()
    for terminal, members in runs:
        if any(m in contested for m in members):
            continue
        terminal_ids.add(terminal)
        skip_ids.update(m for m in members if m != terminal)
    return terminal_ids, skip_ids


def _compute_flow_run_layout(
    by_id: dict[str, dict[str, Any]],
    children_by_parent: dict[str | None, list[str]],
    flow_stage_timelines: dict[str, list[dict[str, Any]]],
    stamped: bool = False,
) -> tuple[set[str], set[str]]:
    """Classify each checkpoint of a multi-stage FlowAgent run.

    Returns ``(fold_ids, answer_ids)``:

    - **fold_ids** — checkpoints whose visible text is a *prep* stage: a
      LATER stage in the same run still makes tool calls, so this stage's
      output was a hand-off, not the answer. Its text folds into the run's
      one turn as collapsed reasoning.
    - **answer_ids** — checkpoints whose visible text is part of the final
      answer: no later stage calls a tool. The first opens the turn; any
      further ones append to it (the stages that only synthesise text).

    Only applied to a run whose trailing visible-AI message id is a key in
    ``flow_stage_timelines`` (which none but a real FlowAgent run persists).
    Ambiguity — a branch fork mid-run — leaves a checkpoint in neither set,
    i.e. the current per-message behaviour.
    """
    if not flow_stage_timelines:
        return set(), set()

    fold_ids: set[str] = set()
    answer_ids: set[str] = set()
    for cid, cp in by_id.items():
        own_ids = _delta_visible_ai_ids(_delta_for(cp, by_id))
        if not own_ids:
            continue  # produces no bubble text

        trailing_id: str | None = own_ids[-1]
        later_tool_calls = False
        cur = cid
        walked = {cid}
        while True:
            nxts = [
                k
                for k in children_by_parent.get(cur, [])
                if k not in walked
                and not _delta_starts_new_run(_delta_for(by_id[k], by_id), stamped=stamped)
            ]
            if len(nxts) != 1:
                break  # 0 = chain end, >1 = retry fork → ambiguous
            nxt = nxts[0]
            walked.add(nxt)
            nxt_delta = _delta_for(by_id[nxt], by_id)
            if _delta_has_ai_tool_calls(nxt_delta):
                later_tool_calls = True
            later_ids = _delta_visible_ai_ids(nxt_delta)
            if later_ids:
                trailing_id = later_ids[-1]
            cur = nxt

        if trailing_id not in flow_stage_timelines:
            continue  # not a recognised FlowAgent run
        (fold_ids if later_tool_calls else answer_ids).add(cid)
    return fold_ids, answer_ids


def reconstruct_message_tree(
    checkpoints: list[dict[str, Any]],
    thread_metadata: dict[str, Any],
    chat_session_id: str,
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    """Walks a thread's full checkpoint history — possibly branching, e.g.
    after a retry forks a new checkpoint chain from an earlier point —
    into the same `messages`/`packets` shape as `reconstruct_messages`.

    `checkpoints` is every checkpoint for the thread, each a dict with:
      - "checkpoint_id": str
      - "parent_checkpoint_id": str | None (None for a root checkpoint)
      - "messages": list[Any] — that checkpoint's own FULL accumulated
        message list (not a delta — the delta relative to its parent is
        computed here)

    Ids are assigned by walking the tree in parent-before-children order
    with ONE shared counter (via `ReconstructionState`, cloned per branch
    point), so two branches sharing a common ancestor never collide on
    message_id for their shared prefix, and never coincidentally reuse an
    id for their genuinely different messages either. Never raises — a
    branch that fails to reconstruct is logged and skipped, the rest of the
    tree still returns.
    """
    messages: list[dict[str, Any]] = []
    packets_2d: list[list[dict[str, Any]]] = []

    if not checkpoints:
        return messages, packets_2d

    by_id = {c["checkpoint_id"]: c for c in checkpoints}
    children_by_parent: dict[str | None, list[str]] = {}
    for c in checkpoints:
        children_by_parent.setdefault(c["parent_checkpoint_id"], []).append(c["checkpoint_id"])

    flow_stage_timelines = thread_metadata.get("flow_stage_timelines") or {}
    flow_timelines = thread_metadata.get("flow_timelines") or {}
    stamped = _thread_has_persona_stamp(checkpoints)
    fold_checkpoint_ids, answer_checkpoint_ids = _compute_flow_run_layout(
        by_id, children_by_parent, flow_stage_timelines, stamped
    )
    blob_terminal_ids, blob_skip_ids = _compute_flow_blob_layout(
        by_id, children_by_parent, flow_timelines, stamped
    )

    initial_state = ReconstructionState(
        current_persona_id=thread_metadata.get("persona_id"),
        flow_stage_timelines=flow_stage_timelines,
        flow_timelines=flow_timelines,
        flow_versions=thread_metadata.get("flow_versions") or {},
    )
    state_after: dict[str, ReconstructionState] = {}

    roots = children_by_parent.get(None, [])
    queue = list(roots)
    visited: set[str] = set()
    while queue:
        checkpoint_id = queue.pop(0)
        if checkpoint_id in visited:
            # A malformed/cyclic parent chain must not spin forever.
            continue
        visited.add(checkpoint_id)

        checkpoint = by_id[checkpoint_id]
        parent_id = checkpoint["parent_checkpoint_id"]
        parent_messages = by_id[parent_id]["messages"] if parent_id in by_id else []
        own_messages = checkpoint["messages"]
        delta = own_messages[len(parent_messages) :]

        state = (
            state_after[parent_id].clone() if parent_id in state_after else initial_state.clone()
        )
        _blob_backed = checkpoint_id in blob_terminal_ids or checkpoint_id in blob_skip_ids
        state.flow_blob_active = checkpoint_id in blob_terminal_ids
        state.flow_blob_skip = checkpoint_id in blob_skip_ids
        # The blob is authoritative for its run — the heuristic layout must
        # not also fire for the same checkpoints.
        state.flow_fold_stage = (not _blob_backed) and checkpoint_id in fold_checkpoint_ids
        state.flow_answer_member = (not _blob_backed) and checkpoint_id in answer_checkpoint_ids
        try:
            for raw_msg in delta:
                _process_raw_message(raw_msg, state, messages, packets_2d, chat_session_id)
        except Exception:
            import traceback as _traceback

            logger.error(
                "Failed to reconstruct branch at checkpoint %s for session %s:\n%s",
                checkpoint_id,
                chat_session_id,
                _traceback.format_exc(),
            )

        state_after[checkpoint_id] = state
        queue.extend(children_by_parent.get(checkpoint_id, []))

    # Flush trailing tool packets once per leaf (a checkpoint with no
    # children) — a mid-tree checkpoint's pending tool packets belong to
    # whichever of its children continues that turn, not to itself.
    for checkpoint_id in state_after:
        if not children_by_parent.get(checkpoint_id):
            _flush_trailing_tool_packets(
                state_after[checkpoint_id], messages, packets_2d, chat_session_id
            )

    compute_latest_children(messages)
    return messages, packets_2d

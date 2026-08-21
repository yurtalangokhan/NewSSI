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

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from service.DocumentProgressTracker import is_document_tool
from service.WebSearchProgressTracker import WebSearchProgressTracker, is_web_search_tool
from service.GeneratedFilePacket import (
    build_generated_file_packet_obj,
    parse_generated_file_payload,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Pure content-extraction helpers (no per-call state)
# =============================================================================


def _strip_think_tags(text: str) -> str:
    if not text:
        return text
    result = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    result = re.sub(r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL)
    result = re.sub(r"<think>(?:(?!</think>).)*$", "", result, flags=re.DOTALL)
    result = re.sub(r"<thinking>(?:(?!</thinking>).)*$", "", result, flags=re.DOTALL)
    return result.strip()


def _extract_content(msg: Any) -> str:
    if hasattr(msg, "content"):
        content = msg.content
    elif isinstance(msg, dict):
        content = msg.get("content", "")
    else:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text", "")
            if isinstance(item, str):
                return item
    if isinstance(content, dict):
        return content.get("text", "") or str(content)
    return ""


def _extract_reasoning_from_tags(text: str) -> str:
    if not text:
        return ""

    reasoning_parts: list[str] = []
    for open_tag, close_tag in (("<think>", "</think>"), ("<thinking>", "</thinking>")):
        start = 0
        while True:
            open_pos = text.find(open_tag, start)
            if open_pos == -1:
                break

            search_from = open_pos + len(open_tag)
            close_pos = text.find(close_tag, search_from)
            if close_pos == -1:
                chunk = text[search_from:]
                if chunk.strip():
                    reasoning_parts.append(chunk.strip())
                break

            chunk = text[search_from:close_pos]
            if chunk.strip():
                reasoning_parts.append(chunk.strip())
            start = close_pos + len(close_tag)

    return "\n".join(reasoning_parts).strip()


def _extract_visible_and_reasoning(msg: Any) -> tuple[str, str]:
    if hasattr(msg, "content"):
        content = msg.content
    elif isinstance(msg, dict):
        content = msg.get("content", "")
    else:
        return "", ""

    if isinstance(content, list):
        visible_parts: list[str] = []
        reasoning_parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "thinking":
                    thinking_text = str(item.get("thinking", "") or "")
                    if thinking_text:
                        reasoning_parts.append(thinking_text)
                    continue

                if item_type == "text":
                    text = str(item.get("text", "") or "")
                    if not text:
                        continue
                    if item.get("thought"):
                        reasoning_parts.append(text)
                    else:
                        visible_parts.append(text)
                    continue

            if isinstance(item, str) and item:
                visible_parts.append(item)

        visible_text = "".join(visible_parts).strip()
        reasoning_text = "\n".join(part for part in reasoning_parts if part).strip()
        return visible_text, reasoning_text

    text = _extract_content(msg)
    return _strip_think_tags(text), _extract_reasoning_from_tags(text)


def _extract_reasoning_from_metadata(msg: Any) -> str:
    def _stringify(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str) and item:
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("reasoning") or item.get("thinking")
                    if isinstance(text, str) and text:
                        parts.append(text)
            return "\n".join(parts).strip()
        return ""

    def _pick(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""

        reasoning_delta = payload.get("reasoning_delta")
        if isinstance(reasoning_delta, str):
            return reasoning_delta

        for key in (
            "reasoning_content",
            "reasoning",
            "thinking",
            "reasoning_text",
            "thoughts",
            "thought",
            "chain_of_thought",
        ):
            extracted = _stringify(payload.get(key))
            if extracted:
                return extracted

        nested_content = payload.get("content")
        if isinstance(nested_content, dict):
            return _pick(nested_content)

        return ""

    if isinstance(msg, dict):
        additional_kwargs = msg.get("additional_kwargs", {}) or {}
        response_metadata = msg.get("response_metadata", {}) or {}
    else:
        additional_kwargs = getattr(msg, "additional_kwargs", {}) or {}
        response_metadata = getattr(msg, "response_metadata", {}) or {}

    return _pick(additional_kwargs) or _pick(response_metadata)


def _reindex_tool_packets(
    packets: list[dict[str, Any]],
    start_turn: int,
) -> tuple[list[dict[str, Any]], int]:
    """Assign stable turn_index values so each reconstructed tool step stays visible."""
    from controller.step_turn_rules import should_increment_turn

    if not packets:
        return [], start_turn

    reindexed: list[dict[str, Any]] = []
    current_turn = start_turn
    prev_type: str | None = None
    prev_tool: str | None = None

    for packet in packets:
        obj = packet.get("obj", {}) if isinstance(packet, dict) else {}
        pkt_type = obj.get("type", "")
        tool_name = obj.get("tool_name")

        if should_increment_turn(
            pkt_type,
            prev_type,
            prev_tool,
            tool_name if isinstance(tool_name, str) else None,
            is_first=not reindexed,
        ):
            current_turn += 1

        reindexed.append(
            {
                **packet,
                "placement": {"turn_index": current_turn, "sub_turn_index": None},
            }
        )
        prev_type = pkt_type
        prev_tool = tool_name if isinstance(tool_name, str) else prev_tool

    return reindexed, current_turn + 1


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

    def clone(self) -> "ReconstructionState":
        return ReconstructionState(
            pending_tool_packets=list(self.pending_tool_packets),
            open_tool_call_positions=dict(self.open_tool_call_positions),
            web_search_progress=self.web_search_progress.clone(),
            pending_ltm_recalled_from_system=self.pending_ltm_recalled_from_system,
            pending_ltm_recalled_from_user=self.pending_ltm_recalled_from_user,
            ids=self.ids,  # shared reference, deliberately not copied — see _IdCounter
            last_message_id=self.last_message_id,
            current_persona_id=self.current_persona_id,
            current_model=self.current_model,
            last_real_user_msg_id=self.last_real_user_msg_id,
            pending_parent_override=self.pending_parent_override,
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
    """
    raw_type = getattr(raw_msg, "type", None)
    if raw_type is None and isinstance(raw_msg, dict):
        raw_type = raw_msg.get("type", "")

    if raw_type == "tool":
        tool_name = (
            getattr(raw_msg, "name", None)
            or (raw_msg.get("name", "") if isinstance(raw_msg, dict) else "")
            or "tool"
        )
        tool_call_id = getattr(raw_msg, "tool_call_id", None) or (
            raw_msg.get("tool_call_id") if isinstance(raw_msg, dict) else None
        )
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

    if raw_type == "system":
        system_text = _extract_content(raw_msg)
        if "[Long-Term Memory — Previously learned facts about this user]" in system_text:
            facts = [
                line for line in system_text.splitlines() if line.strip().startswith("- ")
            ]
            if facts:
                state.pending_ltm_recalled_from_system = len(facts)
        return

    if raw_type == "ai":
        tool_calls = getattr(raw_msg, "tool_calls", None) or (
            raw_msg.get("tool_calls", []) if isinstance(raw_msg, dict) else []
        )
        msg_content, reasoning_text = _extract_visible_and_reasoning(raw_msg)
        if not reasoning_text:
            reasoning_text = _extract_reasoning_from_metadata(raw_msg)

        if tool_calls:
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
                    tool_call.get("id")
                    if isinstance(tool_call, dict)
                    else getattr(tool_call, "id", None)
                )
                # A document tool is shown by its generated_file card
                # alone, exactly as the live stream does it. Adding a
                # generic tool step here made a reloaded conversation grow
                # an extra timeline entry the user never saw while it was
                # streaming.
                if is_document_tool(tool_name):
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
                        state.open_tool_call_positions[call_id] = (
                            len(state.pending_tool_packets) - 1
                        )
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
                    state.open_tool_call_positions[call_id] = (
                        len(state.pending_tool_packets) - 1
                    )
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

        if state.pending_parent_override is not None:
            parent_msg_id = state.pending_parent_override
            state.pending_parent_override = None
        else:
            parent_msg_id = state.last_message_id
        new_id = state.ids.next_id()
        state.last_message_id = new_id

        turn_packets: list[dict[str, Any]] = []
        turn_counter = 0

        # Read LTM metadata from the AI message first so it can be placed
        # before tool packets — matching the streaming order where LTM
        # recall is emitted before the agent begins tool calls.
        _extra = (
            raw_msg.get("additional_kwargs", {}) or {}
            if isinstance(raw_msg, dict)
            else getattr(raw_msg, "additional_kwargs", {}) or {}
        )
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

        if state.pending_tool_packets:
            reindexed_tools, next_turn = _reindex_tool_packets(
                state.pending_tool_packets,
                turn_counter,
            )
            turn_packets.extend(reindexed_tools)
            state.pending_tool_packets = []
            state.open_tool_call_positions = {}
            turn_counter = next_turn

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

        duration_sec = _extra.get("processing_duration_seconds") or _extra.get(
            "duration_seconds"
        )
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
        return

    if raw_type not in ("human", "user"):
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

    msg_content = _strip_think_tags(_extract_content(raw_msg))
    parent_msg_id = state.last_message_id
    new_id = state.ids.next_id()
    state.last_message_id = new_id
    state.last_real_user_msg_id = new_id

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

    reindexed_tools, next_turn = _reindex_tool_packets(state.pending_tool_packets, 0)
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


def _compute_latest_children(messages: list[dict[str, Any]]) -> None:
    """A parent can have multiple children (retried alternates sharing the
    same original user message) instead of always exactly one — the
    "latest" child is whichever was appended last, matching how the live
    in-session switcher already treats the most recent retry as the active
    branch. Mutates `messages` in place.
    """
    children_by_parent: dict[int, list[int]] = {}
    for m in messages:
        if m["parent_message"] is not None:
            children_by_parent.setdefault(m["parent_message"], []).append(m["message_id"])
    for m in messages:
        children = children_by_parent.get(m["message_id"])
        m["latest_child_message"] = children[-1] if children else None


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
    state = ReconstructionState(current_persona_id=thread_metadata.get("persona_id"))

    try:
        for raw_msg in langgraph_messages:
            _process_raw_message(raw_msg, state, messages, packets_2d, chat_session_id)
        _flush_trailing_tool_packets(state, messages, packets_2d, chat_session_id)
        _compute_latest_children(messages)
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
        children_by_parent.setdefault(c["parent_checkpoint_id"], []).append(
            c["checkpoint_id"]
        )

    initial_state = ReconstructionState(current_persona_id=thread_metadata.get("persona_id"))
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

    _compute_latest_children(messages)
    return messages, packets_2d

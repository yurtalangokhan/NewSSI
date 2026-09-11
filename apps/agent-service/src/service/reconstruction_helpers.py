"""Pure content-extraction and reconstruction helpers.

Extracted from ``ChatHistoryReconstruction`` to keep the main module focused
on the state-machine logic and public entry points. All functions here are
stateless — they take inputs and return outputs with no side effects.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------


def strip_think_tags(text: str) -> str:
    """Remove ``<think>`` / ``<thinking>`` tags (complete and trailing fragments)."""
    if not text:
        return text
    result = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    result = re.sub(r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL)
    result = re.sub(r"<think>(?:(?!</think>).)*$", "", result, flags=re.DOTALL)
    result = re.sub(r"<thinking>(?:(?!</thinking>).)*$", "", result, flags=re.DOTALL)
    return result.strip()


def extract_content(msg: Any) -> str:
    """Return the text content of a LangChain message-like object or dict."""
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


def extract_reasoning_from_tags(text: str) -> str:
    """Extract reasoning text from ``<think>`` / ``<thinking>`` tags."""
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


def extract_visible_and_reasoning(msg: Any) -> tuple[str, str]:
    """Split a message into visible text and reasoning text.

    Handles both structured content lists (with ``type: "thinking"`` blocks)
    and plain text with embedded ``<think>`` tags.
    """
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

    text = extract_content(msg)
    return strip_think_tags(text), extract_reasoning_from_tags(text)


def extract_reasoning_from_metadata(msg: Any) -> str:
    """Extract reasoning from ``additional_kwargs`` / ``response_metadata``."""

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


# ---------------------------------------------------------------------------
# Packet reindexing
# ---------------------------------------------------------------------------


def reindex_tool_packets(
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


def compute_latest_children(messages: list[dict[str, Any]]) -> None:
    """Set ``latest_child_message`` on each message.

    A parent can have multiple children (retried alternates). The latest
    child is whichever was appended last.  Mutates *messages* in place.
    """
    children_by_parent: dict[int, list[int]] = {}
    for m in messages:
        if m["parent_message"] is not None:
            children_by_parent.setdefault(m["parent_message"], []).append(m["message_id"])
    for m in messages:
        children = children_by_parent.get(m["message_id"])
        m["latest_child_message"] = children[-1] if children else None


# ---------------------------------------------------------------------------
# Trailing-tool-packet flushing
# ---------------------------------------------------------------------------

# Note: flush_trailing_tool_packets is defined in the main module because it
# depends on ReconstructionState, which lives there to avoid circular imports.
# It is re-imported by the main module from this file only for logical grouping
# in the future if needed.

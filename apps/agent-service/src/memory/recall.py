"""Long-term memory recall around an agent run.

Recall wraps a turn on both sides: before the run it pulls the user's stored
facts into the prompt and marks the input so a page refresh can replay that it
happened; after the run it tags the response so the same replay finds the
memories on the way back.

This lived twice — once in ``LazyLoadingAgent`` and once in ``ComposedAgent`` —
because the second was written while the first was being migrated away, and the
migration stopped halfway. The copies had already started to drift. Both now
call these functions.

Recall is an enhancement, never a precondition: a store that is missing, down
or failing leaves the turn to run without memories rather than failing it.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from core.observability.logger import get_logger

logger = get_logger(__name__)


def resolve_langgraph_store() -> Any | None:
    """Return the process-wide LangGraph store, or ``None`` if unavailable."""
    try:
        from infrastructure.runtime.langgraph_store import get_langgraph_store

        return get_langgraph_store()
    except Exception as exc:
        logger.warning("Could not resolve LangGraph store: %s", exc)
        return None


def build_memory_recall_event(memories: dict[str, Any]) -> dict[str, Any] | None:
    """Build the custom stream event announcing recalled memories."""
    facts = memories.get("user_facts", [])
    if not facts:
        return None
    return {
        "type": "long_term_memory_recall",
        "fact_count": len(facts),
        "memories": facts,
    }


def mark_input_with_ltm_recalled(input: Any, recalled_count: int) -> Any:
    """Record on the latest user message how many memories the turn recalled.

    Reconstructing a thread after a refresh replays the recall event from this
    count, so it has to survive on the message rather than only in the stream.
    """
    if recalled_count <= 0:
        return input
    if not isinstance(input, dict) or "messages" not in input:
        return input

    messages = list(input.get("messages") or [])
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]

        if isinstance(msg, dict):
            if msg.get("type", "") not in ("human", "user"):
                continue
            extra = msg.get("additional_kwargs", {}) or {}
            extra["_ltm_recalled"] = recalled_count
            msg["additional_kwargs"] = extra
            messages[idx] = msg
            return {**input, "messages": messages}

        if getattr(msg, "type", None) not in ("human", "user"):
            continue
        extra = getattr(msg, "additional_kwargs", {}) or {}
        extra["_ltm_recalled"] = recalled_count
        msg.additional_kwargs = extra
        messages[idx] = msg
        return {**input, "messages": messages}

    return input


def tag_output_with_recalled_memories(output: Any, memories: dict[str, Any]) -> Any:
    """Tag response messages so chat history can replay the recall after a refresh."""
    if not memories.get("user_facts"):
        return output

    from memory.long_term import tag_response_with_ltm_recall

    if isinstance(output, dict) and output.get("messages"):
        tag_response_with_ltm_recall(output["messages"][-1], memories)
        return output

    # 2-tuples: (stream_mode, payload). 3-tuples with subgraphs=True: (path, stream_mode, payload).
    if isinstance(output, tuple) and len(output) in (2, 3):
        stream_mode, payload = output[-2], output[-1]
        if stream_mode == "updates" and isinstance(payload, dict):
            for updates in payload.values():
                if isinstance(updates, dict) and updates.get("messages"):
                    tag_response_with_ltm_recall(updates["messages"][-1], memories)
        elif stream_mode == "values" and isinstance(payload, dict) and payload.get("messages"):
            tag_response_with_ltm_recall(payload["messages"][-1], memories)

    return output


async def inject_memory_into_input(
    input: Any,
    config: RunnableConfig | None = None,
) -> tuple[Any, dict, str | None]:
    """Prepend memories relevant to this turn's question to *input*.

    Returns ``(modified_input, memories, user_id)``. When long-term memory is
    off or recall fails, the input comes back untouched with an empty memories
    dict -- the turn proceeds either way.

    Recall is query-aware, so it takes no LangGraph store: the facts live in
    rag-service's semantic index now, not in the store this used to read, and
    only those relevant to the current message are surfaced.

    Args:
        input: The run input, usually ``{"messages": [...]}``.
        config: The run config; ``configurable`` carries the memory flag and user.
    """
    configurable = (config or {}).get("configurable", {})
    long_term_memory = configurable.get("long_term_memory", False)
    user_id = configurable.get("user_id")
    memories: dict = {}

    if not long_term_memory or not user_id:
        return input, memories, user_id

    try:
        from memory.long_term import latest_human_message_text, recall_context_for_turn

        messages = input.get("messages", []) if isinstance(input, dict) else []
        memories, memory_context = await recall_context_for_turn(
            user_id, latest_human_message_text(messages), configurable
        )
        input = mark_input_with_ltm_recalled(input, len(memories.get("user_facts", [])))

        if memory_context and isinstance(input, dict) and "messages" in input:
            input = {
                **input,
                "messages": [SystemMessage(content=memory_context), *list(input["messages"])],
            }
    except Exception as exc:
        # Fail open: a memory outage must not cost the user their answer.
        logger.warning("Memory recall failed: %s", exc)
        memories = {}

    return input, memories, user_id

"""The chat thread the running LangGraph call belongs to."""

from __future__ import annotations

from uuid import UUID

from langgraph.config import get_config

from service.knowledge_evidence.references import parse_uuid


def current_thread_id() -> UUID | None:
    """``configurable.thread_id`` of the running graph, when it is a thread UUID.

    Outside a runnable (tests, tool-mode invocation) there is no config and no
    thread, so evidence is simply not recorded.
    """
    try:
        config = get_config()
    except RuntimeError:
        return None
    thread_id = (config.get("configurable") or {}).get("thread_id")
    return parse_uuid(thread_id)

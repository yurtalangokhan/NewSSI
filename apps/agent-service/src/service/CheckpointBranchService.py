"""Locates the LangGraph checkpoint to fork a retry from.

A retry must generate its response using only the context up through the
original human message — never the previous (rejected) answer. Simply
deleting that answer from the shared checkpoint would satisfy that but
permanently lose it from history (breaking the 1/2 alternate-response
switcher). Instead, retry gets its own real checkpoint branch: find the
checkpoint that existed right after the target human message and before
its original response, and invoke the graph from there. See
.tmp/2026-08-21-retry-checkpoint-branching-design.md.
"""

from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig

from service.ChatHistoryReconstruction import reconstruct_messages


class _StateHistorySnapshot(Protocol):
    values: dict[str, Any]
    config: RunnableConfig


class _AgentWithStateHistory(Protocol):
    def aget_state_history(self, config: RunnableConfig):
        ...


async def find_fork_point(
    agent: _AgentWithStateHistory,
    thread_id: str,
    target_message_id: int,
    thread_metadata: dict[str, Any],
) -> RunnableConfig | None:
    """Returns the config (with a specific checkpoint_id) of the checkpoint
    whose reconstructed history ends exactly at target_message_id with no
    assistant response yet, or None if no such checkpoint is found — the
    caller must fall back to normal (append-to-tip) behavior, never hard-fail
    a retry over this.
    """
    history_config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    async for snapshot in agent.aget_state_history(history_config):
        raw_messages = snapshot.values.get("messages", [])
        messages, _ = reconstruct_messages(
            raw_messages, thread_metadata, thread_id
        )
        if not messages:
            continue
        last = messages[-1]
        if last["message_id"] == target_message_id and last["message_type"] == "user":
            return snapshot.config
    return None

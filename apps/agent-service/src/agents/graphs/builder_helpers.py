"""Pure helpers for the graph builder.

Extracted from ``agents/graphs/builder.py`` to reduce its LOC.  All functions
here are stateless.
"""

from __future__ import annotations

from typing import Any


def agent_def_to_config(agent_def: Any) -> dict[str, Any]:
    """
    Convert AgentDefinitionModel to graph config dict.

    Args:
        agent_def: AgentDefinitionModel instance

    Returns:
        Config dict compatible with graph builders
    """
    return {
        "name": agent_def.name,
        "graph_schema": agent_def.graph_schema,
        "system_prompt": agent_def.system_prompt or "You are a helpful agent.",
        "model": agent_def.model,
        "mcp_tools": agent_def.mcp_tools or [],
        "mcp_tool_configs": agent_def.mcp_tool_configs or {},
        "rag_config": agent_def.rag_config,
        "supervisor_prompt": agent_def.supervisor_prompt,
        "stages": agent_def.stages,
        "pipeline_prompt": agent_def.pipeline_prompt,
        "reflection_prompt": agent_def.reflection_prompt,
        "max_iterations": agent_def.max_iterations or 3,
        "sub_agent_ids": agent_def.sub_agent_ids or [],
    }


MAX_NESTED_SUB_AGENT_DEPTH = 5


async def _inject_memory_context_async(messages: list, config: Any) -> list:
    """Async memory context injection - safe to call from within async node functions."""
    from langchain_core.messages import SystemMessage

    from core.observability.logger import get_logger

    logger = get_logger(__name__)
    try:
        configurable = config.get("configurable", {}) if config else {}
        user_id = configurable.get("user_id")
        long_term_memory = configurable.get("long_term_memory", False)

        if long_term_memory and user_id:
            store = configurable.get("store")
            if store:
                from memory.long_term import (
                    build_event_emitters,
                    build_memory_context,
                    recall_memories,
                )

                on_recall, _ = build_event_emitters(configurable)
                memories = await recall_memories(store, user_id, on_recall=on_recall)
                context = build_memory_context(memories)
                if context:
                    return [SystemMessage(content=context), *list(messages)]
    except Exception as e:
        logger.warning(f"Memory injection failed: {e}")

    return messages

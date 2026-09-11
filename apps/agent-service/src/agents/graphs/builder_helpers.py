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

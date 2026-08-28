"""Built-in agent recipes for the agent-service composition path.

Built-in agents are represented here as *recipes* over the same composer
(``AgentFactory`` / ``AgentComposer``) used by persisted dynamic agents. Each
recipe is a flat configuration dict compatible with ``AgentFactory.create``,
which constructs a ``DynamicAgent`` from it.

Routing policy (see ``agents.agents`` resolver):

* Keys that still live in the legacy static registry (``chatbot``,
  ``configurable-mcp-agent``) continue to be served from that registry for
  backward compatibility. Their canonical recipe definitions are kept here so
  the migration can be completed in a later step without losing the
  configuration.
* Keys that are only defined here (``pipeline``, ``supervisor``) are routed
  through ``AgentFactory.create`` whenever they are resolved, so they share the
  exact construction path used by persisted dynamic agents.

This module intentionally has no framework, LangGraph, or persistence imports so
it stays in the application layer and does not trip the architecture gate.
"""

from __future__ import annotations

from typing import Any

# Canonical flat-config recipes for built-in agents. These mirror the JSON
# configs previously loaded by the reflection-based ``agents.factory`` and the
# static registry in ``agents.agents``, expressed as ``AgentFactory``-compatible
# definition configs.
BUILTIN_RECIPES: dict[str, dict[str, Any]] = {
    "chatbot": {
        "name": "chatbot",
        "graph_schema": "zero_shot",
        "system_prompt": "You are a helpful AI assistant.",
    },
    "configurable-mcp-agent": {
        "name": "configurable-mcp-agent",
        "graph_schema": "react",
        "system_prompt": "You are a helpful assistant with configurable tools.",
        "mcp_tools": [],
    },
    "pipeline": {
        "name": "pipeline",
        "graph_schema": "pipeline",
        "system_prompt": "You are a pipeline supervisor.",
        "stages": [
            {
                "name": "enricher",
                "system_prompt": (
                    "You are a project enricher. Analyze input and expand with details."
                ),
                "mcp_tools": [],
            }
        ],
    },
    "supervisor": {
        "name": "supervisor",
        "graph_schema": "supervisor",
        "system_prompt": "You are a team supervisor.",
        "sub_agents": [
            {
                "name": "assistant",
                "system_prompt": "You are a helpful assistant.",
                "mcp_tools": [],
            }
        ],
    },
}


def get_builtin_recipe(agent_id: str) -> dict[str, Any] | None:
    """Return the recipe config for a built-in agent key, if defined."""
    return BUILTIN_RECIPES.get(agent_id)


def list_builtin_recipe_keys() -> list[str]:
    """Return all built-in recipe keys."""
    return list(BUILTIN_RECIPES)

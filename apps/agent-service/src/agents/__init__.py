"""Agents module - AI agent implementations and management.

Canonical agent construction now flows through ``agent_composition``
(``AgentFactory`` -> ``AgentComposer`` -> ``ComposedAgent``). This package keeps
the backward-compatible static registry facade (``agents.agents``) plus the
retained storage contracts. The legacy reflection factory, registry, configs,
managers, runtime, base, impl, and perceptron islands were removed during the
composition/simplification closeout.

Backward Compatibility:
- Provides the same public facade exports as the original agents.agents module.
"""

# Re-export original module for backward compatibility
from agents.agents import (
    DEFAULT_AGENT,
    AgentGraph,
    AgentGraphLike,
    get_agent,
    get_agent_or_lazy,
    get_all_agent_info,
    load_agent,
)

# Storage
from agents.storage import (
    AgentDefinitionModel,
    AgentDefinitionRepository,
)

__all__ = [
    # Backward compatibility
    "get_agent",
    "get_agent_or_lazy",
    "load_agent",
    "get_all_agent_info",
    "DEFAULT_AGENT",
    "AgentGraph",
    "AgentGraphLike",
    # Storage
    "AgentDefinitionModel",
    "AgentDefinitionRepository",
]

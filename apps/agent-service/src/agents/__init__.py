"""Agents module - AI agent implementations and management.

Canonical agent construction now flows through ``agent_composition``
(``AgentFactory`` -> ``AgentComposer`` -> ``ComposedAgent``). This package keeps
the backward-compatible static registry facade (``agents.agents``). Persistence,
database models, and external tool implementations live outside this runtime
package.

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

__all__ = [
    # Backward compatibility
    "get_agent",
    "get_agent_or_lazy",
    "load_agent",
    "get_all_agent_info",
    "DEFAULT_AGENT",
    "AgentGraph",
    "AgentGraphLike",
]

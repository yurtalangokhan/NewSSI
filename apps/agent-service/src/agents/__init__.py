"""Agents module - AI agent implementations and management.

Canonical agent construction now flows through ``agent_composition``
(``AgentFactory`` -> ``AgentComposer`` -> ``ComposedAgent``). This package keeps
the backward-compatible static registry facade (``agents.agents``) plus the
retained ``base``/``perceptron``/``storage`` contracts. The legacy reflection
factory, registry, configs, managers, and runtime island were removed in ASC-7.

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

# New module exports - from base
from agents.base.agent import (
    AgentMetadata,
    AgentResult,
    BaseAgent,
    LazyLoadingAgent,
)
from agents.base.brain import (
    Brain,
    GuardBrain,
    LLMBrain,
    ReasoningResult,
)
from agents.base.manager import (
    AgentManager,
    DelegateRequest,
    HierarchicalManager,
    PipelineManager,
    SupervisorManager,
    TaskResult,
)
from agents.base.perceptron import (
    MemoryPerceptron,
    PerceptionResult,
    Perceptron,
    ToolPerceptron,
    VectorPerceptron,
)

# From perceptrons
from agents.perceptrons import CompositePerceptron, MCPPerceptron

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
    # Base classes - agent
    "BaseAgent",
    "LazyLoadingAgent",
    "AgentMetadata",
    "AgentResult",
    # Base classes - brain
    "Brain",
    "LLMBrain",
    "GuardBrain",
    "ReasoningResult",
    # Base classes - perceptron
    "Perceptron",
    "ToolPerceptron",
    "MemoryPerceptron",
    "VectorPerceptron",
    "PerceptionResult",
    "MCPPerceptron",
    "CompositePerceptron",
    # Base classes - manager
    "AgentManager",
    "SupervisorManager",
    "PipelineManager",
    "HierarchicalManager",
    "TaskResult",
    "DelegateRequest",
    # Storage
    "AgentDefinitionModel",
    "AgentDefinitionRepository",
]

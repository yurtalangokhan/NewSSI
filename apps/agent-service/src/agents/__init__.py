"""Agents module - AI agent implementations and management.

Core Components:
- base: Abstract base classes (BaseAgent, Brain, Perceptron, AgentManager)
- registry: Agent registration system (@agent decorator)
- configs: JSON configuration files
- storage: Database models and repositories
- managers: Supervisor and Pipeline implementations
- perceptrons: Tool and MCP integrations

Backward Compatibility:
- Provides same exports as original agents.agents module
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
    BaseAgent,
    LazyLoadingAgent,
    AgentMetadata,
    AgentResult,
)

from agents.base.brain import (
    Brain,
    LLMBrain,
    GuardBrain,
    ReasoningResult,
)

from agents.base.perceptron import (
    Perceptron,
    ToolPerceptron,
    MemoryPerceptron,
    VectorPerceptron,
    PerceptionResult,
)

from agents.base.manager import (
    AgentManager,
    SupervisorManager,
    PipelineManager,
    HierarchicalManager,
    TaskResult,
    DelegateRequest,
)

# From perceptrons
from agents.perceptrons import MCPPerceptron, CompositePerceptron

# Registry
from agents.registry import AgentRegistry, agent, agent_factory

# Configs
from agents.configs import (
    load_agent_config,
    load_agent_configs,
    save_agent_config,
    delete_agent_config,
    list_config_names,
)

# Managers
from agents.managers import (
    DynamicFlatSupervisor,
    get_supervisor,
    DynamicPipelineSupervisor,
    get_pipeline,
)

# Storage
from agents.storage import (
    AgentDefinitionModel,
    AgentInstanceModel,
    AgentDefinitionRepository,
    AgentInstanceRepository,
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
    # Registry
    "AgentRegistry",
    "agent",
    "agent_factory",
    # Configs
    "load_agent_config",
    "load_agent_configs",
    "save_agent_config",
    "delete_agent_config",
    "list_config_names",
    # Managers
    "DynamicFlatSupervisor",
    "get_supervisor",
    "DynamicPipelineSupervisor",
    "get_pipeline",
    # Storage
    "AgentDefinitionModel",
    "AgentInstanceModel",
    "AgentDefinitionRepository",
    "AgentInstanceRepository",
]

"""AgentManager - Coordinates multiple agents (Supervisor, Pipeline, Hierarchical)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.base.agent import BaseAgent, AgentResult


@dataclass
class TaskResult:
    """Result from a delegated task."""

    agent_name: str
    output: Any
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DelegateRequest:
    """Request to delegate a task to sub-agents."""

    task: str
    required_agents: list[str] | None = None
    parallel: bool = False
    timeout: int | None = None


class AgentManager(ABC):
    """
    AgentManager - Coordinates multiple agents.

    Managers are responsible for:
    - Managing sub-agent lifecycle
    - Task delegation and routing
    - Result aggregation
    - Error handling across agents

    Types of managers:
    - Supervisor: Flat multi-agent coordination
    - Pipeline: Sequential stage execution
    - Hierarchical: Nested manager structures
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the manager.

        Args:
            config: Manager configuration (sub-agents, stages, etc.)
        """
        self._config = config or {}
        self._sub_agents: dict[str, BaseAgent] = {}
        self._loaded = False

    @property
    @abstractmethod
    def manager_type(self) -> str:
        """Type of manager: supervisor, pipeline, hierarchical."""
        pass

    @property
    def sub_agents(self) -> dict[str, BaseAgent]:
        """Get all registered sub-agents."""
        return self._sub_agents

    @abstractmethod
    async def load(self) -> None:
        """
        Load/initialize the manager.

        Should load sub-agents and set up coordination logic.
        """
        pass

    @abstractmethod
    async def delegate(
        self,
        request: DelegateRequest,
        config: RunnableConfig | None = None,
    ) -> TaskResult:
        """
        Delegate a task to appropriate sub-agent(s).

        Args:
            request: Task to delegate
            config: Runtime configuration

        Returns:
            TaskResult from the delegation
        """
        pass

    @abstractmethod
    async def create_team(
        self,
        agent_definitions: list[dict[str, Any]],
    ) -> None:
        """
        Create a team of sub-agents.

        Args:
            agent_definitions: List of agent configurations
        """
        pass

    def add_sub_agent(self, name: str, agent: BaseAgent) -> None:
        """Add a sub-agent to the manager."""
        self._sub_agents[name] = agent

    def remove_sub_agent(self, name: str) -> None:
        """Remove a sub-agent from the manager."""
        self._sub_agents.pop(name, None)

    def get_sub_agent(self, name: str) -> BaseAgent | None:
        """Get a specific sub-agent."""
        return self._sub_agents.get(name)

    def update_config(self, config: dict[str, Any]) -> None:
        """Update manager configuration."""
        self._config.update(config)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)


class SupervisorManager(AgentManager):
    """
    Flat supervisor - coordinates multiple agents in parallel.

    Routes tasks to appropriate sub-agents based on capabilities.
    Results are aggregated into a coherent response.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._prompt: str = ""

    @property
    def manager_type(self) -> str:
        return "supervisor"

    async def load(self) -> None:
        """Load supervisor with sub-agents."""
        # Load from config
        sub_agents_config = self.get_config("sub_agents", [])
        if sub_agents_config:
            await self.create_team(sub_agents_config)
        self._loaded = True

    async def delegate(
        self,
        request: DelegateRequest,
        config: RunnableConfig | None = None,
    ) -> TaskResult:
        """Delegate task to appropriate sub-agent."""
        # Implementation will use LangGraph supervisor
        return TaskResult(agent_name="", output={}, success=True)

    async def create_team(
        self,
        agent_definitions: list[dict[str, Any]],
    ) -> None:
        """Create team from definitions."""
        for agent_def in agent_definitions:
            name = agent_def.get("name", "agent")
            # Would load/create agent here
            pass

    def set_prompt(self, prompt: str) -> None:
        """Set supervisor system prompt."""
        self._prompt = prompt

    def get_prompt(self) -> str:
        """Get supervisor system prompt."""
        return self._prompt


class PipelineManager(AgentManager):
    """
    Pipeline manager - executes stages sequentially.

    Each stage's output feeds into the next stage.
    Supports error handling and retry logic.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._stages: list[str] = []

    @property
    def manager_type(self) -> str:
        return "pipeline"

    @property
    def stages(self) -> list[str]:
        """Get pipeline stages."""
        return self._stages

    async def load(self) -> None:
        """Load pipeline with stages."""
        stages_config = self.get_config("stages", [])
        self._stages = [s.get("name") for s in stages_config if s.get("name")]
        self._loaded = True

    async def delegate(
        self,
        request: DelegateRequest,
        config: RunnableConfig | None = None,
    ) -> TaskResult:
        """Execute task through pipeline stages."""
        return TaskResult(agent_name="pipeline", output={}, success=True)

    async def create_team(
        self,
        agent_definitions: list[dict[str, Any]],
    ) -> None:
        """Create pipeline stages from definitions."""
        self._stages = []
        for agent_def in agent_definitions:
            name = agent_def.get("name")
            if name:
                self._stages.append(name)

    def add_stage(self, name: str) -> None:
        """Add a stage to the pipeline."""
        if name not in self._stages:
            self._stages.append(name)

    def remove_stage(self, name: str) -> None:
        """Remove a stage from the pipeline."""
        if name in self._stages:
            self._stages.remove(name)

    def get_stage_index(self, name: str) -> int:
        """Get index of a stage."""
        return self._stages.index(name) if name in self._stages else -1


class HierarchicalManager(AgentManager):
    """
    Hierarchical manager - nested manager structures.

    Top-level manager delegates to mid-level managers,
    which delegate to leaf agents.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._managers: dict[str, AgentManager] = {}

    @property
    def manager_type(self) -> str:
        return "hierarchical"

    async def load(self) -> None:
        """Load hierarchical structure."""
        self._loaded = True

    async def delegate(
        self,
        request: DelegateRequest,
        config: RunnableConfig | None = None,
    ) -> TaskResult:
        """Delegate through hierarchy."""
        return TaskResult(agent_name="hierarchy", output={}, success=True)

    async def create_team(
        self,
        agent_definitions: list[dict[str, Any]],
    ) -> None:
        """Create hierarchical team."""
        pass

    def add_manager(self, name: str, manager: AgentManager) -> None:
        """Add a mid-level manager."""
        self._managers[name] = manager

    def remove_manager(self, name: str) -> None:
        """Remove a mid-level manager."""
        self._managers.pop(name, None)

    def get_manager(self, name: str) -> AgentManager | None:
        """Get a mid-level manager."""
        return self._managers.get(name)

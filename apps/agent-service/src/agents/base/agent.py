"""Abstract base classes for agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from langchain_core.runnables import RunnableConfig


@dataclass
class AgentMetadata:
    """Metadata for an agent definition."""

    name: str
    agent_type: str
    description: str = ""
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Result from agent execution."""

    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Agents are the core execution units in the system. They can be:
    - Simple single-purpose agents (chatbot, researcher)
    - Composite agents (with brains and perceptrons)
    - Managers (supervisors, pipelines)

    All agents implement invoke/stream methods for execution.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the agent with optional configuration.

        Args:
            config: Agent configuration dictionary
        """
        self._config = config or {}
        self._metadata: AgentMetadata | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this agent."""
        pass

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Type of agent: basic, brain, perceptron, manager, composite."""
        pass

    @property
    def description(self) -> str:
        """Human-readable description of what this agent does."""
        return ""

    @property
    def metadata(self) -> AgentMetadata:
        """Get agent metadata."""
        if self._metadata is None:
            self._metadata = AgentMetadata(
                name=self.name,
                agent_type=self.agent_type,
                description=self.description,
            )
        return self._metadata

    @abstractmethod
    async def load(self) -> None:
        """
        Load/initialize the agent.

        Called once during service startup. Should handle:
        - Loading tools or resources
        - Setting up connections (MCP, databases)
        - Creating the execution graph
        """
        pass

    @abstractmethod
    async def invoke(
        self, input: Any, config: RunnableConfig | None = None, **kwargs: Any
    ) -> AgentResult:
        """
        Synchronous invoke of the agent.

        Args:
            input: Input to process (usually dict with 'messages' key)
            config: Optional runtime configuration
            **kwargs: Additional arguments

        Returns:
            AgentResult with output and metadata
        """
        pass

    @abstractmethod
    async def stream(
        self, input: Any, config: RunnableConfig | None = None, **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        """
        Streaming invoke of the agent.

        Args:
            input: Input to process
            config: Optional runtime configuration
            **kwargs: Additional arguments

        Yields:
            Chunks of output
        """
        pass

    @abstractmethod
    async def astream_events(
        self, input: Any, config: RunnableConfig | None = None, version: str = "v2", **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream events for monitoring/observability.

        Args:
            input: Input to process
            config: Optional runtime configuration
            version: LangGraph events version
            **kwargs: Additional arguments

        Yields:
            Event dictionaries
        """
        pass

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)

    def update_config(self, config: dict[str, Any]) -> None:
        """Update agent configuration."""
        self._config.update(config)

    async def ensure_loaded(self) -> None:
        """Ensure the agent is loaded before execution."""
        if not hasattr(self, "_loaded") or not self._loaded:
            await self.load()

    def get_graph(self) -> Any:
        """
        Get the underlying LangGraph graph.

        Returns:
            CompiledStateGraph or Pregel instance
        """
        raise NotImplementedError("Agent does not support graph access")


class LazyLoadingAgent(BaseAgent):
    """
    Base class for agents that require async loading.

    Extends BaseAgent with lazy loading capabilities for:
    - MCP tool connections
    - Database connections
    - Expensive resource initialization
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._loaded = False
        self._graph: Any = None

    @property
    def is_loaded(self) -> bool:
        """Check if agent is loaded."""
        return self._loaded

    async def ensure_loaded(self) -> None:
        """Ensure the agent is loaded."""
        if not self._loaded:
            await self.load()

    def get_graph(self) -> Any:
        """Get the loaded graph."""
        if not self._loaded:
            raise RuntimeError("Agent not loaded. Call load() first.")
        return self._graph

    async def invoke(
        self, input: Any, config: RunnableConfig | None = None, **kwargs: Any
    ) -> AgentResult:
        await self.ensure_loaded()
        return AgentResult(output={})

    async def stream(
        self, input: Any, config: RunnableConfig | None = None, **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        await self.ensure_loaded()
        yield {}

    async def astream_events(
        self, input: Any, config: RunnableConfig | None = None, version: str = "v2", **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        await self.ensure_loaded()
        yield {}

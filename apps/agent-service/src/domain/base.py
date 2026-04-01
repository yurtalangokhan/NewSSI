"""Abstract base classes for the domain layer."""

from abc import ABC, abstractmethod
from typing import Any


class BaseService(ABC):
    """Abstract base class for domain services."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the service."""
        pass


class AgentServiceInterface(ABC):
    """Interface for agent management service."""

    @abstractmethod
    async def get_agent(self, agent_id: str) -> Any:
        """Get an agent by ID."""
        pass

    @abstractmethod
    async def list_agents(self) -> list[dict[str, Any]]:
        """List all available agents."""
        pass


class ThreadServiceInterface(ABC):
    """Interface for thread/conversation management."""

    @abstractmethod
    async def create_thread(
        self, thread_id: str | None = None, metadata: dict | None = None
    ) -> dict[str, Any]:
        """Create a new thread."""
        pass

    @abstractmethod
    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Get a thread by ID."""
        pass

    @abstractmethod
    async def update_thread(self, thread_id: str, metadata: dict) -> dict[str, Any] | None:
        """Update thread metadata."""
        pass


class AssistantServiceInterface(ABC):
    """Interface for assistant management."""

    @abstractmethod
    async def create_assistant(
        self, graph_id: str, name: str | None = None, config: dict | None = None
    ) -> dict[str, Any]:
        """Create a new assistant."""
        pass

    @abstractmethod
    async def get_assistant(self, assistant_id: str) -> dict[str, Any] | None:
        """Get an assistant by ID."""
        pass


class DatasourceServiceInterface(ABC):
    """Interface for datasource management."""

    @abstractmethod
    async def create_datasource(self, name: str, config: dict) -> dict[str, Any]:
        """Create a new datasource."""
        pass

    @abstractmethod
    async def list_datasources(self) -> list[dict[str, Any]]:
        """List all datasources."""
        pass

    @abstractmethod
    async def sync_datasource(self, datasource_id: str) -> dict[str, Any]:
        """Sync a datasource."""
        pass

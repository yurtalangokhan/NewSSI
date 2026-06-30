"""Agent controller - handles agents and assistants domain logic."""

from typing import Any

from controller.base import BaseController
from core.db.repositories import AssistantRepository
from service.AssistantAgentService import AssistantAgentService

# Agent-level permission checking
class AgentPermissionError(Exception):
    def __init__(self, action: str, agent_id: str = None):
        self.action = action
        self.agent_id = agent_id
        if agent_id:
            super().__init__(f"Permission denied: {action} on agent '{agent_id}'")
        else:
            super().__init__(f"Permission denied: {action}")


class AgentController(BaseController):
    """Controller for agents and assistants domain.

    Injects:
    - AssistantAgentService: for agent management and execution
    - AssistantRepository: for persistent assistant storage
    """

    def __init__(
        self,
        service: AssistantAgentService | None = None,
        repo: AssistantRepository | None = None,
    ):
        self._service = service or AssistantAgentService.get_instance()
        self._repo = repo or AssistantRepository()

    # =========================================================================
    # Assistant CRUD (database)
    # =========================================================================

    async def get_assistant(self, assistant_id: str) -> dict[str, Any] | None:
        """Get an assistant by ID from the database."""
        return await self._service.get_assistant(assistant_id)

    async def list_assistants(self) -> list[dict[str, Any]]:
        """List all assistants from the database."""
        return await self._service.list_assistants()

    async def create_assistant(
        self,
        graph_id: str,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new assistant in the database."""
        return await self._service.create_assistant(
            graph_id=graph_id,
            name=name,
            config=config,
            metadata=metadata,
        )

    async def update_assistant(
        self,
        assistant_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update an assistant in the database."""
        return await self._service.update_assistant(assistant_id, updates)

    async def delete_assistant(self, assistant_id: str) -> bool:
        """Delete an assistant from the database."""
        return await self._service.delete_assistant(assistant_id)

    # =========================================================================
    # Agent listing (from agents module)
    # =========================================================================

    def list_agents(self) -> list[dict[str, Any]]:
        """List all available agents from the agents module."""
        return self._service.list_agents()

    def get_agent_info(self, agent_id: str) -> dict[str, Any] | None:
        """Get info for a specific agent."""
        return self._service.get_agent_info(agent_id)

    def get_default_agent_id(self) -> str:
        """Get the default agent ID."""
        return self._service.get_default_agent_id()

    # =========================================================================
    # Graph/config resolution
    # =========================================================================

    async def get_graph_and_config(self, agent_id: str) -> tuple[str, dict[str, Any]]:
        """Resolve agent ID to graph ID and config."""
        return await self._service.get_graph_and_config(agent_id)

    async def get_configured_agent(
        self,
        agent_id: str,
        agent_config: dict[str, Any] | None = None,
    ):
        """Get agent with dynamic configuration applied."""
        return await self._service.get_configured_agent(agent_id, agent_config)


# Singleton instance
_agent_controller: AgentController | None = None


def get_agent_controller() -> AgentController:
    """Get the singleton AgentController instance."""
    global _agent_controller
    if _agent_controller is None:
        _agent_controller = AgentController()
    return _agent_controller

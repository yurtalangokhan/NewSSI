"""Agent domain service - handles agent registry and management."""

import logging
from typing import Any

from schema import AgentInfo

logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing agent instances and configurations."""

    def __init__(self, agent_registry: dict[str, Any]):
        self._registry = agent_registry

    async def get_agent(self, agent_id: str) -> Any:
        """Get an agent by ID."""
        from agents import get_agent

        return get_agent(agent_id)

    async def get_all_agent_info(self) -> list[AgentInfo]:
        """List all available agents."""
        from agents import get_all_agent_info

        return get_all_agent_info()

    async def load_agent(self, agent_id: str) -> None:
        """Load a lazy agent."""
        from agents import load_agent

        await load_agent(agent_id)

    async def get_default_agent(self) -> str:
        """Get the default agent key."""
        from agents import DEFAULT_AGENT

        return DEFAULT_AGENT

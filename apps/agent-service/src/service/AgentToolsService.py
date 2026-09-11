"""Agent Tools Service - manages tool bindings to agents."""

from __future__ import annotations

from typing import Any

from core.db.repositories import AgentToolsRepository, MCPToolRepository
from core.logger import get_logger

logger = get_logger(__name__)


class AgentToolsService:
    """Service for managing agent-tool bindings."""

    _instance: AgentToolsService | None = None

    def __init__(self):
        self._repo = AgentToolsRepository()
        self._tool_repo = MCPToolRepository()

    @classmethod
    def get_instance(cls) -> AgentToolsService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def get_tools_for_agent(self, agent_id: int) -> list[dict[str, Any]]:
        bindings = await self._repo.list_by_agent(agent_id)
        tools = []
        for binding in bindings:
            tool = await self._tool_repo.get_by_id(binding["tool_id"])
            if tool:
                tools.append(
                    {
                        **tool,
                        "config": binding.get("config", {}),
                        "order_index": binding.get("order_index", 0),
                        "binding_id": binding["id"],
                    }
                )
        return tools

    async def add_tool_to_agent(
        self,
        agent_id: int,
        tool_id: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = await self._repo.get(agent_id, tool_id)
        if existing:
            return existing
        return await self._repo.add_tool(agent_id, tool_id, config)

    async def add_tools_to_agent(
        self,
        agent_id: int,
        tool_ids: list[str],
    ) -> list[dict[str, Any]]:
        return await self._repo.add_tools(agent_id, tool_ids)

    async def remove_tool_from_agent(self, agent_id: int, tool_id: str) -> bool:
        return await self._repo.remove_tool(agent_id, tool_id)

    async def remove_all_tools_from_agent(self, agent_id: int) -> int:
        return await self._repo.remove_all_tools(agent_id)

    async def reorder_tools(
        self,
        agent_id: int,
        tool_ids: list[str],
    ) -> list[dict[str, Any]]:
        return await self._repo.reorder_tools(agent_id, tool_ids)

    async def get_tool_configs(self, agent_id: int) -> dict[str, dict[str, Any]]:
        bindings = await self._repo.list_by_agent(agent_id)
        configs = {}
        for binding in bindings:
            tool_id = binding["tool_id"]
            tool = await self._tool_repo.get_by_id(tool_id)
            if tool:
                configs[tool["name"]] = binding.get("config", {})
        return configs

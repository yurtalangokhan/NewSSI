from typing import Any

from error_contract import BadRequestError, NotFoundError

from service.orchestration.agent_tools_service import AgentToolsService


class AgentToolsApplicationService:
    """Framework-free use cases for this JSON surface."""

    async def get_agent_tools(self, agent_id: int, service: AgentToolsService) -> list[dict[str, Any]]:
        return await service.get_tools_for_agent(agent_id)

    async def add_tools_to_agent(
        self, agent_id: int, request: dict[str, Any], service: AgentToolsService
    ) -> list[dict[str, Any]]:
        tool_ids = request.get("tool_ids", [])
        if not tool_ids:
            raise BadRequestError(message_key="tool.ids_required")
        return await service.add_tools_to_agent(agent_id, tool_ids)

    async def add_tool_to_agent(self, agent_id: int, tool_id: str, service: AgentToolsService) -> dict[str, Any]:
        return await service.add_tool_to_agent(agent_id, tool_id)

    async def remove_tool_from_agent(self, agent_id: int, tool_id: str, service: AgentToolsService) -> dict[str, Any]:
        removed = await service.remove_tool_from_agent(agent_id, tool_id)
        if not removed:
            raise NotFoundError(message_key="tool.binding_not_found")
        return {"status": "ok", "agent_id": agent_id, "tool_id": tool_id}

    async def reorder_agent_tools(
        self, agent_id: int, request: dict[str, Any], service: AgentToolsService
    ) -> list[dict[str, Any]]:
        tool_ids = request.get("tool_ids", [])
        return await service.reorder_tools(agent_id, tool_ids)

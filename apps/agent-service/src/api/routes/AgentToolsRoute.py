"""Agent Tools routes - bind tools to assistants."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_user
from service.AgentToolsService import AgentToolsService

router = APIRouter(prefix="/assistants", tags=["agent-tools"], dependencies=[Depends(require_user)])


def _get_service() -> AgentToolsService:
    return AgentToolsService.get_instance()


@router.get("/{agent_id}/tools")
async def get_agent_tools(
    agent_id: int,
    service: AgentToolsService = Depends(_get_service),
) -> list[dict[str, Any]]:
    return await service.get_tools_for_agent(agent_id)


@router.post("/{agent_id}/tools")
async def add_tools_to_agent(
    agent_id: int,
    request: dict[str, Any],
    service: AgentToolsService = Depends(_get_service),
) -> list[dict[str, Any]]:
    tool_ids = request.get("tool_ids", [])
    if not tool_ids:
        raise HTTPException(status_code=400, detail="tool_ids required")
    return await service.add_tools_to_agent(agent_id, tool_ids)


@router.post("/{agent_id}/tools/{tool_id}")
async def add_tool_to_agent(
    agent_id: int,
    tool_id: str,
    service: AgentToolsService = Depends(_get_service),
) -> dict[str, Any]:
    return await service.add_tool_to_agent(agent_id, tool_id)


@router.delete("/{agent_id}/tools/{tool_id}")
async def remove_tool_from_agent(
    agent_id: int,
    tool_id: str,
    service: AgentToolsService = Depends(_get_service),
) -> dict[str, Any]:
    removed = await service.remove_tool_from_agent(agent_id, tool_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Tool binding not found")
    return {"status": "ok", "agent_id": agent_id, "tool_id": tool_id}


@router.put("/{agent_id}/tools/reorder")
async def reorder_agent_tools(
    agent_id: int,
    request: dict[str, Any],
    service: AgentToolsService = Depends(_get_service),
) -> list[dict[str, Any]]:
    tool_ids = request.get("tool_ids", [])
    return await service.reorder_tools(agent_id, tool_ids)

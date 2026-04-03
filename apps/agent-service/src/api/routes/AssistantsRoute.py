"""
Assistant CRUD routes.

Endpoints: POST /assistants/search, GET /assistants/{id},
POST /assistants, PUT|PATCH /assistants/{id}, DELETE /assistants/{id}
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from service.AssistantAgentService import AssistantAgentService
from service.AuthService import verify_bearer
from service.Schemas import (
    AssistantCreateRequest,
    AssistantSearchRequest,
    AssistantUpdateRequest,
)

from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/assistants", tags=["assistants"], dependencies=[Depends(verify_bearer)])


# =============================================================================
# Helpers
# =============================================================================


def agent_to_assistant(agent_id: str, agent_description: str) -> dict:
    """Convert an agent to LangGraph Assistant format."""
    now = datetime.now(UTC).isoformat()
    return {
        "assistant_id": agent_id,
        "graph_id": agent_id,
        "name": agent_id,
        "config": {},
        "metadata": {
            "description": agent_description,
            "_x_oap_is_default": True,
        },
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }


def _get_service() -> AssistantAgentService:
    return AssistantAgentService.get_instance()


# =============================================================================
# Routes
# =============================================================================


@router.post("/search")
async def search_assistants(
    request: AssistantSearchRequest = AssistantSearchRequest(),
) -> list[dict]:
    """
    Search for assistants. Returns all available agents as assistants.
    Compatible with @langchain/langgraph-sdk client.assistants.search()
    """
    service = _get_service()

    all_agents = service.list_agents()
    assistants: list[dict] = []

    for agent_info in all_agents:
        if request.graph_id and agent_info.get("key") != request.graph_id:
            continue
        assistants.append(agent_to_assistant(agent_info["key"], agent_info.get("description", "")))

    stored = await service.list_assistants()
    for assistant in stored:
        if request.graph_id and assistant.get("graph_id") != request.graph_id:
            continue

        if request.metadata:
            matches = True
            for k, v in request.metadata.items():
                if assistant.get("metadata", {}).get(k) != v:
                    matches = False
                    break
            if not matches:
                continue

        assistants.append(assistant)

    start = request.offset
    end = min(start + request.limit, len(assistants))
    if start >= len(assistants):
        return []

    return assistants[start:end]


@router.get("/{assistant_id}")
async def get_assistant(assistant_id: str) -> dict:
    """
    Get a specific assistant by ID.
    Compatible with @langchain/langgraph-sdk client.assistants.get()
    """
    service = _get_service()

    stored = await service.get_assistant(assistant_id)
    if stored:
        return stored

    all_agents = service.list_agents()
    for agent_info in all_agents:
        if agent_info.get("key") == assistant_id:
            return agent_to_assistant(agent_info["key"], agent_info.get("description", ""))

    raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")


@router.post("")
async def create_assistant(request: AssistantCreateRequest) -> dict:
    """
    Create a new assistant.
    Compatible with @langchain/langgraph-sdk client.assistants.create()
    """
    service = _get_service()

    all_agents = service.list_agents()
    agent_exists = any(a.get("key") == request.graph_id for a in all_agents)

    if not agent_exists:
        raise HTTPException(status_code=404, detail=f"Graph {request.graph_id} not found")

    return await service.create_assistant(
        graph_id=request.graph_id,
        name=request.name,
        config=request.config,
        metadata=request.metadata,
    )


@router.put("/{assistant_id}")
@router.patch("/{assistant_id}")
async def update_assistant(assistant_id: str, request: AssistantUpdateRequest) -> dict:
    """
    Update an assistant.
    Compatible with @langchain/langgraph-sdk client.assistants.update()
    """
    service = _get_service()

    updates: dict = {}
    if request.name:
        updates["name"] = request.name
    if request.config:
        updates["config"] = request.config
    if request.metadata:
        updates["metadata"] = request.metadata

    updated = await service.update_assistant(assistant_id, updates)
    if updated:
        return updated

    all_agents = service.list_agents()
    for agent_info in all_agents:
        if agent_info.get("key") == assistant_id:
            raise HTTPException(status_code=403, detail="Cannot update system templates")

    raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")


@router.delete("/{assistant_id}")
async def delete_assistant(assistant_id: str) -> dict:
    """
    Delete an assistant.
    Compatible with @langchain/langgraph-sdk client.assistants.delete()
    """
    service = _get_service()

    deleted = await service.delete_assistant(assistant_id)
    if deleted:
        return {"status": "ok", "assistant_id": assistant_id}

    all_agents = service.list_agents()
    for agent_info in all_agents:
        if agent_info.get("key") == assistant_id:
            return {
                "status": "ok",
                "assistant_id": assistant_id,
                "detail": "System template not deleted",
            }

    raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")

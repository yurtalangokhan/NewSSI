"""
Assistant CRUD routes.

Endpoints: POST /assistants/search, GET /assistants/{id},
POST /assistants, PUT|PATCH /assistants/{id}, DELETE /assistants/{id}
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException

from agents import get_all_agent_info
from service.auth import verify_bearer
from service.schemas import (
    AssistantCreateRequest,
    AssistantSearchRequest,
    AssistantUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_bearer)])


# =============================================================================
# Helpers
# =============================================================================

def agent_to_assistant(agent_id: str, agent_description: str) -> Dict:
    """Convert an agent to LangGraph Assistant format."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "assistant_id": agent_id,
        "graph_id": agent_id,
        "name": agent_id,
        "config": {},
        "metadata": {
            "description": agent_description,
            "_x_oap_is_default": True,  # Required for open-agent-platform graph selection
        },
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }


# =============================================================================
# Routes
# =============================================================================

@router.post("/assistants/search")
async def search_assistants(
    request: AssistantSearchRequest = AssistantSearchRequest(),
) -> List[Dict]:
    """
    Search for assistants. Returns all available agents as assistants.
    Compatible with @langchain/langgraph-sdk client.assistants.search()
    """
    from .store import list_assistants_from_store

    all_agents = get_all_agent_info()
    assistants: list[Dict] = []

    for agent_info in all_agents:
        if request.graph_id and agent_info.key != request.graph_id:
            continue
        assistants.append(agent_to_assistant(agent_info.key, agent_info.description))

    stored = await list_assistants_from_store()
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


@router.get("/assistants/{assistant_id}")
async def get_assistant(assistant_id: str) -> Dict:
    """
    Get a specific assistant by ID.
    Compatible with @langchain/langgraph-sdk client.assistants.get()
    """
    from .store import get_assistant_from_store

    stored = await get_assistant_from_store(assistant_id)
    if stored:
        return stored

    all_agents = get_all_agent_info()
    for agent_info in all_agents:
        if agent_info.key == assistant_id:
            return agent_to_assistant(agent_info.key, agent_info.description)

    raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")


@router.post("/assistants")
async def create_assistant(request: AssistantCreateRequest) -> Dict:
    """
    Create a new assistant.
    Compatible with @langchain/langgraph-sdk client.assistants.create()
    """
    from .store import save_assistant_async

    all_agents = get_all_agent_info()
    agent_exists = any(a.key == request.graph_id for a in all_agents)

    if not agent_exists:
        raise HTTPException(status_code=404, detail=f"Graph {request.graph_id} not found")

    now = datetime.now(timezone.utc).isoformat()
    assistant_id = str(uuid.uuid4())
    name = request.name or f"{request.graph_id}-{assistant_id[:8]}"

    assistant = {
        "assistant_id": assistant_id,
        "graph_id": request.graph_id,
        "name": name,
        "config": request.config or {},
        "metadata": request.metadata or {},
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }

    await save_assistant_async(assistant)
    return assistant


@router.put("/assistants/{assistant_id}")
@router.patch("/assistants/{assistant_id}")
async def update_assistant(assistant_id: str, request: AssistantUpdateRequest) -> Dict:
    """
    Update an assistant.
    Compatible with @langchain/langgraph-sdk client.assistants.update()
    """
    from .store import update_assistant_in_store

    updates: dict = {}
    if request.name:
        updates["name"] = request.name
    if request.config:
        updates["config"] = request.config
    if request.metadata:
        updates["metadata"] = request.metadata

    updated = await update_assistant_in_store(assistant_id, updates)
    if updated:
        return updated

    all_agents = get_all_agent_info()
    for agent_info in all_agents:
        if agent_info.key == assistant_id:
            raise HTTPException(status_code=403, detail="Cannot update system templates")

    raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")


@router.delete("/assistants/{assistant_id}")
async def delete_assistant(assistant_id: str) -> Dict:
    """
    Delete an assistant.
    Compatible with @langchain/langgraph-sdk client.assistants.delete()
    """
    from .store import delete_assistant_from_store

    deleted = await delete_assistant_from_store(assistant_id)
    if deleted:
        return {"status": "ok", "assistant_id": assistant_id}

    all_agents = get_all_agent_info()
    for agent_info in all_agents:
        if agent_info.key == assistant_id:
            return {
                "status": "ok",
                "assistant_id": assistant_id,
                "detail": "System template not deleted",
            }

    raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")

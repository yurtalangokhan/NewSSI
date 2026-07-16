"""Agent Definitions CRUD API.

Endpoints:
  POST   /agent-definitions              - Create a new dynamic agent definition
  GET    /agent-definitions              - List all agent definitions
  GET    /agent-definitions/{id}         - Get a single agent definition
  PUT    /agent-definitions/{id}         - Update an agent definition
  DELETE /agent-definitions/{id}         - Delete an agent definition
  GET    /agent-definitions/schemas/list - Available graph schemas
  GET    /agent-definitions/brains/list  - Available brain types
  GET    /agent-definitions/memory/list  - Available memory types
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from agents.storage.repository import AgentDefinitionRepository
from api.dependencies import require_permission, require_user
from domain.agents.service import (
    AgentDefinitionService,
    BrainTypeService,
    GraphSchemaService,
    MemoryTypeService,
)
from models.agent_definitions import (
    CreateAgentDefinitionRequest,
    UpdateAgentDefinitionRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agent-definitions",
    tags=["agent-definitions"],
    dependencies=[Depends(require_user)],
)


def _definition_to_dict(d) -> dict[str, Any]:
    """Serialize an AgentDefinitionModel to a response dict."""
    return {
        "id": str(d.id),
        "persona_id": d.persona_id,
        "name": d.name,
        "agent_type": d.agent_type,
        "description": d.description,
        "graph_schema": d.graph_schema,
        "brain_type": d.brain_type,
        "memory_type": d.memory_type,
        "system_prompt": d.system_prompt,
        "model": d.model,
        "mcp_tools": d.mcp_tools or [],
        "rag_config": d.rag_config or {"document_processing": [], "knowledge_graph": []},
        "sub_agents": d.sub_agents or [],
        "supervisor_prompt": d.supervisor_prompt,
        "stages": d.stages or [],
        "pipeline_prompt": d.pipeline_prompt,
        "reflection_prompt": d.reflection_prompt,
        "max_iterations": d.max_iterations,
        "version": d.version,
        "tags": d.tags or [],
        "is_active": d.is_active,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


def _get_service() -> AgentDefinitionService:
    return AgentDefinitionService(AgentDefinitionRepository())


# ---------------------------------------------------------------------------
# Metadata endpoints (must come before /{id} to avoid route shadowing)
# ---------------------------------------------------------------------------


@router.get("/schemas/list")
async def list_schemas(_user=Depends(require_permission("agent:list"))) -> list[dict[str, Any]]:
    """Return all available graph schemas with their capabilities."""
    return GraphSchemaService.get_available_schemas()


@router.get("/brains/list")
async def list_brain_types(_user=Depends(require_permission("agent:list"))) -> list[dict[str, Any]]:
    """Return all available brain types."""
    return BrainTypeService.get_available_brain_types()


@router.get("/memory/list")
async def list_memory_types(_user=Depends(require_permission("agent:list"))) -> list[dict[str, Any]]:
    """Return all available memory types."""
    return MemoryTypeService.get_available_memory_types()


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent_definition(
    body: CreateAgentDefinitionRequest,
    _user=Depends(require_permission("agent:create")),
) -> dict[str, Any]:
    """Create a new agent definition."""
    service = _get_service()
    try:
        definition = await service.create_agent_definition(
            name=body.name,
            persona_id=None,
            graph_schema=body.graph_schema,
            brain_type=body.brain_type,
            memory_type=body.memory_type,
            system_prompt=body.system_prompt,
            model=body.model,
            mcp_tools=body.mcp_tools,
            rag_config=body.rag_config,
            sub_agents=[sa.model_dump() for sa in body.sub_agents],
            supervisor_prompt=body.supervisor_prompt,
            stages=[s.model_dump() for s in body.stages],
            pipeline_prompt=body.pipeline_prompt,
            reflection_prompt=body.reflection_prompt,
            max_iterations=body.max_iterations,
            description=body.description,
            tags=body.tags,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return _definition_to_dict(definition)


@router.get("")
async def list_agent_definitions(
    graph_schema: str | None = None,
    active_only: bool = True,
    _user=Depends(require_permission("agent:list")),
) -> list[dict[str, Any]]:
    """List all agent definitions, optionally filtered by graph_schema."""
    service = _get_service()
    definitions = await service.list_agent_definitions(
        graph_schema=graph_schema,
        active_only=active_only,
    )
    return [_definition_to_dict(d) for d in definitions]


@router.get("/{definition_id}")
async def get_agent_definition(
    definition_id: UUID,
    _user=Depends(require_permission("agent:read")),
) -> dict[str, Any]:
    """Get a single agent definition by ID."""
    service = _get_service()
    definition = await service.get_agent_definition(definition_id)
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent definition {definition_id} not found",
        )
    return _definition_to_dict(definition)


@router.put("/{definition_id}")
async def update_agent_definition(
    definition_id: UUID,
    body: UpdateAgentDefinitionRequest,
    _user=Depends(require_permission("agent:update")),
) -> dict[str, Any]:
    """Update an agent definition. Only provided fields are updated."""
    service = _get_service()

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    try:
        definition = await service.update_agent_definition(definition_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent definition {definition_id} not found",
        )
    return _definition_to_dict(definition)


@router.delete("/{definition_id}", status_code=status.HTTP_200_OK)
async def delete_agent_definition(
    definition_id: UUID,
    _user=Depends(require_permission("agent:delete")),
) -> dict[str, str]:
    """Delete an agent definition."""
    service = _get_service()
    deleted = await service.delete_agent_definition(definition_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent definition {definition_id} not found",
        )
    return {"status": "deleted", "id": str(definition_id)}

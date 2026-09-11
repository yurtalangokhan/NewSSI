"""Agent Definitions CRUD API.

Endpoints:
  POST   /agent-definitions                    - Create a new dynamic agent definition
  GET    /agent-definitions                    - List all agent definitions
  POST   /agent-definitions/validate-composition     - Validate agent composition
  POST   /agent-definitions/available-for-composition - List agents for composition (with schema filter)
  POST   /agent-definitions/validate-flow            - Validate a FlowSpec without persisting
  GET    /agent-definitions/{id}/composition-info    - Get hierarchical composition structure
  PUT    /agent-definitions/{id}/sub-agents          - Update sub-agents with validation
  GET    /agent-definitions/{id}               - Get a single agent definition
  PUT    /agent-definitions/{id}               - Update an agent definition
  DELETE /agent-definitions/{id}               - Delete an agent definition
  GET    /agent-definitions/schemas/list      - Available graph schemas
  GET    /agent-definitions/brains/list       - Available brain types
  GET    /agent-definitions/memory/list       - Available memory types

IMPORTANT: Route order matters! Specific literal routes MUST come before generic {id} routes.
- Metadata routes: schemas/list, brains/list, memory/list
- CRUD routes: POST "", GET ""
- Specific composition routes: validate-composition, available-for-composition
- Flow routes: validate-flow
- Routes with path params but specific: {id}/composition-info, {id}/sub-agents
- Generic routes: {id}, {id}, {id}
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from i18n import t
from pydantic import ValidationError

from api.dependencies import require_permission, require_user
from core.logger import get_logger
from domain.agents.service import (
    AgentDefinitionService,
    BrainTypeService,
    GraphSchemaService,
    MemoryTypeService,
)
from domain.flows.agent_expansion import AgentExpansionError, expand_agent_definition
from models.agent_definitions import (
    CreateAgentDefinitionRequest,
    UpdateAgentDefinitionRequest,
)
from repository.agent_definition_repository import AgentDefinitionRepository

logger = get_logger(__name__)

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
        "sub_agent_ids": d.sub_agent_ids or [],
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


def _serialize_definition_for_composition(
    d, depth: int, persona_names: dict[int, str]
) -> dict[str, Any]:
    """Serialize an agent definition for the composition picker.

    Prefers the linked persona's real display name over the internal
    ``AgentDefinitionModel.name`` placeholder (e.g. "persona-15"), and
    includes a compact ``preview`` string for hover tooltips.
    """
    from domain.agents.service import build_agent_preview_text

    display_name = persona_names.get(d.persona_id, d.name) if d.persona_id else d.name
    return {
        "id": str(d.id),
        "name": display_name,
        "graph_schema": d.graph_schema,
        "status": "active" if d.is_active else "inactive",
        "depth": depth,
        "preview": build_agent_preview_text(d),
    }


def _normalize_schema_name(schema: str | None) -> str | None:
    """Normalize schema names for case-insensitive comparisons."""
    if not schema:
        return None
    return schema.strip().upper()


def _filter_available_agents_by_schema(
    agents: list[dict[str, Any]],
    schema: str | None,
) -> list[dict[str, Any]]:
    """Filter available agents by target composition schema.

    Flow-backed agents are excluded unconditionally, even when no schema
    filter is requested — flows are not composable as sub-agents (design
    spec 5.4). This keeps classic-agent composition acyclic by construction:
    a flow can reference a classic agent, never the reverse.
    """
    agents = [a for a in agents if str(a.get("graph_schema", "")).upper() != "FLOW"]

    normalized_schema = _normalize_schema_name(schema)
    if not normalized_schema:
        return agents

    filtered: list[dict[str, Any]] = []
    for agent in agents:
        schema_upper = str(agent.get("graph_schema", "")).upper()

        if normalized_schema == "SUPERVISOR" and schema_upper in (
            "REACT",
            "PLAN_EXECUTE",
            "SUPERVISOR",
        ):
            filtered.append(agent)
        elif normalized_schema == "PIPELINE" and schema_upper not in ("SUPERVISOR", "PIPELINE"):
            filtered.append(agent)

    return filtered


# =========================================================================
# METADATA ENDPOINTS (must come first - literal paths)
# =========================================================================


@router.get("/schemas/list")
async def list_schemas(_user=Depends(require_permission("agent:list"))) -> list[dict[str, Any]]:
    """Return all available graph schemas with their capabilities."""
    return GraphSchemaService.get_available_schemas()


@router.get("/brains/list")
async def list_brain_types(_user=Depends(require_permission("agent:list"))) -> list[dict[str, Any]]:
    """Return all available brain types."""
    return BrainTypeService.get_available_brain_types()


@router.get("/memory/list")
async def list_memory_types(
    _user=Depends(require_permission("agent:list")),
) -> list[dict[str, Any]]:
    """Return all available memory types."""
    return MemoryTypeService.get_available_memory_types()


# =========================================================================
# BASIC CRUD (create, list - no path params)
# =========================================================================


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent_definition(
    body: CreateAgentDefinitionRequest,
    user=Depends(require_permission("agent:create")),
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
            sub_agent_ids=body.sub_agent_ids,
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

    if body.graph_schema == "flow":
        from domain.flows.audit import get_flow_audit_emitter

        await get_flow_audit_emitter().emit(
            "flow:created",
            definition.id,
            user=user,
            details={"node_count": 0, "edge_count": 0},
        )

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


# =========================================================================
# COMPOSITION ENDPOINTS (specific literal paths - must come BEFORE generic /{id})
# =========================================================================


@router.post("/validate-composition")
async def validate_composition(
    body: dict[str, Any],
    _user=Depends(require_permission("agent:read")),
) -> dict[str, Any]:
    """
    Validate agent composition before saving.

    Request body:
    {
        "agent_id": UUID (null if creating new),
        "graph_schema": str (SUPERVISOR, PIPELINE, etc.),
        "sub_agent_ids": [UUID, UUID, ...]
    }

    Returns: {
        "valid": bool,
        "errors": [str],
        "warnings": [str],
        "depth": int
    }
    """
    try:
        agent_id = body.get("agent_id")
        if agent_id:
            agent_id = UUID(agent_id)

        graph_schema = body.get("graph_schema")
        if not graph_schema:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=t("agent.graph_schema_required"),
            )

        sub_agent_ids_raw = body.get("sub_agent_ids", [])
        sub_agent_ids = []
        for sid in sub_agent_ids_raw:
            try:
                sub_agent_ids.append(UUID(sid))
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=t("agent.invalid_uuid", id=sid),
                )

        service = _get_service()
        result = await service.validate_composition(
            agent_id=agent_id,
            graph_schema=graph_schema,
            sub_agent_ids=sub_agent_ids,
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Validation error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/available-for-composition")
async def get_available_for_composition(
    body: dict[str, Any],
    _user=Depends(require_permission("agent:read")),
) -> list[dict[str, Any]]:
    """
    List all agents available for composition as sub-agents.

    Request body (all optional):
    {
        "schema": "SUPERVISOR" | "PIPELINE" (optional, filter eligible agents),
        "exclude_ids": [UUID, ...] (optional, exclude certain agents)
    }

    Returns:
    [
        {
            "id": str,
            "name": str,
            "graph_schema": str,
            "status": "active" | "inactive",
            "depth": int,
            "preview": str
        }
    ]
    """
    try:
        from core.db.repositories.persona_repo import PersonaRepository

        schema = body.get("schema")
        exclude_ids_raw = body.get("exclude_ids", [])
        exclude_ids = set()

        for eid in exclude_ids_raw:
            try:
                exclude_ids.add(UUID(eid))
            except (ValueError, TypeError):
                logger.warning(f"Invalid UUID in exclude_ids: {eid}")

        service = _get_service()

        # Get all active agents
        definitions = await service.list_agent_definitions(active_only=True)
        persona_names = {p["id"]: p["name"] for p in await PersonaRepository().list_all()}

        result = []
        for d in definitions:
            # Skip excluded IDs
            if d.id in exclude_ids:
                continue

            # Get depth
            try:
                info = await service.get_composition_info(d.id)
                depth = info.get("depth", 0)
            except Exception:
                depth = 0

            result.append(_serialize_definition_for_composition(d, depth, persona_names))

        # Filter by schema if provided.
        # SUPERVISOR: only tool-capable single agents (REACT, PLAN_EXECUTE).
        # PIPELINE: disallow nested multi-agent schemas (SUPERVISOR, PIPELINE).
        result = _filter_available_agents_by_schema(result, schema)

        return result

    except Exception as e:
        logger.error(f"Available agents error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =========================================================================
# FLOW VALIDATION (specific literal path - must come BEFORE generic /{id})
# =========================================================================


@router.post("/validate-flow")
async def validate_flow(
    body: dict[str, Any],
    user=Depends(require_permission("flow:read")),
) -> dict[str, Any]:
    """
    Validate a FlowSpec without persisting it.

    Request body: {"flow_spec": <FlowSpec JSON>}

    Returns: {"valid": bool, "errors": [{code, message, node_id, edge_id}], "warnings": [...]}
    """
    from domain.flows.resolvers import ResolverContext
    from domain.flows.service import FlowService
    from models.flows import FlowSpec

    try:
        spec = FlowSpec.model_validate(body.get("flow_spec", body))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    service = FlowService()
    context = ResolverContext(user_id=user.user_id, access_token=user.access_token)
    result = await service.validate_flow(spec, context)

    return {
        "valid": result.valid,
        "errors": [e.to_dict() for e in result.errors],
        "warnings": [w.to_dict() for w in result.warnings],
    }


# =========================================================================
# COMPOSITION INFO & SUB-AGENTS (path params but specific - before generic /{id})
# =========================================================================


@router.get("/{definition_id}/composition-info")
async def get_composition_info(
    definition_id: UUID,
    _user=Depends(require_permission("agent:read")),
) -> dict[str, Any]:
    """
    Get hierarchical composition structure for UI preview.

    Returns:
    {
        "id": str,
        "name": str,
        "graph_schema": str,
        "status": "active" | "inactive",
        "depth": int,
        "sub_agents": [
            {same structure recursively}
        ]
    }
    """
    try:
        service = _get_service()
        info = await service.get_composition_info(definition_id)
        return info

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Composition info error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{definition_id}/sub-agents")
async def update_sub_agents(
    definition_id: UUID,
    body: dict[str, Any],
    _user=Depends(require_permission("agent:update")),
) -> dict[str, Any]:
    """
    Update an agent's sub-agent references with validation + cascade invalidation.

    Request body:
    {
        "sub_agent_ids": [UUID, UUID, ...]
    }

    Returns:
    Updated agent definition dict
    """
    try:
        sub_agent_ids_raw = body.get("sub_agent_ids", [])
        if not isinstance(sub_agent_ids_raw, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=t("agent.sub_agent_ids_must_be_array"),
            )

        sub_agent_ids = []
        for sid in sub_agent_ids_raw:
            try:
                sub_agent_ids.append(UUID(sid))
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=t("agent.invalid_uuid", id=sid),
                )

        service = _get_service()
        updated = await service.update_sub_agents(definition_id, sub_agent_ids)

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=t("agent.definition_not_found", definition_id=definition_id),
            )

        return _definition_to_dict(updated)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update sub-agents error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{definition_id}/expand")
async def expand_agent_definition_route(
    definition_id: UUID,
    _user=Depends(require_permission("agent:create")),
) -> dict[str, Any]:
    """Materialize an existing agent onto a flow canvas as separate
    model/tools/memory/input nodes (single-brain and Pipeline sources) or a
    detached Supervisor node (Supervisor sources) — design spec
    .tmp/2026-08-27-agent-flow-expansion-design.md §7.3.
    """
    try:
        nodes, edges = await expand_agent_definition(definition_id, AgentDefinitionRepository())
    except AgentExpansionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Agent expansion error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return {
        "nodes": [n.model_dump(by_alias=True) for n in nodes],
        "edges": [e.model_dump(by_alias=True) for e in edges],
    }


# =========================================================================
# GENERIC CRUD (get, update, delete by ID - must come LAST)
# =========================================================================


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
            detail=t("agent.definition_not_found", definition_id=definition_id),
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
            detail=t("agent.no_fields_to_update"),
        )

    try:
        definition = await service.update_agent_definition(definition_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("agent.definition_not_found", definition_id=definition_id),
        )
    return _definition_to_dict(definition)


@router.delete("/{definition_id}", status_code=status.HTTP_200_OK)
async def delete_agent_definition(
    definition_id: UUID,
    user=Depends(require_permission("agent:delete")),
) -> dict[str, str]:
    """Delete an agent definition."""
    service = _get_service()

    existing_definition = await service.get_agent_definition(definition_id)
    is_flow_backed = bool(existing_definition and existing_definition.graph_schema == "flow")

    last_version_no = None
    if is_flow_backed:
        # agent_flow_versions cascades on delete (Task 14) — the version
        # history is gone the moment delete_agent_definition succeeds below,
        # so the last version number must be read before that call.
        from repository.flow_version_repository import FlowVersionRepository

        versions = await FlowVersionRepository().list_versions(definition_id)
        if versions:
            last_version_no = versions[0].version_no  # list_versions orders newest first

    deleted = await service.delete_agent_definition(definition_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("agent.definition_not_found", definition_id=definition_id),
        )

    if is_flow_backed:
        from domain.flows.audit import get_flow_audit_emitter

        await get_flow_audit_emitter().emit(
            "flow:deleted",
            definition_id,
            user=user,
            details={"last_version_no": last_version_no},
        )

    return {"status": "deleted", "id": str(definition_id)}

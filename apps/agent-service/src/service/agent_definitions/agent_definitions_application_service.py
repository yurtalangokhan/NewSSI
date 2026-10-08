from __future__ import annotations

from typing import Any
from uuid import UUID

from error_contract import (
    ApplicationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
)
from pydantic import ValidationError

from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import flow_version_repository, persona_repository
from schemas.agent_definitions import (
    AgentDefinitionResponse,
    ComponentTypeItemResponse,
    CreateAgentDefinitionRequest,
    GraphSchemaItemResponse,
    UpdateAgentDefinitionRequest,
)
from schemas.common import StatusResponse
from service.agent_definitions.agent_definition_service import (
    AgentDefinitionService,
    BrainTypeService,
    GraphSchemaService,
    MemoryTypeService,
)
from service.auth.auth_service import AuthenticatedUser
from service.flows.agent_expansion import AgentExpansionError, expand_agent_definition

logger = get_logger(__name__)


def definition_to_dict(d: Any) -> dict[str, Any]:
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


def serialize_definition_for_composition(d: Any, depth: int, persona_names: dict[int, str]) -> dict[str, Any]:
    """Serialize an agent definition for the composition picker.

    Prefers the linked persona's real display name over the internal
    ``AgentDefinitionModel.name`` placeholder (e.g. "persona-15"), and
    includes a compact ``preview`` string for hover tooltips.
    """
    from service.agent_definitions.agent_definition_service import build_agent_preview_text

    display_name = persona_names.get(d.persona_id, d.name) if d.persona_id else d.name
    return {
        "id": str(d.id),
        "name": display_name,
        "graph_schema": d.graph_schema,
        "status": "active" if d.is_active else "inactive",
        "depth": depth,
        "preview": build_agent_preview_text(d),
    }


def normalize_schema_name(schema: str | None) -> str | None:
    """Normalize schema names for case-insensitive comparisons."""
    if not schema:
        return None
    return schema.strip().upper()


def filter_available_agents_by_schema(agents: list[dict[str, Any]], schema: str | None) -> list[dict[str, Any]]:
    """Filter available agents by target composition schema.

    Flow-backed agents are excluded unconditionally, even when no schema
    filter is requested — flows are not composable as sub-agents (design
    spec 5.4). This keeps classic-agent composition acyclic by construction:
    a flow can reference a classic agent, never the reverse.
    """
    agents = [a for a in agents if str(a.get("graph_schema", "")).upper() != "FLOW"]
    normalized_schema = normalize_schema_name(schema)
    if not normalized_schema:
        return agents
    filtered: list[dict[str, Any]] = []
    for agent in agents:
        schema_upper = str(agent.get("graph_schema", "")).upper()
        if (normalized_schema == "SUPERVISOR" and schema_upper in ("REACT", "PLAN_EXECUTE", "SUPERVISOR")) or (
            normalized_schema == "PIPELINE" and schema_upper not in ("SUPERVISOR", "PIPELINE")
        ):
            filtered.append(agent)
    return filtered


class AgentDefinitionsApplicationService:
    """Framework-free use cases for this JSON surface."""

    def __init__(self, service: AgentDefinitionService | None = None):
        self.domain_service = service if service is not None else AgentDefinitionService()

    async def list_schemas(self) -> list[GraphSchemaItemResponse]:
        """Return all available graph schemas with their capabilities."""
        return GraphSchemaService.get_available_schemas()

    async def list_brain_types(self) -> list[ComponentTypeItemResponse]:
        """Return all available brain types."""
        return BrainTypeService.get_available_brain_types()

    async def list_memory_types(self) -> list[ComponentTypeItemResponse]:
        """Return all available memory types."""
        return MemoryTypeService.get_available_memory_types()

    async def create_agent_definition(
        self, body: CreateAgentDefinitionRequest, user: AuthenticatedUser
    ) -> AgentDefinitionResponse:
        """Create a new agent definition."""
        service = self.domain_service
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
        except ValueError as exc:
            raise BadRequestError(message_key="common.bad_request") from exc
        if body.graph_schema == "flow":
            from service.flows.audit import get_flow_audit_emitter

            await get_flow_audit_emitter().emit(
                "flow:created", definition.id, user=user, details={"node_count": 0, "edge_count": 0}
            )
        return definition_to_dict(definition)

    async def list_agent_definitions(
        self, graph_schema: str | None = None, active_only: bool = True
    ) -> list[dict[str, Any]]:
        """List all agent definitions, optionally filtered by graph_schema."""
        service = self.domain_service
        definitions = await service.list_agent_definitions(graph_schema=graph_schema, active_only=active_only)
        return [definition_to_dict(d) for d in definitions]

    async def validate_composition(self, body: dict[str, Any]) -> dict[str, Any]:
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
                raise BadRequestError(message_key="agent.graph_schema_required")
            sub_agent_ids_raw = body.get("sub_agent_ids", [])
            sub_agent_ids = []
            for sid in sub_agent_ids_raw:
                try:
                    sub_agent_ids.append(UUID(sid))
                except (ValueError, TypeError) as exc:
                    raise BadRequestError(message_key="agent.invalid_uuid", message_params={"id": sid}) from exc
            service = self.domain_service
            result = await service.validate_composition(
                agent_id=agent_id, graph_schema=graph_schema, sub_agent_ids=sub_agent_ids
            )
            return result
        except ValueError as exc:
            raise BadRequestError(message_key="common.bad_request") from exc
        except ApplicationError:
            raise
        except Exception as exc:
            logger.exception("Composition validation failed")
            raise InternalServerError(message_key="common.internal_error") from exc

    async def get_available_for_composition(self, body: dict[str, Any]) -> list[dict[str, Any]]:
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
            schema = body.get("schema")
            exclude_ids_raw = body.get("exclude_ids", [])
            exclude_ids = set()
            for eid in exclude_ids_raw:
                try:
                    exclude_ids.add(UUID(eid))
                except (ValueError, TypeError):
                    logger.warning(f"Invalid UUID in exclude_ids: {eid}")
            service = self.domain_service
            definitions = await service.list_agent_definitions(active_only=True)
            persona_names = {p["id"]: p["name"] for p in await persona_repository().list_all()}
            result = []
            for d in definitions:
                if d.id in exclude_ids:
                    continue
                try:
                    info = await service.get_composition_info(d.id)
                    depth = info.get("depth", 0)
                except Exception:
                    depth = 0
                result.append(serialize_definition_for_composition(d, depth, persona_names))
            result = filter_available_agents_by_schema(result, schema)
            return result
        except ApplicationError:
            raise
        except Exception as exc:
            logger.exception("Available-agent lookup failed")
            raise InternalServerError(message_key="common.internal_error") from exc

    async def validate_flow(self, body: dict[str, Any], user: AuthenticatedUser) -> dict[str, Any]:
        """
        Validate a FlowSpec without persisting it.

        Request body: {"flow_spec": <FlowSpec JSON>}

        Returns: {"valid": bool, "errors": [{code, message, node_id, edge_id}], "warnings": [...]}
        """
        from schemas.flows import FlowSpec
        from service.flows.resolvers import ResolverContext
        from service.flows.service import FlowService

        try:
            spec = FlowSpec.model_validate(body.get("flow_spec", body))
        except ValidationError as exc:
            raise BadRequestError(message_key="common.bad_request") from exc
        service = FlowService()
        context = ResolverContext(user_id=user.user_id, access_token=user.access_token)
        result = await service.validate_flow(spec, context)
        return {
            "valid": result.valid,
            "errors": [e.to_dict() for e in result.errors],
            "warnings": [w.to_dict() for w in result.warnings],
        }

    async def get_composition_info(self, definition_id: UUID) -> dict[str, Any]:
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
            service = self.domain_service
            info = await service.get_composition_info(definition_id)
            return info
        except ValueError as exc:
            raise NotFoundError(message_key="common.not_found") from exc
        except ApplicationError:
            raise
        except Exception as exc:
            logger.exception("Composition-info lookup failed")
            raise InternalServerError(message_key="common.internal_error") from exc

    async def update_sub_agents(self, definition_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
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
                raise BadRequestError(message_key="agent.sub_agent_ids_must_be_array")
            sub_agent_ids = []
            for sid in sub_agent_ids_raw:
                try:
                    sub_agent_ids.append(UUID(sid))
                except (ValueError, TypeError) as exc:
                    raise BadRequestError(message_key="agent.invalid_uuid", message_params={"id": sid}) from exc
            service = self.domain_service
            updated = await service.update_sub_agents(definition_id, sub_agent_ids)
            if not updated:
                raise NotFoundError(
                    message_key="agent.definition_not_found", message_params={"definition_id": definition_id}
                )
            return definition_to_dict(updated)
        except ValueError as exc:
            raise BadRequestError(message_key="common.bad_request") from exc
        except ApplicationError:
            raise
        except Exception as exc:
            logger.exception("Sub-agent update failed")
            raise InternalServerError(message_key="common.internal_error") from exc

    async def expand_agent_definition(self, definition_id: UUID) -> dict[str, Any]:
        """Materialize an existing agent onto a flow canvas as separate
        model/tools/memory/input nodes (single-brain and Pipeline sources) or a
        detached Supervisor node (Supervisor sources) — design spec
        .tmp/2026-08-27-agent-flow-expansion-design.md §7.3.
        """
        try:
            nodes, edges = await expand_agent_definition(definition_id)
        except AgentExpansionError as exc:
            raise BadRequestError(message_key="common.bad_request") from exc
        except ApplicationError:
            raise
        except Exception as exc:
            logger.exception("Agent expansion failed")
            raise InternalServerError(message_key="common.internal_error") from exc
        return {
            "nodes": [n.model_dump(by_alias=True) for n in nodes],
            "edges": [e.model_dump(by_alias=True) for e in edges],
        }

    async def get_agent_definition(self, definition_id: UUID) -> dict[str, Any]:
        """Get a single agent definition by ID."""
        service = self.domain_service
        definition = await service.get_agent_definition(definition_id)
        if not definition:
            raise NotFoundError(
                message_key="agent.definition_not_found", message_params={"definition_id": definition_id}
            )
        return definition_to_dict(definition)

    async def update_agent_definition(self, definition_id: UUID, body: UpdateAgentDefinitionRequest) -> dict[str, Any]:
        """Update an agent definition. Only provided fields are updated."""
        service = self.domain_service
        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise BadRequestError(message_key="agent.no_fields_to_update")
        try:
            definition = await service.update_agent_definition(definition_id, updates)
        except ValueError as exc:
            raise BadRequestError(message_key="common.bad_request") from exc
        if not definition:
            raise NotFoundError(
                message_key="agent.definition_not_found", message_params={"definition_id": definition_id}
            )
        return definition_to_dict(definition)

    async def delete_agent_definition(self, definition_id: UUID, user: AuthenticatedUser) -> StatusResponse:
        """Delete an agent definition."""
        service = self.domain_service
        existing_definition = await service.get_agent_definition(definition_id)
        is_flow_backed = bool(existing_definition and existing_definition.graph_schema == "flow")
        last_version_no = None
        if is_flow_backed:
            versions = await flow_version_repository().list_versions(definition_id)
            if versions:
                last_version_no = versions[0].version_no
        deleted = await service.delete_agent_definition(definition_id)
        if not deleted:
            raise NotFoundError(
                message_key="agent.definition_not_found", message_params={"definition_id": definition_id}
            )
        if is_flow_backed:
            from service.flows.audit import get_flow_audit_emitter

            await get_flow_audit_emitter().emit(
                "flow:deleted", definition_id, user=user, details={"last_version_no": last_version_no}
            )
        return {"status": "deleted", "id": str(definition_id)}

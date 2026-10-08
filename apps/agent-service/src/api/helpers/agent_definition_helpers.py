"""Pure helpers for agent definition routes.

Extracted from ``agent_definitions_route`` to keep the route file focused on
endpoint definitions.
"""

from __future__ import annotations

from typing import Any


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


def filter_available_agents_by_schema(
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

    normalized_schema = normalize_schema_name(schema)
    if not normalized_schema:
        return agents

    filtered: list[dict[str, Any]] = []
    for agent in agents:
        schema_upper = str(agent.get("graph_schema", "")).upper()

        if (
            normalized_schema == "SUPERVISOR"
            and schema_upper
            in (
                "REACT",
                "PLAN_EXECUTE",
                "SUPERVISOR",
            )
        ) or (normalized_schema == "PIPELINE" and schema_upper not in ("SUPERVISOR", "PIPELINE")):
            filtered.append(agent)

    return filtered

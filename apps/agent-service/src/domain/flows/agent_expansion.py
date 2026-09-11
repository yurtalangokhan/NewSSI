"""Materializes an existing AgentDefinitionModel into flow-canvas nodes/edges.

Two strategies, chosen by the source's graph_schema (design spec §6):
- single-brain / pipeline sources become real, visible flow-native nodes
  (this module), reusing the existing node catalog — no new node types.
- supervisor sources stay as the single existing Supervisor node; their
  sub-agents are made a detached copy by recursively cloning DB rows
  (see clone_sub_agent_tree), not by decomposing them onto canvas.

Spec: .tmp/2026-08-27-agent-flow-expansion-design.md
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agents.graphs.schemas import GraphSchemaType
from core.logger import get_logger
from domain.flows.mcp_catalog import CATEGORY_NODE_TYPES, MCP_CATEGORY_BY_KEY
from models.flows import FlowEdge, FlowNode

logger = get_logger(__name__)

# ``CATEGORY_NODE_TYPES`` (category key -> flow-canvas node ``type``) is the
# canonical map from domain/flows/mcp_catalog. ``mail`` is intentionally
# absent there — it needs a bespoke MailTools + MailConfig pair, so a plain
# category node must not be materialized for it.


async def resolve_tool_categories(
    tool_names: list[str], *, service: Any = None
) -> dict[str, list[str]]:
    """Group ``tool_names`` by MCP category, mirroring
    domain/flows/resolvers.py's _resolve_mcp_tools_by_category fallback
    behavior exactly (live MCPToolService, degrading to the builtin table).
    """
    if not tool_names:
        return {}

    name_to_category: dict[str, str] = {}

    try:
        from service.MCPToolService import MCPToolService

        svc = service or MCPToolService.get_instance()
        for category in await svc.list_categories():
            for tool in await svc.get_tools_by_category(category):
                name_to_category[tool["name"]] = category
    except Exception:
        logger.warning(
            "MCPToolService unavailable — grouping tools with the built-in catalog", exc_info=True
        )
        for category in MCP_CATEGORY_BY_KEY.values():
            for tool in category.tools:
                name_to_category[tool.value] = category.key

    result: dict[str, list[str]] = {}
    for name in tool_names:
        category = name_to_category.get(name)
        if category is None:
            logger.warning("No known MCP category for tool %r — skipped in expansion", name)
            continue
        result.setdefault(category, []).append(name)

    return result


def _new_id() -> str:
    return str(uuid4())


# Horizontal gap between successive Pipeline stages. Wider than the intra-stage
# spread (resource nodes sit +320 from their stage node) so each stage's node
# cluster lands in its own column instead of stacking on the drop point
# (design spec §7.3 — deterministic offset layout).
_STAGE_X_GAP = 720


_SINGLE_BRAIN_NODE_TYPES = {
    GraphSchemaType.REACT: "ReActAgent",
    GraphSchemaType.PLAN_EXECUTE: "PlanExecuteAgent",
    GraphSchemaType.SELF_REFLECT: "SelfReflectAgent",
}


def select_agent_node_type(graph_schema: str, *, has_tools: bool) -> str:
    """Pick which flow-canvas agent-execution node type represents a given
    classic agent. zero_shot is special: Chatbot/ZeroShotAgent (core.py) have
    no tools handle, so an agent with tools must become ReActAgent instead —
    the same promotion agents/graphs/builder.py:292-297 does at build time.
    """
    if graph_schema == GraphSchemaType.ZERO_SHOT:
        return "ReActAgent" if has_tools else "ZeroShotAgent"
    try:
        return _SINGLE_BRAIN_NODE_TYPES[GraphSchemaType(graph_schema)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Not a single-brain graph_schema: {graph_schema!r}") from exc


def _build_agent_and_resource_nodes(
    *,
    node_type: str,
    system_prompt: str | None,
    model: str | None,
    memory_type: str | None,
    tool_categories: dict[str, list[str]],
    include_chat_input: bool,
    id_factory: Callable[[], str],
) -> tuple[list[FlowNode], list[FlowEdge], str]:
    """Shared by materialize_single_brain and (Task 4) each Pipeline stage.
    Returns (nodes, edges, agent_node_id) — the caller wires the agent
    node's message ports (input from ChatInput or the previous stage,
    output to whatever comes next) since that differs between the two
    callers.
    """
    nodes: list[FlowNode] = []
    edges: list[FlowEdge] = []

    agent_id = id_factory()
    nodes.append(
        FlowNode(
            id=agent_id,
            type=node_type,
            values={"system_prompt": system_prompt or ""},
            position={"x": 0, "y": 0},
        )
    )

    if include_chat_input:
        chat_input_id = id_factory()
        nodes.append(
            FlowNode(id=chat_input_id, type="ChatInput", values={}, position={"x": -320, "y": 0})
        )
        edges.append(
            FlowEdge(
                id=id_factory(),
                source=chat_input_id,
                sourceHandle="message",
                target=agent_id,
                targetHandle="input",
            )
        )

    if model:
        model_id = id_factory()
        nodes.append(
            FlowNode(
                id=model_id,
                type="LLMModel",
                values={"model": model},
                position={"x": 320, "y": -140},
            )
        )
        edges.append(
            FlowEdge(
                id=id_factory(),
                source=model_id,
                sourceHandle="model",
                target=agent_id,
                targetHandle="model",
            )
        )

    materializable = [
        (category, tool_names)
        for category, tool_names in sorted(tool_categories.items())
        if category in CATEGORY_NODE_TYPES
    ]
    for category in sorted(set(tool_categories) - set(CATEGORY_NODE_TYPES)):
        logger.warning(
            "MCP category %r has no plain flow-canvas node type — its tools are "
            "dropped from agent expansion",
            category,
        )
    for i, (category, tool_names) in enumerate(materializable):
        node_id = id_factory()
        nodes.append(
            FlowNode(
                id=node_id,
                type=CATEGORY_NODE_TYPES[category],
                values={"tools": tool_names},
                position={"x": 320, "y": i * 90},
            )
        )
        edges.append(
            FlowEdge(
                id=id_factory(),
                source=node_id,
                sourceHandle="tools",
                target=agent_id,
                targetHandle="tools",
            )
        )

    if memory_type == "long_term":
        memory_id = id_factory()
        nodes.append(
            FlowNode(
                id=memory_id,
                type="LongTermMemory",
                values={},
                position={"x": 320, "y": len(tool_categories) * 90 + 90},
            )
        )
        edges.append(
            FlowEdge(
                id=id_factory(),
                source=memory_id,
                sourceHandle="memory",
                target=agent_id,
                targetHandle="memory",
            )
        )
    elif memory_type not in (None, "none"):
        logger.warning(
            "memory_type %r has no flow-canvas node representation — skipped in expansion",
            memory_type,
        )

    return nodes, edges, agent_id


def materialize_single_brain(
    definition: Any,
    tool_categories: dict[str, list[str]],
    *,
    id_factory: Callable[[], str] | None = None,
) -> tuple[list[FlowNode], list[FlowEdge]]:
    """Expand a single-brain AgentDefinitionModel (design spec §7.1)."""
    id_factory = id_factory or _new_id
    node_type = select_agent_node_type(definition.graph_schema, has_tools=bool(tool_categories))
    nodes, edges, _agent_id = _build_agent_and_resource_nodes(
        node_type=node_type,
        system_prompt=definition.system_prompt,
        model=definition.model,
        memory_type=definition.memory_type,
        tool_categories=tool_categories,
        include_chat_input=True,
        id_factory=id_factory,
    )
    return nodes, edges


async def resolve_pipeline_stage_configs(definition: Any, repository: Any) -> list[dict[str, Any]]:
    """Full ordered stage list for a Pipeline agent, mirroring
    GraphBuilder._load_sub_agents_from_db's own ordering exactly:
    resolved sub_agent_ids first, then inline `stages` entries
    (agents/graphs/builder.py:167-264).
    """
    resolved: list[dict[str, Any]] = []
    for sub_id in definition.sub_agent_ids or []:
        stage_definition = await repository.get_by_id(sub_id)
        if stage_definition is None:
            logger.warning("Pipeline sub_agent_id %r not found — skipped in expansion", sub_id)
            continue
        resolved.append(
            {
                "name": stage_definition.name,
                "system_prompt": stage_definition.system_prompt,
                "model": stage_definition.model,
                "mcp_tools": stage_definition.mcp_tools or [],
            }
        )

    inline = [
        {
            "name": stage.get("name", "stage"),
            "system_prompt": stage.get("system_prompt", ""),
            "model": stage.get("model"),
            "mcp_tools": stage.get("mcp_tools") or [],
        }
        for stage in (definition.stages or [])
    ]

    return resolved + inline


def materialize_pipeline(
    stage_configs: list[dict[str, Any]],
    tool_categories_by_stage: list[dict[str, list[str]]],
    *,
    id_factory: Callable[[], str] | None = None,
) -> tuple[list[FlowNode], list[FlowEdge]]:
    """Expand a Pipeline agent into a chain of PipelineStage nodes (design
    spec §7.2a) — a flow-canvas pipeline is N single-agent nodes wired by
    ordinary MESSAGE edges (agents_multi.py:60-86, flow_builder.py:164),
    unrelated to how the classic (non-flow) pipeline actually executes
    (agents/graphs/builder.py:418-441's create_supervisor-based runner) —
    this materializes the *configuration*, not the classic runtime.
    """
    id_factory = id_factory or _new_id
    all_nodes: list[FlowNode] = []
    all_edges: list[FlowEdge] = []
    stage_agent_ids: list[str] = []

    for i, (stage, tool_categories) in enumerate(zip(stage_configs, tool_categories_by_stage)):
        nodes, edges, stage_agent_id = _build_agent_and_resource_nodes(
            node_type="PipelineStage",
            system_prompt=stage["system_prompt"],
            model=stage.get("model"),
            memory_type=None,
            tool_categories=tool_categories,
            include_chat_input=(i == 0),
            id_factory=id_factory,
        )
        # PipelineStage also has its own required `name` field
        # (agents_multi.py:69-74) — not covered by the shared helper, which
        # only sets `system_prompt` (the field every agent-execution node
        # shares).
        for node in nodes:
            if node.id == stage_agent_id:
                node.values["name"] = stage["name"]
            if i:
                node.position.x += i * _STAGE_X_GAP

        all_nodes.extend(nodes)
        all_edges.extend(edges)
        stage_agent_ids.append(stage_agent_id)

    for i in range(len(stage_agent_ids) - 1):
        all_edges.append(
            FlowEdge(
                id=id_factory(),
                source=stage_agent_ids[i],
                sourceHandle="output",
                target=stage_agent_ids[i + 1],
                targetHandle="input",
            )
        )

    return all_nodes, all_edges


class AgentExpansionError(Exception):
    """Raised when an agent cannot be expanded onto a flow canvas."""


def _clone_name(original_name: str) -> str:
    # AgentDefinitionModel.name is unique=True (core/db/models/agent_definition.py)
    # — the hex suffix is drawn from a fresh uuid4, so collisions are as
    # unlikely as any other uuid4 collision, independent of the original name.
    return f"{original_name} (copy {uuid4().hex[:8]})"


async def _clone_one(definition_id: str, repository: Any) -> str:
    """Depth-first: clone this row's own sub_agent_ids first, so the parent
    clone can be created with sub_agent_ids already pointing at the new
    child clones, never the originals."""
    source = await repository.get_by_id(definition_id)
    if source is None:
        raise AgentExpansionError(f"Referenced agent '{definition_id}' no longer exists")

    cloned_child_ids = [
        await _clone_one(child_id, repository) for child_id in (source.sub_agent_ids or [])
    ]

    created = await repository.create(
        name=_clone_name(source.name),
        persona_id=None,
        agent_type=source.agent_type,
        description=source.description,
        graph_schema=source.graph_schema,
        brain_type=source.brain_type,
        memory_type=source.memory_type,
        system_prompt=source.system_prompt,
        model=source.model,
        mcp_tools=source.mcp_tools,
        mcp_tool_configs=source.mcp_tool_configs,
        rag_config=source.rag_config,
        sub_agents=source.sub_agents,
        sub_agent_ids=cloned_child_ids,
        supervisor_prompt=source.supervisor_prompt,
        stages=source.stages,
        pipeline_prompt=source.pipeline_prompt,
        reflection_prompt=source.reflection_prompt,
        max_iterations=source.max_iterations,
        tags=source.tags,
        version=source.version,
    )
    return str(created.id)


async def clone_sub_agent_tree(
    sub_agent_ids: list[str], repository: Any, *, depth_service: Any = None
) -> list[str]:
    """Recursively deep-clone every AgentDefinitionModel reachable from
    ``sub_agent_ids`` into new, detached DB rows (design spec §7.2b).
    Validates depth for the *entire* tree before writing anything, so a
    MAX_DEPTH violation never leaves orphaned partial clones behind.
    """
    from service.CompositionValidationService import CompositionValidationService

    service = depth_service or CompositionValidationService(repository)

    for sub_id in sub_agent_ids:
        depth = await service.get_composition_depth_async(sub_id)
        if depth >= CompositionValidationService.MAX_DEPTH:
            raise AgentExpansionError(
                f"Agent '{sub_id}' composition depth {depth} would exceed the "
                f"{CompositionValidationService.MAX_DEPTH}-level limit — expansion aborted "
                "before creating any clones"
            )

    return [await _clone_one(sub_id, repository) for sub_id in sub_agent_ids]


async def expand_agent_definition(
    definition_id: Any,
    repository: Any,
    *,
    mcp_service: Any = None,
    depth_service: Any = None,
) -> tuple[list[FlowNode], list[FlowEdge]]:
    """Top-level entry point: materialize an existing agent onto a flow
    canvas (design spec §7.3), branching by graph_schema per §6.
    """
    definition = await repository.get_by_id(definition_id)
    if definition is None:
        raise AgentExpansionError(f"Agent '{definition_id}' not found")

    if definition.graph_schema == GraphSchemaType.FLOW:
        raise AgentExpansionError(
            f"Agent '{definition_id}' is flow-backed; a flow cannot expand another flow "
            "(design spec 5.4, same rule AgentRef already enforces)"
        )

    if definition.graph_schema == GraphSchemaType.SUPERVISOR:
        clone_ids = await clone_sub_agent_tree(
            definition.sub_agent_ids or [], repository, depth_service=depth_service
        )
        node = FlowNode(
            id=_new_id(),
            type="Supervisor",
            values={
                "supervisor_prompt": definition.supervisor_prompt or "You are a team supervisor.",
                "sub_agents": clone_ids,
            },
            position={"x": 0, "y": 0},
        )
        return [node], []

    if definition.graph_schema == GraphSchemaType.PIPELINE:
        stage_configs = await resolve_pipeline_stage_configs(definition, repository)
        tool_categories_by_stage = [
            await resolve_tool_categories(stage["mcp_tools"], service=mcp_service)
            for stage in stage_configs
        ]
        return materialize_pipeline(stage_configs, tool_categories_by_stage)

    tool_categories = await resolve_tool_categories(
        getattr(definition, "mcp_tools", None) or [], service=mcp_service
    )
    return materialize_single_brain(definition, tool_categories)

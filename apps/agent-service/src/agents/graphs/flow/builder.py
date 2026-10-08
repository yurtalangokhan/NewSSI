"""FlowGraphBuilder — compiles a validated FlowSpec into a LangGraph graph."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.graphs.flow.message_flow import (
    _extract_last_message_text,
    _final_stage_in_cycle,
    _isolate_subagent_node,
    _loop_body_node_ids,
    _make_arrival_stamp,
    _make_merge_node,
    _message_suppressed_producer_ids,
    _resolve_final_stage_nodes,
    _suppress_messages,
    derive_tool_name,
)
from agents.graphs.flow.node_types import NOOP_NODE_TYPES
from agents.graphs.flow.nodes import (
    _make_batch_run_node,
    _make_chat_input_node,
    _make_condrouter_node,
    _make_condrouter_route_fn,
    _make_content_crawl_node,
    _make_document_context_node,
    _make_document_search_node,
    _make_fetch_webpage_node,
    _make_foreach_node,
    _make_foreach_route_fn,
    _make_graph_entity_search_node,
    _make_graph_neighborhood_node,
    _make_graph_search_node,
    _make_graph_stats_node,
    _make_guardrails_node,
    _make_guardrails_route_fn,
    _make_human_input_node,
    _make_human_input_route_fn,
    _make_loop_node,
    _make_loop_route_fn,
    _make_operations_node,
    _make_parser_node,
    _make_prompt_template_node,
    _make_set_variable_node,
    _make_smart_router_node,
    _make_smart_router_route_fn,
    _make_split_text_node,
    _make_structured_output_node,
    _make_sync_trigger_node,
    _make_text_input_node,
    _make_type_converter_node,
    _make_web_search_node,
    make_component_tool,
)
from agents.graphs.flow.state import (
    _MODEL_RESOURCE_TYPES,
    _TOOL_RESOURCE_TYPES,
    FlowState,
    ResolvedResources,
    _select_model,
    is_tool_mode,
    partition_nodes,
    resolve_resources,
)
from core.exceptions import FlowBuildError, UnknownComponentError
from core.observability.logger import get_logger
from schemas.agent_graphs import GraphSchemaType
from schemas.flows import FlowEdge, FlowNode, FlowSpec
from service.flow_model.comparison import evaluate_comparison
from service.flow_model.handles import effective_input_handles
from service.flow_model.migrations import migrate_spec
from service.flow_model.registry import ComponentRegistry, get_registry

logger = get_logger(__name__)

_AGENT_SCHEMA_BY_TYPE = {
    "Chatbot": GraphSchemaType.ZERO_SHOT,
    "ZeroShotAgent": GraphSchemaType.ZERO_SHOT,
    "ReActAgent": GraphSchemaType.REACT,
    "PlanExecuteAgent": GraphSchemaType.PLAN_EXECUTE,
    "SelfReflectAgent": GraphSchemaType.SELF_REFLECT,
    "PipelineStage": GraphSchemaType.REACT,
}


async def _noop_node(state: FlowState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
    """ChatInput/ChatOutput: addressable no-ops. Edges need somewhere to
    originate/terminate; no state transformation happens here."""
    return {}


async def _make_agent_node(
    node: FlowNode,
    resources: ResolvedResources,
    *,
    user_id: str | None = None,
    mcp_tools_map: dict[str, Any] | None = None,
    model_node_id: str | None = None,
    mcp_tools: list[str] | None = None,
    mcp_tool_configs: dict[str, Any] | None = None,
    memory_enabled: bool = False,
) -> CompiledStateGraph:
    """Reuses agents/graphs/builder.py's existing per-schema logic directly —
    the returned compiled graph *is* GraphBuilder's own output, embedded as a
    subgraph. There is no separate agent-behavior code path to diverge from
    the classic builder; Task 0's spike proved this embedding pattern is safe.
    """
    from agents.graphs.builder import GraphBuilder

    schema_type = _AGENT_SCHEMA_BY_TYPE[node.type]
    model = _select_model(resources, model_node_id)

    builder = GraphBuilder(
        model=model,
        mcp_tools_map=mcp_tools_map or {},
        checkpointer=None,  # the parent flow's checkpointer owns persistence
        memory_enabled=memory_enabled,
    )
    config: dict[str, Any] = {
        "system_prompt": node.values.get("system_prompt", ""),
        "user_id": user_id,
    }
    if schema_type != GraphSchemaType.ZERO_SHOT:
        if mcp_tools:
            config["mcp_tools"] = mcp_tools
        if mcp_tool_configs:
            config["mcp_tool_configs"] = mcp_tool_configs

    if node.type == "SelfReflectAgent":
        config["reflection_prompt"] = node.values.get("reflection_prompt", "")
        config["max_iterations"] = node.values.get("max_iterations", 3)
    # The per-schema strategies are async (they may load referenced sub-agents
    # from the database), so the embedded subgraph is built through
    # ``build_async`` — the sync ``build`` would hand LangGraph a coroutine.
    return await builder.build_async(schema_type, config)


async def make_node(
    node: FlowNode,
    resources: ResolvedResources,
    *,
    user_id: str | None = None,
    mcp_tools_map: dict[str, Any] | None = None,
    model_node_id: str | None = None,
    mcp_tools: list[str] | None = None,
    mcp_tool_configs: dict[str, Any] | None = None,
    memory_enabled: bool = False,
    port_sources: dict[str, str] | None = None,
    body_end_id: str | None = None,
    extra_frame_sources: Sequence[str] | None = None,
) -> Any:
    """Return the LangGraph-node-compatible value for one execution node.

    For agent types this is a compiled subgraph (GraphBuilder's own output);
    for everything else it's a plain async callable of (FlowState, config).
    `model_node_id` names the resource actually wired to this node's
    Model handle (Task 10 supplies it from the flow's edges); omit it for a
    single-model flow. Raises UnknownComponentError for a type this factory
    doesn't know.

    `port_sources` maps this node's input handle names to the id of the node
    wired to each; `build()` supplies it from the flow's edges. Empty when a
    node is built standalone, which is exactly the "nothing wired" case, so
    every port falls back to its declared field.

    `body_end_id` is the Loop-only companion: the node that closes the foreach
    body (whatever wires back into the Loop's `input` handle), whose value is
    what each pass aggregates. `extra_frame_sources` is the Data Operations
    companion: every table wired into `df` beyond the first, which only
    Concatenate reads.
    """
    if node.type == "ChatInput":
        # The flow's per-turn reset point. ``build()`` calls this same factory
        # with the flow's While / If-Else / foreach ids to zero; standalone
        # there are none, but the arrivals channel is cleared either way.
        return _make_chat_input_node((), (), ())
    if node.type in NOOP_NODE_TYPES:
        return _noop_node
    # Table defined below, after the factories it names.
    simple_factory = _SIMPLE_NODE_FACTORIES.get(node.type)
    if simple_factory is not None:
        return simple_factory(node)

    # What remains needs more than the node: a model resolved from the flow's
    # edges, the MCP tool map, or the whole resource set.
    if node.type == "ConditionalRouter":
        return _make_condrouter_node(node, port_sources)
    if node.type == "Loop":
        return _make_foreach_node(node, port_sources, body_end_id)
    if node.type == "SmartRouter":
        return _make_smart_router_node(node, _select_model(resources, model_node_id), port_sources)
    if node.type == "Guardrails":
        return _make_guardrails_node(node, _select_model(resources, model_node_id), port_sources)
    if node.type == "Operations":
        return _make_operations_node(node, port_sources, extra_frame_sources)
    if node.type == "SplitText":
        return _make_split_text_node(node, port_sources)
    if node.type == "TypeConverter":
        return _make_type_converter_node(node, port_sources)
    if node.type == "Parser":
        return _make_parser_node(node, port_sources)
    if node.type == "BatchRun":
        return _make_batch_run_node(node, _select_model(resources, model_node_id), port_sources)
    if node.type == "StructuredOutput":
        return _make_structured_output_node(node, _select_model(resources, model_node_id), port_sources)
    if node.type == "WebSearch":
        return _make_web_search_node(node, resources, mcp_tools_map=mcp_tools_map)
    if node.type == "FetchWebpage":
        return _make_fetch_webpage_node(node, resources)
    if node.type == "ContentCrawl":
        return _make_content_crawl_node(node, resources)
    if node.type in _AGENT_SCHEMA_BY_TYPE:
        return await _make_agent_node(
            node,
            resources,
            user_id=user_id,
            mcp_tools_map=mcp_tools_map,
            model_node_id=model_node_id,
            mcp_tools=mcp_tools,
            mcp_tool_configs=mcp_tool_configs,
            memory_enabled=memory_enabled,
        )
    raise UnknownComponentError(node.type)


_MAX_FLOW_DEPTH = 5


_SIMPLE_NODE_FACTORIES: dict[str, Callable[[FlowNode], Any]] = {
    "TextInput": _make_text_input_node,
    "PromptTemplate": _make_prompt_template_node,
    "Merge": _make_merge_node,
    "SetVariable": _make_set_variable_node,
    "HumanInput": _make_human_input_node,
    "While": _make_loop_node,
    "DocumentSearch": _make_document_search_node,
    "KnowledgeBase": _make_document_search_node,
    "DocumentContext": _make_document_context_node,
    "GraphSearch": _make_graph_search_node,
    "GraphEntitySearch": _make_graph_entity_search_node,
    "GraphNeighborhood": _make_graph_neighborhood_node,
    "GraphStats": _make_graph_stats_node,
    "SyncTrigger": _make_sync_trigger_node,
}


class FlowGraphBuilder:
    """Compiles a FlowSpec into a runnable LangGraph graph.

    Assumes `spec` already passed FlowService.validate_flow (P1 Task 6) — this
    class does not re-validate. A spec that reaches here in a state validation
    should have caught still fails clearly (FlowBuildError), never silently.
    """

    def __init__(
        self,
        *,
        user_id: str | None = None,
        checkpointer: Any | None = None,
        repository: Any | None = None,
        registry: ComponentRegistry | None = None,
        mcp_tools_map: dict[str, Any] | None = None,
        build_depth: int = 0,
    ) -> None:
        self.user_id = user_id
        self.checkpointer = checkpointer
        self.repository = repository
        self.registry = registry
        self.mcp_tools_map = mcp_tools_map or {}
        # How many RunFlow hops deep this compile already is. A child
        # builder is constructed with build_depth + 1, so a reference cycle
        # hits the bound instead of recursing forever (see _MAX_FLOW_DEPTH).
        self.build_depth = build_depth
        # Populated by build(); the execution nodes whose output is the
        # flow's final answer. Stays empty if build() raises. See
        # _resolve_final_stage_nodes.
        self.final_stage_node_ids: set[str] = set()
        # Node ids the compiler itself inserts that are NOT on the canvas
        # (arrival stamps for first/last Merge, today). Consumers that report
        # stages consult this set so they never have to pattern-match a
        # naming convention this module owns.
        self.synthetic_node_ids: set[str] = set()
        # Tools built from tool-mode components on this flow, by the name the
        # model sees. Merged into the map handed to every agent node.
        self.component_tools: dict[str, Any] = {}
        # True when a final node sits on a loop cycle (runs several times) —
        # the live layer then folds every iteration and promotes the last.
        self.final_stage_in_cycle: bool = False
        # Execution nodes structurally known to sit on a Loop/While cycle
        # (B18) — the client can fold a loop's first iteration into its
        # collapsible group immediately instead of waiting to observe a
        # second one. See _loop_body_node_ids.
        self.loop_body_node_ids: set[str] = set()
        # Execution nodes whose message is suppressed because their only
        # consumer is a first/last Merge (B19). See
        # _message_suppressed_producer_ids.
        self.message_suppressed_node_ids: set[str] = set()

    async def build(self, spec: FlowSpec) -> CompiledStateGraph:
        registry = self.registry or get_registry()

        # Migrate on read (design spec 4.6): a stored spec may predate a
        # template version bump (Router v1->v2 is the first). This is a pure,
        # in-memory rewrite; the next save persists it. Every routing/runtime
        # helper below can then assume current-version values.
        spec = migrate_spec(spec, registry=registry)

        try:
            resource_nodes, execution_nodes = partition_nodes(spec.nodes, registry)
        except UnknownComponentError as exc:
            raise FlowBuildError(str(exc)) from exc

        # A tool-mode node is a resource for this run, but it resolves to a
        # tool rather than to a model or a tool *name*. GraphBuilder resolves
        # tools by name from the map it is handed, so registering it there is
        # the whole integration — the agent side is untouched.
        tool_mode_nodes = {n.id: n for n in resource_nodes if is_tool_mode(n, registry.get(n.type))}
        resources = resolve_resources(resource_nodes, set(tool_mode_nodes))
        resource_ids = {n.id for n in resource_nodes}

        self.component_tools = {}
        for tool_node in tool_mode_nodes.values():
            tool = make_component_tool(
                tool_node,
                resources,
                user_id=self.user_id,
                mcp_tools_map=self.mcp_tools_map,
                node_factory=make_node,
            )
            self.component_tools[tool.name] = tool

        # Which execution node each resource feeds — the resolver's per-node
        # model selection needs this; resources are never add_node'd.
        model_node_id_by_target: dict[str, str] = {}
        tool_node_ids_by_target: dict[str, list[str]] = defaultdict(list)
        mail_config_by_tool_node: dict[str, str] = {}
        memory_node_id_by_target: dict[str, str] = {}

        for edge in spec.edges:
            if edge.source in resource_ids:
                source_node = next((n for n in resource_nodes if n.id == edge.source), None)
                if source_node:
                    if source_node.type in _MODEL_RESOURCE_TYPES:
                        model_node_id_by_target[edge.target] = edge.source
                    elif source_node.id in tool_mode_nodes or source_node.type in _TOOL_RESOURCE_TYPES:
                        tool_node_ids_by_target[edge.target].append(edge.source)
                    elif source_node.type == "MailConfig":
                        mail_config_by_tool_node[edge.target] = edge.source
                    elif source_node.type == "LongTermMemory":
                        memory_node_id_by_target[edge.target] = edge.source

        entry_nodes = [n for n in execution_nodes if n.type == "ChatInput"]
        exit_nodes = [n for n in execution_nodes if n.type == "ChatOutput"]
        if not entry_nodes:
            raise FlowBuildError("Flow has no Chat Input node")
        if not exit_nodes:
            raise FlowBuildError("Flow has no Chat Output node")

        # Defense in depth for the validator/compiler reachability contract: a
        # spec whose only entry→exit path traverses a resource node compiles
        # into a dead-end graph that looks successful while silently doing
        # nothing. Validation rejects that shape; build() must not accept it
        # unvalidated either (e.g. a stale playground draft).
        execution_adjacency: dict[str, list[str]] = {n.id: [] for n in execution_nodes}
        for edge in spec.edges:
            if edge.source in resource_ids or edge.target in resource_ids:
                continue  # resource wiring — consumed above, not a graph edge
            execution_adjacency[edge.source].append(edge.target)
        reached: set[str] = set()
        pending = [n.id for n in entry_nodes]
        while pending:
            current = pending.pop()
            if current in reached:
                continue
            reached.add(current)
            pending.extend(execution_adjacency.get(current, []))
        if not any(n.id in reached for n in exit_nodes):
            raise FlowBuildError(
                "No Chat Output node is reachable from Chat Input through execution "
                "nodes; resource nodes are injected at build time and do not forward "
                "the flow"
            )

        router_ids = {n.id for n in execution_nodes if n.type == "Router"}
        loop_ids = {n.id for n in execution_nodes if n.type == "Loop"}  # foreach
        while_ids = {n.id for n in execution_nodes if n.type == "While"}  # counter loop
        condrouter_ids = {n.id for n in execution_nodes if n.type == "ConditionalRouter"}
        smart_router_ids = {n.id for n in execution_nodes if n.type == "SmartRouter"}
        guardrails_ids = {n.id for n in execution_nodes if n.type == "Guardrails"}
        human_input_ids = {n.id for n in execution_nodes if n.type == "HumanInput"}
        # Merge nodes whose strategy needs branch arrival order: each incoming
        # edge is routed through an arrival-stamp node (added in the edge loop).
        stamped_merge_ids = {
            n.id
            for n in execution_nodes
            if n.type == "Merge" and n.values.get("strategy", "concat") in ("first", "last")
        }
        # B19: a producer whose only consumer is one of these merges never
        # emits its own message — see _message_suppressed_producer_ids.
        message_suppressed_ids = _message_suppressed_producer_ids(
            execution_adjacency,
            stamped_merge_ids,
            entry_ids={n.id for n in entry_nodes},
        )
        self.message_suppressed_node_ids = message_suppressed_ids

        self.final_stage_node_ids = _resolve_final_stage_nodes(
            spec, resource_ids, message_suppressed_ids=message_suppressed_ids
        )
        self.final_stage_in_cycle = _final_stage_in_cycle(spec, resource_ids, self.final_stage_node_ids)
        self.loop_body_node_ids = _loop_body_node_ids(spec, resource_ids)
        # B19: how many branches each first/last Merge waits for before it
        # emits its one message — see _make_merge_node.
        expected_arrivals_by_merge: dict[str, int] = defaultdict(int)
        for edge in spec.edges:
            if edge.source in resource_ids or edge.target in resource_ids:
                continue
            if edge.target in stamped_merge_ids:
                expected_arrivals_by_merge[edge.target] += 1

        # Which node feeds each input handle of each node. This is how a
        # declared port carries a value: the consumer reads the producer's
        # scratch slot at runtime (see `_resolve_port_value`). Resource wiring
        # is excluded — it is consumed above and is not a graph edge.
        port_sources_by_node: dict[str, dict[str, str]] = defaultdict(dict)
        for edge in spec.edges:
            if edge.source in resource_ids or edge.target in resource_ids:
                continue
            port_sources_by_node[edge.target][edge.target_handle] = edge.source

        # Every table wired into a node's `df` handle, in edge order. Only
        # Concatenate reads past the first; port_sources_by_node keeps just one.
        frame_sources_by_node: dict[str, list[str]] = defaultdict(list)
        for edge in spec.edges:
            if edge.source in resource_ids or edge.target in resource_ids:
                continue
            if edge.target_handle == "df":
                frame_sources_by_node[edge.target].append(edge.source)

        # A foreach body's end is whatever wires back into the Loop's `input`
        # handle; its value is what each pass aggregates.
        def _body_end(loop_id: str) -> str | None:
            """The node that closes the foreach body.

            Two edges land on a Loop's `input`: Chat Input at the start of the
            turn, and the body's last node on every pass. Taking the first one
            found picks Chat Input in every normally-drawn flow, so the body
            has to be identified by reachability from the `item` branch —
            the same rule the validator uses.
            """
            item_target = next(
                (e.target for e in spec.edges if e.source == loop_id and e.source_handle == "item"),
                None,
            )
            if item_target is None:
                return None
            body = set()
            stack = [item_target]
            while stack:
                current = stack.pop()
                if current in body or current == loop_id:
                    continue
                body.add(current)
                stack.extend(execution_adjacency.get(current, []))
            return next(
                (
                    e.source
                    for e in spec.edges
                    if e.target == loop_id and e.target_handle == "input" and e.source in body
                ),
                None,
            )

        body_end_by_loop = {loop_id: _body_end(loop_id) for loop_id in loop_ids}

        graph = StateGraph(FlowState)

        # Every node type is built by `make_node`. The three cases below are
        # the only ones that need something `make_node` cannot see: the flow's
        # other nodes (ChatInput's per-turn reset list) or an awaited
        # sub-graph (AgentRef, Supervisor).
        for node in execution_nodes:
            # B19: a producer whose only consumer is a first/last Merge
            # never lets a message reach the transcript on its own.
            _wrap = _suppress_messages if node.id in message_suppressed_ids else (lambda f: f)
            if node.type == "ChatInput":
                graph.add_node(
                    node.id,
                    _make_chat_input_node(sorted(while_ids), sorted(condrouter_ids), sorted(loop_ids)),
                )
                continue
            if node.type == "RunFlow":
                graph.add_node(node.id, _wrap(await self._resolve_run_flow(node)))
                continue
            if node.type == "AgentRef":
                subgraph = await self._resolve_agent_ref(node)
                graph.add_node(node.id, _wrap(_isolate_subagent_node(subgraph, node.id)))
                continue
            if node.type == "Supervisor":
                subgraph = await self._resolve_supervisor(node)
                graph.add_node(node.id, _wrap(_isolate_subagent_node(subgraph, node.id)))
                continue
            if node.type == "Merge":
                graph.add_node(
                    node.id,
                    _make_merge_node(node, expected_arrivals=expected_arrivals_by_merge.get(node.id)),
                )
                continue
            model_node_id = model_node_id_by_target.get(node.id)
            connected_tool_nodes = tool_node_ids_by_target.get(node.id, [])
            node_tool_names: list[str] = []
            node_tool_configs: dict[str, Any] = {}
            for t_id in connected_tool_nodes:
                if t_id in tool_mode_nodes:
                    component_tool_name = derive_tool_name(tool_mode_nodes[t_id])
                    if component_tool_name not in node_tool_names:
                        node_tool_names.append(component_tool_name)
                    continue
                for tool_name in resources.tool_names.get(t_id, []):
                    if tool_name not in node_tool_names:
                        node_tool_names.append(tool_name)
                if t_id in mail_config_by_tool_node:
                    mail_cfg_id = mail_config_by_tool_node[t_id]
                    config_val = resources.mail_config_ids.get(mail_cfg_id)
                    if config_val:
                        node_tool_configs["send_email"] = {"mail_config_id": config_val}

            graph.add_node(
                node.id,
                _wrap(
                    await make_node(
                        node,
                        resources,
                        user_id=self.user_id,
                        mcp_tools_map={**self.mcp_tools_map, **self.component_tools},
                        model_node_id=model_node_id,
                        mcp_tools=node_tool_names,
                        mcp_tool_configs=node_tool_configs,
                        memory_enabled=(node.id in memory_node_id_by_target),
                        port_sources=port_sources_by_node.get(node.id, {}),
                        body_end_id=body_end_by_loop.get(node.id),
                        extra_frame_sources=frame_sources_by_node.get(node.id, [])[1:],
                    )
                ),
            )

        stamped: set[str] = set()
        for edge in spec.edges:
            if edge.source in resource_ids or edge.target in resource_ids:
                continue  # resource wiring — consumed above, not a graph edge
            if (
                edge.source in router_ids
                or edge.source in loop_ids
                or edge.source in while_ids
                or edge.source in condrouter_ids
                or edge.source in smart_router_ids
                or edge.source in guardrails_ids
                or edge.source in human_input_ids
            ):
                continue  # handled by add_conditional_edges below
            if edge.target in stamped_merge_ids and edge.source not in stamped_merge_ids:
                stamp_id = f"__arrival__{edge.target}__{edge.source}"
                if stamp_id not in stamped:
                    graph.add_node(stamp_id, _make_arrival_stamp(edge.target, edge.source))
                    stamped.add(stamp_id)
                    self.synthetic_node_ids.add(stamp_id)
                graph.add_edge(edge.source, stamp_id)
                graph.add_edge(stamp_id, edge.target)
                continue
            graph.add_edge(edge.source, edge.target)

        for router_id in router_ids:
            router_node = next(n for n in execution_nodes if n.id == router_id)
            graph.add_conditional_edges(router_id, self._make_router_fn(router_node, spec.edges))

        for loop_id in loop_ids:
            loop_node = next(n for n in execution_nodes if n.id == loop_id)
            graph.add_conditional_edges(loop_id, _make_foreach_route_fn(loop_node, spec.edges))

        for while_id in while_ids:
            while_node = next(n for n in execution_nodes if n.id == while_id)
            graph.add_conditional_edges(while_id, _make_loop_route_fn(while_node, spec.edges))

        for cr_id in condrouter_ids:
            cr_node = next(n for n in execution_nodes if n.id == cr_id)
            graph.add_conditional_edges(cr_id, _make_condrouter_route_fn(cr_node, spec.edges))

        for sr_id in smart_router_ids:
            sr_node = next(n for n in execution_nodes if n.id == sr_id)
            graph.add_conditional_edges(sr_id, _make_smart_router_route_fn(sr_node, spec.edges))

        for gr_id in guardrails_ids:
            gr_node = next(n for n in execution_nodes if n.id == gr_id)
            graph.add_conditional_edges(gr_id, _make_guardrails_route_fn(gr_node, spec.edges))

        for hi_id in human_input_ids:
            hi_node = next(n for n in execution_nodes if n.id == hi_id)
            graph.add_conditional_edges(hi_id, _make_human_input_route_fn(hi_node, spec.edges))

        # Every node that has no way to receive input is a graph entry point:
        # LangGraph only runs a node reachable from START. That is ChatInput
        # (required above) *and* author-placed source nodes like TextInput —
        # whose template declares no input handle at all. Before this they
        # had no START edge and never ran; a TextInput feeding a
        # StructuredOutput silently delivered nothing (B15).
        source_node_ids = {n.id for n in entry_nodes}
        for n in execution_nodes:
            if n.id in source_node_ids:
                continue
            if not effective_input_handles(registry.get(n.type), n.values):
                source_node_ids.add(n.id)
        for node_id in source_node_ids:
            graph.add_edge(START, node_id)
        for node in exit_nodes:
            graph.add_edge(node.id, END)

        compiled = graph.compile(checkpointer=self.checkpointer)

        # LangGraph's default recursion_limit (25 super-steps) is fine for an
        # acyclic flow but a loop can legitimately need more: every While /
        # ConditionalRouter / Loop pass is at least two super-steps (the node
        # plus its body). Raise the ceiling to the worst case the bounds
        # allow, so a valid flow never dies with GraphRecursionError; keep it
        # capped so a runaway still stops. A foreach Loop has no static bound,
        # so it gets a fixed allowance (very long collections may still hit
        # the cap).
        iteration_budget = sum(
            int(n.values.get("max_iterations") or 0)
            for n in execution_nodes
            if n.type in ("While", "ConditionalRouter")
        )
        iteration_budget += 50 * sum(1 for n in execution_nodes if n.type == "Loop")
        if iteration_budget:
            recursion_limit = max(25, min(500, 25 + 3 * iteration_budget))
            compiled = compiled.with_config({"recursion_limit": recursion_limit})

        return compiled

    async def _resolve_run_flow(self, node: FlowNode) -> Any:
        """Compile another published flow as this node (Langflow's Run Flow).

        Mirrors `_resolve_agent_ref`: the child compiles with
        `checkpointer=None`, so the parent owns persistence. It runs
        **isolated** — invoked with only the latest message, and only its
        answer comes back — so the two flows' `scratch` namespaces cannot
        collide. Two authors can each use a variable called `result` without
        knowing about each other.

        Returns a node callable rather than the raw subgraph, because the
        isolation and the depth check both happen *around* the child call.
        Nothing here reads the parent's edges, which is also the shape a
        tool-mode wrapper will need later.
        """
        flow_id = str(node.values.get("flow_id", "") or "").strip()
        if not flow_id:
            raise FlowBuildError(f"RunFlow '{node.id}' has no target flow selected")

        if self.build_depth >= _MAX_FLOW_DEPTH:
            raise FlowBuildError(
                f"RunFlow '{node.id}' exceeds the maximum flow nesting depth "
                f"({_MAX_FLOW_DEPTH}); check for a reference cycle"
            )

        try:
            definition_id = UUID(flow_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise FlowBuildError(f"RunFlow '{node.id}' has an invalid flow_id: {flow_id!r}") from exc

        definition = await self.repository.get_by_id(definition_id)
        if definition is None:
            raise FlowBuildError(f"RunFlow '{node.id}' references unknown flow '{flow_id}'")
        child_spec = getattr(definition, "flow_spec", None)
        if not child_spec:
            raise FlowBuildError(f"RunFlow '{node.id}' targets flow '{flow_id}', which has no published version")

        child = await FlowGraphBuilder(
            user_id=self.user_id,
            checkpointer=None,
            repository=self.repository,
            registry=self.registry,
            mcp_tools_map=self.mcp_tools_map,
            build_depth=self.build_depth + 1,
        ).build(FlowSpec.model_validate(child_spec))

        async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
            configurable = dict((config or {}).get("configurable", {}))
            depth = int(configurable.get("flow_depth", 0) or 0)
            if depth >= _MAX_FLOW_DEPTH:
                raise FlowBuildError(
                    f"RunFlow '{node.id}' exceeded the maximum flow nesting depth ({_MAX_FLOW_DEPTH}) at run time"
                )
            configurable["flow_depth"] = depth + 1
            child_config = {**(config or {}), "configurable": configurable}

            # Isolation: seed only the latest message, keep only the answer.
            seed = list(state.get("messages", []))[-1:]
            result = await child.ainvoke({"messages": seed, "scratch": {}, "arrivals": []}, child_config)

            produced = list(result.get("messages", []))[len(seed) :]
            answer = _extract_last_message_text(result)
            update: dict[str, Any] = {"scratch": {node.id: answer}}
            if produced:
                # Forward the child's own messages rather than re-wrapping the
                # text: a child ending in an agent produced an AIMessage, and
                # flattening that to some other type would lose what it is.
                update["messages"] = produced
            return update

        return _run

    async def _resolve_agent_ref(self, node: FlowNode) -> CompiledStateGraph:
        """Embed an existing classic agent as a subgraph — constraint #1's
        concrete proof. Mirrors Task 0's spike almost verbatim:
        `agents/graphs/builder.py` is called through its public API,
        unmodified, and compiled with `checkpointer=None` so the parent flow
        owns persistence (Task 0 finding A).
        """
        from agents.graphs.builder import GraphBuilder  # UNMODIFIED — do not edit

        agent_id = node.values.get("agent_id")
        if not agent_id:
            raise FlowBuildError(f"AgentRef '{node.id}' has no agent_id configured")

        try:
            definition_id = UUID(str(agent_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise FlowBuildError(f"AgentRef '{node.id}' has an invalid agent_id: {agent_id!r}") from exc

        # The flow spec is client-authored, so the id in it is scoped to who is
        # running the flow: without this, naming another user's definition ran
        # their agent with their prompt, tool grants and mail binding.
        definition = await self._definition_for_runner(definition_id)
        if definition is None:
            raise FlowBuildError(f"AgentRef '{node.id}' references unknown agent '{agent_id}'")

        if definition.graph_schema == GraphSchemaType.FLOW:
            raise FlowBuildError(
                f"AgentRef '{node.id}' targets '{agent_id}', which is itself "
                "flow-backed; a flow cannot reference another flow (design spec 5.4)"
            )

        builder = GraphBuilder(
            checkpointer=None,
            repository=self.repository,
            owner_ids=self._runner_owner_ids(),
        )
        return await builder.build_async(definition.graph_schema, definition.to_config())

    def _runner_owner_ids(self) -> list[str] | None:
        """Identities allowed to run definitions this flow pulls from the DB."""
        return [self.user_id] if self.user_id else None

    async def _is_flow_backed(self, agent_id: str) -> bool:
        """Whether ``agent_id`` names a flow-backed definition.

        Kept here rather than imported from the service layer: the builder
        already holds the repository and the schema enum, and reaching upward
        for this one predicate was the single edge that made ``agents`` and
        ``service`` import each other.
        """
        try:
            definition_id = UUID(agent_id)
        except (ValueError, TypeError, AttributeError):
            # A non-UUID sub-agent id names a built-in, never a flow.
            return False

        repository = self.repository
        if repository is None:
            from infrastructure.db.persistence_gateway import agent_definition_repository

            repository = agent_definition_repository()
        definition = await repository.get_by_id(definition_id)
        return definition is not None and definition.graph_schema == GraphSchemaType.FLOW

    async def _definition_for_runner(self, definition_id):
        owner_ids = self._runner_owner_ids()
        if owner_ids is None:
            return await self.repository.get_by_id(definition_id)
        return await self.repository.get_by_id_for_user(definition_id, owner_ids)

    async def _resolve_supervisor(self, node: FlowNode) -> CompiledStateGraph:
        """Compile a Supervisor node by delegating to GraphBuilder.build_async('supervisor', ...).

        Sub-agents are resolved from sub_agents (list of agent IDs) through
        GraphBuilder's existing sub_agent_ids mechanism. Flow-backed agents
        are rejected explicitly to satisfy section 5.4.
        """
        from agents.graphs.builder import GraphBuilder

        sub_agents = node.values.get("sub_agents")
        if not sub_agents:
            raise FlowBuildError(f"Supervisor node '{node.id}' must declare at least one sub_agent")

        if isinstance(sub_agents, str):
            sub_agent_ids = [sub_agents]
        elif isinstance(sub_agents, list):
            sub_agent_ids = [str(s) for s in sub_agents if s]
        else:
            sub_agent_ids = []

        if not sub_agent_ids:
            raise FlowBuildError(f"Supervisor node '{node.id}' must declare at least one sub_agent")

        for sub_id in sub_agent_ids:
            is_flow = await self._is_flow_backed(sub_id)
            if is_flow:
                raise FlowBuildError(
                    f"Supervisor node '{node.id}' references '{sub_id}', which is flow-backed; "
                    "a flow cannot embed another flow (design spec 5.4)"
                )

        supervisor_prompt = str(node.values.get("supervisor_prompt") or "You are a team supervisor.")
        config = {
            "supervisor_prompt": supervisor_prompt,
            "sub_agent_ids": sub_agent_ids,
        }

        builder = GraphBuilder(
            checkpointer=None,
            repository=self.repository,
            mcp_tools_map=self.mcp_tools_map,
            owner_ids=self._runner_owner_ids(),
        )
        return await builder.build_async("supervisor", config)

    @staticmethod
    def _make_router_fn(router_node: FlowNode, edges: list[FlowEdge]):
        routes_table = router_node.values.get("routes", [])
        label_to_target = {edge.source_handle: edge.target for edge in edges if edge.source == router_node.id}

        def _route(state: FlowState) -> str:
            # v2 rows: {source, operator, match_text, route}. ``source`` is a
            # Set Variable name, or blank for the latest message's text. v1
            # rows ({condition, route}) are rewritten to an ``is_truthy``
            # comparison by migrate_spec before build(), so this only ever
            # sees the v2 shape.
            scratch = state.get("scratch", {})
            for row in routes_table:
                if not isinstance(row, dict):
                    continue
                source = row.get("source", "")
                operator = row.get("operator") or "is_truthy"
                left = scratch.get(source) if source else _extract_last_message_text(state)
                if evaluate_comparison(operator, left, row.get("match_text", "")):
                    target = label_to_target.get(row.get("route"))
                    if target is not None:
                        return target
            default_target = label_to_target.get("default")
            if default_target is None:
                raise FlowBuildError(f"Router '{router_node.id}' has no matching route and no 'default' fallback")
            return default_target

        return _route

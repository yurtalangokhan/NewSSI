"""FlowAgent - runtime agent backed by a canvas-defined FlowSpec.

Mirrors dynamic_agent.py deliberately: same LazyLoadingAgent base, same
per-definition-id cache pattern, same fallback-graph-on-load-failure
behavior. A sibling class, not a subclass — design spec section 6.2.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph.state import CompiledStateGraph

from agents.lazy_agent import LazyLoadingAgent
from core.logger import get_logger

logger = get_logger(__name__)

# Per-definition-id cache, mirroring dynamic_agent.py's module-level cache.
_agent_cache: dict[str, FlowAgent] = {}


def get_cached_agent(definition_id: str) -> FlowAgent | None:
    """Return a previously loaded FlowAgent if present in cache."""
    return _agent_cache.get(definition_id)


def cache_agent(definition_id: str, agent: FlowAgent) -> None:
    """Store a loaded FlowAgent in cache."""
    _agent_cache[definition_id] = agent


def invalidate_agent_cache(definition_id: str) -> None:
    """Remove agent from cache (call after definition update/delete)."""
    _agent_cache.pop(definition_id, None)


class FlowAgent(LazyLoadingAgent):
    """A dynamic agent whose graph is compiled from a canvas FlowSpec.

    Wraps LazyLoadingAgent and delegates graph construction to
    FlowGraphBuilder. On any load failure the agent falls back to a minimal
    error-explaining graph rather than raising — the same behavior
    DynamicAgent already has for classic agents.
    """

    def __init__(
        self,
        flow_spec: dict[str, Any] | None,
        *,
        definition_id: str,
        user_id: str | None = None,
        repository: Any | None = None,
        name_hint: str | None = None,
        flow_version_no: int | None = None,
    ) -> None:
        super().__init__()
        self._flow_spec_raw = flow_spec
        self._definition_id = definition_id
        self._user_id = user_id
        self._repository = repository
        self._name_hint = name_hint
        # The published agent_flow_versions.version_no this agent's graph was
        # compiled from. Emitted once per run and persisted with the message
        # so the chat-side flow strip pins to the version that actually ran,
        # not whatever is published by the time the message is re-read. The
        # per-definition agent cache is evicted on publish, so a cached
        # FlowAgent's version_no can never drift from its compiled graph.
        self.flow_version_no = flow_version_no
        self._load_failed = False
        self._mcp_tools_map: dict[str, Any] = {}
        self._final_stage_node_ids: set[str] = set()
        self._final_stage_in_cycle: bool = False

    @property
    def name(self) -> str:
        return self._name_hint or f"flow-{self._definition_id}"

    @property
    def description(self) -> str:
        from agents.graphs.schemas import get_schema

        schema = get_schema("flow")
        return schema.description if schema else "Flow agent"

    @property
    def agent_type(self) -> str:
        return "flow"

    @property
    def graph_schema(self) -> str:
        return "flow"

    @property
    def final_stage_node_ids(self) -> set[str]:
        """Canvas node ids whose output is the flow's final answer bubble.
        Every earlier stage folds into the per-stage timeline. Empty for the
        fallback graph. See flow_builder._resolve_final_stage_nodes."""
        return set(self._final_stage_node_ids)

    @property
    def final_stage_in_cycle(self) -> bool:
        """True when a final node sits on a loop cycle — the live layer folds
        every iteration and promotes only the last to the answer bubble."""
        return self._final_stage_in_cycle

    async def _load_mcp_tools(self) -> None:
        try:
            from agents.mcp_loader import load_mcp_tools_map

            self._mcp_tools_map = await load_mcp_tools_map(self.name)
        except Exception as e:
            logger.warning("Could not load MCP tools for FlowAgent '%s': %s", self.name, e)
            self._mcp_tools_map = {}

    async def load(self) -> None:
        if self._loaded:
            return

        try:
            await self._load_mcp_tools()
            self._graph = await self._build_graph()
            self._loaded = True
            self._load_failed = False
            logger.info("FlowAgent '%s' loaded (definition_id=%s)", self.name, self._definition_id)
        except Exception as e:
            logger.error("FlowAgent load failed (definition_id=%s): %s", self._definition_id, e)
            self._graph = await self._create_fallback_graph()
            self._loaded = True
            self._load_failed = True

    async def _build_graph(self) -> CompiledStateGraph:
        from agents.graphs.flow_builder import FlowGraphBuilder
        from core.exceptions import FlowValidationError
        from domain.flows.validator import validate as validate_flow_spec
        from models.flows import FlowSpec

        if not self._flow_spec_raw:
            raise ValueError(f"FlowAgent '{self._definition_id}' has no flow_spec to compile")

        spec = FlowSpec.model_validate(self._flow_spec_raw)

        # Migrate on read (design spec 4.6): a published spec may predate a
        # template version bump (e.g. Router v1->v2). The next save rewrites
        # the stored spec; here it is a pure, in-memory rewrite so the
        # validator and compiler only ever see current-version values.
        from domain.flows.migrations import migrate_spec

        spec = migrate_spec(spec)

        # Structural backstop for a spec that reached here without passing
        # publish (e.g. a client that bypassed the create-page gate and
        # never published): refuse to compile a graph that would silently
        # echo the user's input instead of running a real flow. Pure /
        # I/O-free — safe on every cache-miss build; published specs
        # already satisfy this in publish_flow().
        structural = validate_flow_spec(spec)
        if not structural.valid:
            detail = "; ".join(f"{i.code}: {i.message}" for i in structural.errors)
            logger.error(
                "FlowAgent '%s' (definition_id=%s) has an invalid flow_spec: %s",
                self.name,
                self._definition_id,
                detail,
            )
            raise FlowValidationError(list(structural.errors))

        repository = self._repository
        if repository is None:
            from service.persistence_gateway import agent_definition_repository

            repository = agent_definition_repository()

        builder = FlowGraphBuilder(
            user_id=self._user_id,
            checkpointer=getattr(self, "_checkpointer", None),
            repository=repository,
            mcp_tools_map=self._mcp_tools_map,
        )
        graph = await builder.build(spec)
        self._final_stage_node_ids = set(builder.final_stage_node_ids)
        self._final_stage_in_cycle = bool(builder.final_stage_in_cycle)
        return graph

    async def _create_fallback_graph(self) -> CompiledStateGraph:
        """Minimal fallback graph when load fails. Mirrors
        DynamicAgent._create_fallback_graph's shape and reasoning."""
        self._final_stage_node_ids = set()
        self._final_stage_in_cycle = False
        from agents.graphs.builder import GraphBuilder
        from core import get_model, settings

        return await GraphBuilder(
            model=get_model(settings.DEFAULT_MODEL),
            system_prompt=(
                "This flow could not be loaded due to a configuration error. "
                "Please contact an administrator."
            ),
            mcp_tools_map={},
            checkpointer=getattr(self, "_checkpointer", None),
        ).build_async("zero_shot")

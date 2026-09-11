"""ASC-0 characterization: agent runtime memory/brain/pipeline behavior.

These tests record the *current* supported behavior of the production dynamic
runtime so that later refactors (composer cutover, legacy deletion) have a
regression and compatibility baseline. They do not change any production module.

Key findings characterized here (see current-state-analysis.md):
- `memory_type == "long_term"` enables long-term memory; `"buffer"` and `"none"`
  are advertised but NOT honored by the dynamic runtime (treated as no memory).
- `brain_type` is stored but not read by the dynamic runtime; only `llm` model
  selection occurs regardless of the advertised brain type.
- Pipeline ordering is prompt-driven: submitted `stages` are passed through in
  submission order and the builder adds no structural stage-to-stage
  transition contract.
"""

from types import SimpleNamespace
from uuid import UUID

import pytest
from langchain_core.messages import AIMessage

from agents.dynamic_agent import DynamicAgent
from agents.graphs.builder import GraphBuilder
from agents.graphs.schemas import GraphSchemaType
from agents.lazy_agent import LazyLoadingAgent


def _fake_builder(monkeypatch):
    """Install a FakeBuilder that records GraphBuilder kwargs and avoids models."""
    calls: dict = {}

    class FakeBuilder:
        def __init__(self, **kwargs):
            calls["builder_kwargs"] = kwargs

        def build(self, *_a, **_k):
            return None

        async def build_async(self, *_a, **_k):
            return None

    monkeypatch.setattr("agents.dynamic_agent.GraphBuilder", FakeBuilder)
    monkeypatch.setattr("agents.dynamic_agent.get_model_from_config", lambda *_a: object())
    return calls


def test_memory_type_long_term_enables_long_term_memory(monkeypatch):
    calls = _fake_builder(monkeypatch)
    agent = DynamicAgent({"name": "a", "graph_schema": "zero_shot", "memory_type": "long_term"})
    agent._prepare_graph_build()
    assert calls["builder_kwargs"]["memory_enabled"] is True


def test_memory_type_buffer_is_not_honored_by_dynamic_runtime(monkeypatch):
    """`buffer` is advertised but the runtime treats it as no long-term memory."""
    calls = _fake_builder(monkeypatch)
    agent = DynamicAgent({"name": "a", "graph_schema": "zero_shot", "memory_type": "buffer"})
    agent._prepare_graph_build()
    assert calls["builder_kwargs"]["memory_enabled"] is False


def test_memory_type_none_disables_long_term_memory(monkeypatch):
    """`none` is the supported configuration for disabling long-term memory."""
    calls = _fake_builder(monkeypatch)
    agent = DynamicAgent({"name": "a", "graph_schema": "zero_shot", "memory_type": "none"})
    agent._prepare_graph_build()
    assert calls["builder_kwargs"]["memory_enabled"] is False


def test_brain_type_is_not_read_by_dynamic_runtime(monkeypatch):
    """DynamicAgent omits brain_type from the current builder contract."""
    model = object()
    calls_guard = _fake_builder(monkeypatch)
    monkeypatch.setattr("agents.dynamic_agent.get_model_from_config", lambda *_a: model)
    DynamicAgent(
        {"name": "a", "graph_schema": "zero_shot", "memory_type": "none", "brain_type": "guard"}
    )._prepare_graph_build()
    guard_kwargs = calls_guard["builder_kwargs"]

    calls_llm = _fake_builder(monkeypatch)
    monkeypatch.setattr("agents.dynamic_agent.get_model_from_config", lambda *_a: model)
    DynamicAgent(
        {"name": "a", "graph_schema": "zero_shot", "memory_type": "none", "brain_type": "llm"}
    )._prepare_graph_build()
    llm_kwargs = calls_llm["builder_kwargs"]

    assert "brain_type" not in guard_kwargs
    assert "brain_type" not in llm_kwargs
    assert guard_kwargs["model"] is model
    assert llm_kwargs["model"] is model
    assert guard_kwargs["memory_enabled"] == llm_kwargs["memory_enabled"]


def test_pipeline_stages_preserved_without_deterministic_ordering(monkeypatch):
    """Pipeline passes submitted stages through; no structural transition contract."""
    _fake_builder(monkeypatch)
    stages = [
        {"name": "research", "prompt": "Research the topic."},
        {"name": "draft", "prompt": "Draft the answer."},
    ]
    agent = DynamicAgent(
        {
            "name": "pipe",
            "graph_schema": "pipeline",
            "stages": stages,
            "pipeline_prompt": "Go through every stage.",
        }
    )
    _, schema_type, build_config = agent._prepare_graph_build()

    assert schema_type == GraphSchemaType.PIPELINE
    # Stages are preserved in submission order (prompt-driven, not reordered).
    assert build_config["stages"] == stages
    # The builder does not add a structural ordering contract between stages.
    assert "stage_transitions" not in build_config


@pytest.mark.xfail(
    strict=True,
    reason="Current pipeline delegates routing to a supervisor prompt instead of graph edges.",
)
def test_pipeline_graph_exposes_deterministic_stage_transitions(monkeypatch):
    """The future pipeline strategy must expose each stage transition structurally."""
    import langgraph_supervisor

    captured = {}

    class FakeWorkflow:
        def __init__(self, **kwargs):
            self.stage_transitions = kwargs.get("stage_transitions")

        def compile(self, **_kwargs):
            return self

    def fake_create_supervisor(_agents, **kwargs):
        captured.update(kwargs)
        return FakeWorkflow(**kwargs)

    monkeypatch.setattr(langgraph_supervisor, "create_supervisor", fake_create_supervisor)

    builder = GraphBuilder(model=object())
    monkeypatch.setattr(
        builder,
        "_build_sub_agent_graph",
        lambda config: {"name": config["name"]},
    )

    graph = builder._build_pipeline(
        {
            "name": "ordered-pipeline",
            "stages": [{"name": "intake"}, {"name": "verify"}, {"name": "publish"}],
        }
    )

    assert captured["stage_transitions"] == [
        ("intake", "verify"),
        ("verify", "publish"),
    ]
    assert graph.stage_transitions == [
        ("intake", "verify"),
        ("verify", "publish"),
    ]


@pytest.mark.asyncio
async def test_lazy_runtime_delegates_invoke_stream_events_and_checkpoint_state():
    """The current lazy runtime exposes one graph contract to all callers."""

    class FakeGraph:
        async def ainvoke(self, input, config=None, **kwargs):
            return {"messages": [AIMessage(content="invoked")], "input": input}

        async def astream(self, input, config=None, **kwargs):
            yield ("updates", {"model": {"messages": [AIMessage(content="streamed")]}})

        async def astream_events(self, input, config=None, version="v2", **kwargs):
            yield {"event": "on_chain_end", "data": {"output": "event"}}

        async def aget_state(self, config=None, **kwargs):
            return {"config": config, "values": {"messages": []}}

    class CharacterizationAgent(LazyLoadingAgent):
        async def load(self):
            self._graph = FakeGraph()
            self._loaded = True

    agent = CharacterizationAgent()
    config = {"configurable": {"thread_id": "asc0-runtime"}}

    invoked = await agent.ainvoke({"messages": ["hello"]}, config=config)
    chunks = [chunk async for chunk in agent.astream({"messages": ["hello"]}, config=config)]
    events = [event async for event in agent.astream_events({"messages": ["hello"]}, config=config)]
    state = await agent.aget_state(config=config)

    assert invoked["messages"][0].content == "invoked"
    assert chunks[0][0] == "updates"
    assert events == [{"event": "on_chain_end", "data": {"output": "event"}}]
    assert state["config"] == config


@pytest.mark.asyncio
async def test_uuid_resolution_returns_dynamic_runtime_for_agent_definition(monkeypatch):
    """A UUID definition resolves through the dynamic runtime path."""
    from service.AssistantAgentService import AssistantAgentService

    definition_id = UUID("00000000-0000-0000-0000-0000000000a0")
    definition = SimpleNamespace(id=definition_id, name="dynamic-definition")
    runtime = object()
    service = object.__new__(AssistantAgentService)

    async def fake_get_graph_and_config(agent_id):
        assert str(agent_id) == str(definition_id)
        return str(definition_id), {}

    async def fake_get_definition(agent_id):
        assert agent_id == definition_id
        return definition

    async def fake_create(agent):
        assert agent is definition
        return runtime

    monkeypatch.setattr(service, "get_graph_and_config", fake_get_graph_and_config)
    monkeypatch.setattr(service, "_get_agent_definition", fake_get_definition)
    monkeypatch.setattr(service, "_get_or_create_dynamic_agent", fake_create)

    assert await service.get_configured_agent(definition_id) is runtime


@pytest.mark.asyncio
async def test_resolver_cache_reuses_loaded_dynamic_agent(monkeypatch):
    """AssistantAgentService reuses a loaded definition runtime by UUID."""
    from service.AssistantAgentService import AssistantAgentService

    definition_id = UUID("00000000-0000-0000-0000-0000000000a1")
    definition = SimpleNamespace(
        id=definition_id,
        name="cached-definition",
        to_config=lambda: {"name": "cached-definition"},
    )
    load_count = 0

    class FakeDynamicAgent:
        def __init__(self, agent_config, **_kwargs):
            assert agent_config["name"] == "cached-definition"

        async def load(self):
            nonlocal load_count
            load_count += 1

        def get_graph(self):
            return SimpleNamespace(checkpointer=None)

    monkeypatch.setattr("agents.dynamic_agent.DynamicAgent", FakeDynamicAgent)
    monkeypatch.setattr("service.CheckpointerService.get_checkpointer", lambda: None)

    service = object.__new__(AssistantAgentService)
    try:
        first = await service._get_or_create_dynamic_agent(definition)
        second = await service._get_or_create_dynamic_agent(definition)
    finally:
        from agents.dynamic_agent import invalidate_agent_cache

        invalidate_agent_cache(str(definition_id))

    assert first is second
    assert load_count == 1


def test_nested_definition_preserves_manager_schema_for_composition(monkeypatch):
    """Nested supervisor definitions stay nested instead of becoming ReAct agents."""
    calls = {}

    def fake_build(_self, schema_type, config):
        calls["schema_type"] = schema_type
        calls["config"] = config
        return {"schema": schema_type}

    monkeypatch.setattr(GraphBuilder, "build", fake_build)
    graph = GraphBuilder(model=object())._build_sub_agent_graph(
        {
            "name": "nested-supervisor",
            "graph_schema": "supervisor",
            "sub_agents": [{"name": "leaf"}],
        }
    )

    assert graph == {"schema": GraphSchemaType.SUPERVISOR}
    assert calls["config"]["name"] == "nested-supervisor"


def test_dynamic_agent_cache_reuses_and_invalidates_definition_runtime():
    """The current definition cache is keyed by definition ID and invalidatable."""
    from agents.dynamic_agent import (
        _agent_cache,
        cache_agent,
        get_cached_agent,
        invalidate_agent_cache,
    )

    definition_id = "asc0-cache-characterization"
    agent = DynamicAgent({"name": "cached"})
    try:
        cache_agent(definition_id, agent)
        assert get_cached_agent(definition_id) is agent
    finally:
        invalidate_agent_cache(definition_id)

    assert get_cached_agent(definition_id) is None
    assert definition_id not in _agent_cache

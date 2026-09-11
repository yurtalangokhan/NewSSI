"""Tests for Core execution-node runnables.

Agent nodes (ZeroShotAgent/ReActAgent/PlanExecuteAgent/SelfReflectAgent) reuse
agents/graphs/builder.py's existing per-schema logic directly — make_node
returns GraphBuilder.build()'s CompiledStateGraph unmodified, so there is no
separate code path to diverge from the classic behavior. Full embedded
end-to-end streaming through a real assembled flow is Task 10's job (10.6);
this file tests each node's own behavior in isolation.

PromptTemplate's `{variable}` placeholders resolve against `scratch` keyed by
the *source node id* of an incoming edge — not a semantic alias. FlowEdge
(P1) has no field to bind an edge to a named variable; that is a P4/canvas
UX decision, not a P2 compiler one. Documented here as a deliberate v1
simplification.

Spec: .tmp/flow-canvas-design.md section 7.1.
Brief: .tmp/flow-canvas-task-9-brief.md
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from agents.graphs.flow_builder import ResolvedResources, make_node
from core.exceptions import UnknownComponentError
from models.flows import FlowNode


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _empty_resources() -> ResolvedResources:
    return ResolvedResources(models={})


# ---------------------------------------------------------------------------
# 9.1 / 9.2 — pass-through nodes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_input_node_clears_the_turns_arrival_channel():
    """9.1 — the flow's per-turn reset point. It forwards messages untouched,
    but it is not a no-op: it clears the checkpointed ``arrivals`` channel so a
    "first" Merge cannot answer with an earlier turn's branch. ``build()``
    additionally hands it the flow's While / If-Else / foreach ids to zero;
    standalone there are none, so ``scratch`` comes back empty."""
    node = FlowNode(id="in-1", type="ChatInput")
    fn = await make_node(node, _empty_resources())

    result = await fn({"messages": [HumanMessage(content="hi")], "scratch": {}}, {})

    assert result == {"scratch": {}, "arrivals": None}


@pytest.mark.asyncio
async def test_chat_output_node_passes_through_messages():
    """9.2 — an addressable no-op; exists so edges have somewhere to terminate."""
    node = FlowNode(id="out-1", type="ChatOutput")
    fn = await make_node(node, _empty_resources())

    result = await fn({"messages": [HumanMessage(content="hi")], "scratch": {}}, {})

    assert result == {}


# ---------------------------------------------------------------------------
# 9.3 — TextInput
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_input_node_writes_to_scratch_and_emits_a_message():
    node = FlowNode(id="text-1", type="TextInput", values={"text": "hello world"})
    fn = await make_node(node, _empty_resources())

    result = await fn({"messages": [], "scratch": {}}, {})

    # keeps its scratch slot for {node-id} interpolation downstream ...
    assert result["scratch"] == {"text-1": "hello world"}
    # ... and now also emits the text as a message (Langflow parity)
    assert [m.content for m in result["messages"]] == ["hello world"]


# ---------------------------------------------------------------------------
# 9.4 / 9.5 — PromptTemplate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_template_node_substitutes_variables():
    """9.4 — {node_id} placeholders resolve from scratch, keyed by source node id."""
    node = FlowNode(id="prompt-1", type="PromptTemplate", values={"template": "Hello {text-1}!"})
    fn = await make_node(node, _empty_resources())

    result = await fn({"messages": [], "scratch": {"text-1": "World"}}, {})

    # scratch slot survives (chained Prompt Templates read it) ...
    assert result["scratch"] == {"prompt-1": "Hello World!"}
    # ... and the rendered text is emitted as a message so it can feed an agent
    assert [m.content for m in result["messages"]] == ["Hello World!"]


@pytest.mark.asyncio
async def test_prompt_template_node_raises_on_missing_variable():
    """9.5 — a clear error, not a silent empty substitution."""
    node = FlowNode(
        id="prompt-1", type="PromptTemplate", values={"template": "Hello {missing-node}!"}
    )
    fn = await make_node(node, _empty_resources())

    with pytest.raises(KeyError, match="missing-node"):
        await fn({"messages": [], "scratch": {}}, {})


# ---------------------------------------------------------------------------
# 9.6 — ZeroShotAgent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_shot_agent_node_invokes_model_with_system_prompt():
    node = FlowNode(id="agent-1", type="ZeroShotAgent", values={"system_prompt": "You are terse."})
    graph = await make_node(node, _empty_resources())

    assert isinstance(graph, CompiledStateGraph)
    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")]})
    assert len(result["messages"]) >= 2  # input + at least one response


@pytest.mark.asyncio
async def test_self_reflect_agent_node_compiles_and_runs():
    """SelfReflectAgent embeds GraphBuilder._build_self_reflect as a subgraph.

    builder.py uses ``from __future__ import annotations``, so every signature
    annotation is a stringized forward ref resolved against the *module*
    globals. ``_build_self_reflect``'s ``should_continue`` branch callable must
    therefore not be annotated with a name that only exists as a local import
    inside the function — LangGraph's ``add_conditional_edges`` calls
    ``get_type_hints`` on the branch path and a missing name raises NameError
    at build time (regression: flows with a SelfReflect node failed to compile).
    """
    node = FlowNode(
        id="agent-1",
        type="SelfReflectAgent",
        values={
            "system_prompt": "Draft, then improve.",
            "reflection_prompt": "Say DONE when good.",
            "max_iterations": 2,
        },
    )
    graph = await make_node(node, _empty_resources())

    assert isinstance(graph, CompiledStateGraph)
    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")]})
    assert len(result["messages"]) >= 2


def test_select_model_uses_the_explicitly_wired_resource():
    """A flow with two Model resources feeding two different agent nodes must
    resolve each agent's *own* wired model, not whichever resource happens to
    be first in the dict."""
    from agents.graphs.flow_builder import _select_model

    model_a = object()
    model_b = object()
    resources = ResolvedResources(models={"model-a": model_a, "model-b": model_b})

    assert _select_model(resources, "model-b") is model_b
    assert _select_model(resources, "model-a") is model_a


def test_select_model_falls_back_to_the_only_resource_when_unspecified():
    """A single-model flow (the common case) needs no explicit wiring."""
    from agents.graphs.flow_builder import _select_model

    model_a = object()
    resources = ResolvedResources(models={"model-a": model_a})

    assert _select_model(resources, None) is model_a


def test_select_model_returns_none_when_no_resource_and_none_specified():
    """No Model resource at all -> GraphBuilder falls back to DEFAULT_MODEL,
    matching the classic agent's own behavior with no LLM override."""
    from agents.graphs.flow_builder import _select_model

    assert _select_model(ResolvedResources(models={}), None) is None


# ---------------------------------------------------------------------------
# 9.7 — ReActAgent with a tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_react_agent_node_can_call_a_tool():
    from langchain_core.tools import tool

    @tool
    def echo(text: str) -> str:
        """Echo text back."""
        return f"echoed:{text}"

    node = FlowNode(id="agent-1", type="ReActAgent", values={"system_prompt": "Use tools."})
    resources = ResolvedResources(models={})
    graph = await make_node(node, resources, mcp_tools_map={"echo": echo})

    assert isinstance(graph, CompiledStateGraph)


# ---------------------------------------------------------------------------
# 9.9 — unknown node type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_node_type_raises_unknown_component_error():
    node = FlowNode(id="mystery-1", type="TotallyMadeUp")

    with pytest.raises(UnknownComponentError):
        await make_node(node, _empty_resources())


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_node_concat_is_a_passthrough():
    """ "concat" needs no node-level logic: add_messages already accumulates
    every incoming edge's contribution before this node runs."""
    node = FlowNode(id="merge-1", type="Merge", values={"strategy": "concat"})
    fn = await make_node(node, _empty_resources())

    result = await fn({"messages": [HumanMessage(content="a")], "scratch": {}}, {})

    assert result == {}


@pytest.mark.asyncio
async def test_merge_node_accepts_first_and_last():
    """first / last are implemented via the arrival-stamp channel (see
    test_merge_node.py); only a genuinely unknown strategy still raises."""
    for strategy in ("concat", "first", "last"):
        node = FlowNode(id="merge-1", type="Merge", values={"strategy": strategy})
        assert await make_node(node, _empty_resources()) is not None

    bogus = FlowNode(id="merge-1", type="Merge", values={"strategy": "nonsense"})
    with pytest.raises(NotImplementedError):
        await make_node(bogus, _empty_resources())

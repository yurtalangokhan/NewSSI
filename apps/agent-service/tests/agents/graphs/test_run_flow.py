"""Tests for RunFlow — one flow running another as a node.

Isolation is the point: the child is invoked with only the latest message and
only its answer returns, so ``scratch`` and ``arrivals`` never cross the
boundary. The child compiles with ``checkpointer=None`` — the parent owns
persistence, exactly as ``_resolve_agent_ref`` has done since Phase 0.

Recursion is blocked twice over: ``FlowGraphBuilder.build_depth`` stops a
reference cycle from hanging the *compiler*, and ``flow_depth`` in
``RunnableConfig`` stops one from hanging a *run*. The config counter is
deliberately not in ``FlowState``: a future tool-mode call reaches a flow
through LangChain's tool path, which carries config but not our state.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.graphs.flow import FlowGraphBuilder
from core.exceptions import FlowBuildError
from schemas.flows import FlowSpec


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


# SetVariable writes scratch but emits no message, so the child also carries a
# Prompt Template: that is what actually produces the answer the parent reads.
CHILD_SPEC = {
    "nodes": [
        {"id": "in-1", "type": "ChatInput"},
        {"id": "keep", "type": "SetVariable", "values": {"name": "ortak", "value": "CHILD"}},
        {"id": "say", "type": "PromptTemplate", "values": {"template": "CHILD"}},
        {"id": "out-1", "type": "ChatOutput"},
    ],
    "edges": [
        {
            "id": "e1",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "keep",
            "targetHandle": "input",
        },
        {
            "id": "e2",
            "source": "keep",
            "sourceHandle": "output",
            "target": "say",
            "targetHandle": "variables",
        },
        {
            "id": "e3",
            "source": "say",
            "sourceHandle": "text",
            "target": "out-1",
            "targetHandle": "message",
        },
    ],
}

PARENT_SPEC = {
    "nodes": [
        {"id": "in-1", "type": "ChatInput"},
        {"id": "keep", "type": "SetVariable", "values": {"name": "ortak", "value": "PARENT"}},
        {
            "id": "rf-1",
            "type": "RunFlow",
            "values": {"flow_id": "11111111-1111-1111-1111-111111111111"},
        },
        {"id": "out-1", "type": "ChatOutput"},
    ],
    "edges": [
        {
            "id": "e1",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "keep",
            "targetHandle": "input",
        },
        {
            "id": "e2",
            "source": "keep",
            "sourceHandle": "output",
            "target": "rf-1",
            "targetHandle": "input",
        },
        {
            "id": "e3",
            "source": "rf-1",
            "sourceHandle": "output",
            "target": "out-1",
            "targetHandle": "message",
        },
    ],
}

# A flow whose RunFlow points at itself — the shape publish-time cycle
# detection rejects, but which the playground can still hand the compiler.
SELF_SPEC = {
    "nodes": [
        {"id": "in-1", "type": "ChatInput"},
        {
            "id": "rf-1",
            "type": "RunFlow",
            "values": {"flow_id": "22222222-2222-2222-2222-222222222222"},
        },
        {"id": "out-1", "type": "ChatOutput"},
    ],
    "edges": [
        {
            "id": "e1",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "rf-1",
            "targetHandle": "input",
        },
        {
            "id": "e2",
            "source": "rf-1",
            "sourceHandle": "output",
            "target": "out-1",
            "targetHandle": "message",
        },
    ],
}


class _Definition:
    graph_schema = "flow"
    name = "Child"

    def __init__(self, spec):
        self.flow_spec = spec


class _Repo:
    """Every lookup returns the same definition — enough for a one-level call."""

    def __init__(self, spec=CHILD_SPEC):
        self._spec = spec

    async def get_by_id(self, definition_id):
        return _Definition(self._spec)


class _MissingRepo:
    async def get_by_id(self, definition_id):
        return None


class _UnpublishedRepo:
    async def get_by_id(self, definition_id):
        return _Definition(None)


async def _parent_graph(repo=None):
    return await FlowGraphBuilder(repository=repo or _Repo()).build(
        FlowSpec.model_validate(PARENT_SPEC)
    )


# ---------------------------------------------------------------------------
# The call itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_child_runs_and_its_answer_reaches_the_parent():
    graph = await _parent_graph()
    result = await graph.ainvoke({"messages": [HumanMessage(content="hello")], "scratch": {}})
    assert result["messages"][-1].content == "CHILD"


@pytest.mark.asyncio
async def test_the_childs_variables_do_not_overwrite_the_parents():
    """Both flows write a variable called `ortak`. Isolation means the parent's
    value survives — otherwise two flows written by different people silently
    corrupt each other."""
    graph = await _parent_graph()
    result = await graph.ainvoke({"messages": [HumanMessage(content="hello")], "scratch": {}})
    assert result["scratch"]["ortak"] == "PARENT"


@pytest.mark.asyncio
async def test_the_childs_answer_is_stored_under_the_node_id():
    """Every execution node owns its id in scratch, so a downstream Prompt
    Template can read this one as {rf-1}."""
    graph = await _parent_graph()
    result = await graph.ainvoke({"messages": [HumanMessage(content="hello")], "scratch": {}})
    assert result["scratch"]["rf-1"] == "CHILD"


# ---------------------------------------------------------------------------
# Refusals at compile time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unknown_target_fails_the_build_clearly():
    with pytest.raises(FlowBuildError, match="unknown flow"):
        await _parent_graph(repo=_MissingRepo())


@pytest.mark.asyncio
async def test_an_unpublished_target_fails_the_build_clearly():
    with pytest.raises(FlowBuildError, match="no published version"):
        await _parent_graph(repo=_UnpublishedRepo())


# ---------------------------------------------------------------------------
# The two depth counters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_self_referencing_flow_stops_the_compiler_instead_of_hanging():
    """Publish-time cycle detection protects published flows; the playground
    compiles unvalidated drafts, so the compiler needs its own bound. Without
    it this call never returns."""
    with pytest.raises(FlowBuildError, match="nesting depth"):
        await FlowGraphBuilder(repository=_Repo(SELF_SPEC)).build(
            FlowSpec.model_validate(SELF_SPEC)
        )


@pytest.mark.asyncio
async def test_the_runtime_counter_stops_a_run_that_reached_the_bound():
    graph = await _parent_graph()
    with pytest.raises(FlowBuildError, match="at run time"):
        await graph.ainvoke(
            {"messages": [HumanMessage(content="hi")], "scratch": {}},
            {"configurable": {"flow_depth": 5}},
        )


@pytest.mark.asyncio
async def test_a_run_below_the_bound_is_untouched():
    graph = await _parent_graph()
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")], "scratch": {}},
        {"configurable": {"flow_depth": 1}},
    )
    assert result["messages"][-1].content == "CHILD"


# ---------------------------------------------------------------------------
# B19: two RunFlow branches into a first/last Merge — the real production
# shape (F13: SetVariable -> 2x RunFlow -> Merge -> ChatOutput). Only the
# chosen branch's answer should ever reach the transcript.
# ---------------------------------------------------------------------------

CHILD_A_SPEC = {
    "nodes": [
        {"id": "in-1", "type": "ChatInput"},
        {"id": "say", "type": "PromptTemplate", "values": {"template": "ANSWER-A"}},
        {"id": "out-1", "type": "ChatOutput"},
    ],
    "edges": [
        {
            "id": "e1",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "say",
            "targetHandle": "variables",
        },
        {
            "id": "e2",
            "source": "say",
            "sourceHandle": "text",
            "target": "out-1",
            "targetHandle": "message",
        },
    ],
}

CHILD_B_SPEC = {
    "nodes": [
        {"id": "in-1", "type": "ChatInput"},
        {"id": "say", "type": "PromptTemplate", "values": {"template": "ANSWER-B"}},
        {"id": "out-1", "type": "ChatOutput"},
    ],
    "edges": [
        {
            "id": "e1",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "say",
            "targetHandle": "variables",
        },
        {
            "id": "e2",
            "source": "say",
            "sourceHandle": "text",
            "target": "out-1",
            "targetHandle": "message",
        },
    ],
}

FLOW_ID_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
FLOW_ID_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class _TwoFlowRepo:
    def __init__(self):
        self._specs = {FLOW_ID_A: CHILD_A_SPEC, FLOW_ID_B: CHILD_B_SPEC}

    async def get_by_id(self, definition_id):
        return _Definition(self._specs[str(definition_id)])


def _merge_of_two_run_flows(strategy: str) -> dict:
    """ChatInput -> RunFlow(A) ------------------------> Merge -> ChatOutput
                 -> RunFlow(B) -> PromptTemplate(relay) -> Merge
    B's branch has one extra hop so it reaches Merge one super-step later —
    same determinism trick as _two_branch_merge in test_merge_node.py."""
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "rf-a", "type": "RunFlow", "values": {"flow_id": FLOW_ID_A}},
            {"id": "rf-b", "type": "RunFlow", "values": {"flow_id": FLOW_ID_B}},
            {"id": "relay", "type": "PromptTemplate", "values": {"template": "{rf-b}"}},
            {"id": "merge-1", "type": "Merge", "values": {"strategy": strategy}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "rf-a",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "rf-b",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "rf-b",
                "sourceHandle": "output",
                "target": "relay",
                "targetHandle": "variables",
            },
            {
                "id": "e4",
                "source": "rf-a",
                "sourceHandle": "output",
                "target": "merge-1",
                "targetHandle": "input",
            },
            {
                "id": "e5",
                "source": "relay",
                "sourceHandle": "text",
                "target": "merge-1",
                "targetHandle": "input",
            },
            {
                "id": "e6",
                "source": "merge-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


@pytest.mark.asyncio
async def test_last_merge_of_two_subflows_shows_only_the_winning_answer():
    spec = FlowSpec.model_validate(_merge_of_two_run_flows("last"))
    graph = await FlowGraphBuilder(repository=_TwoFlowRepo()).build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    contents = [m.content for m in result["messages"]]
    assert contents == ["go", "ANSWER-B"]  # no leftover ANSWER-A bubble
    # AIMessage, not HumanMessage: the persistence layer keys off type=="ai"
    # to decide "this is the assistant's reply" — get this wrong and the
    # live stream still shows the right text, but nothing ever gets saved
    # to chat history (a reload shows the question with no answer).
    assert isinstance(result["messages"][-1], AIMessage)


@pytest.mark.asyncio
async def test_first_merge_of_two_subflows_shows_only_the_winning_answer():
    spec = FlowSpec.model_validate(_merge_of_two_run_flows("first"))
    graph = await FlowGraphBuilder(repository=_TwoFlowRepo()).build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    contents = [m.content for m in result["messages"]]
    assert contents == ["go", "ANSWER-A"]  # no leftover ANSWER-B bubble

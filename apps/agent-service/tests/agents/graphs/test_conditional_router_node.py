"""Tests for the ConditionalRouter ("If-Else") node — a content-driven branch
that may own a cycle.

Two concerns:

- **Routing** — the latest message is compared with ``match_text`` via
  ``operator`` and the true / false branch is taken accordingly.
- **R2 ("no infinite loop")** — when a branch is wired back upstream, the
  per-turn iteration count must stop the cycle at ``max_iterations`` by
  forcing ``default_route``, exactly like Loop's bound.

Reuses the same ``evaluate_comparison`` the validator uses — one comparison
mini-language, not two.

Companion of ``test_loop_node.py``.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agents.graphs.flow_builder import FlowGraphBuilder, _make_condrouter_node
from domain.flows.comparison import evaluate_comparison
from models.flows import FlowNode, FlowSpec


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _branch_flow_dict(
    *,
    operator: str = "contains",
    match_text: str = "DONE",
    case_sensitive: bool = True,
    max_iterations: int = 5,
    default_route: str = "false_result",
    strip_match: bool = False,
    input_source: str = "",
    true_case_message: str = "",
    false_case_message: str = "",
) -> dict:
    """ChatInput -> If-Else -[true]-> ChatOutput
    -[false]-> Agent -> (back to If-Else)"""
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {
                "id": "cr-1",
                "type": "ConditionalRouter",
                "values": {
                    "operator": operator,
                    "match_text": match_text,
                    "case_sensitive": case_sensitive,
                    "max_iterations": max_iterations,
                    "default_route": default_route,
                    "strip_match": strip_match,
                    "input_source": input_source,
                    "true_case_message": true_case_message,
                    "false_case_message": false_case_message,
                },
            },
            {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "cr-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "cr-1",
                "sourceHandle": "true_result",
                "target": "out-1",
                "targetHandle": "message",
            },
            {
                "id": "e3",
                "source": "cr-1",
                "sourceHandle": "false_result",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e4",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "cr-1",
                "targetHandle": "input",
            },
        ],
    }


# ---------------------------------------------------------------------------
# evaluate_comparison — the operator table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("operator", "left", "right", "expected"),
    [
        ("equals", "abc", "abc", True),
        ("equals", "abc", "abd", False),
        ("not_equals", "abc", "abd", True),
        ("contains", "hello world", "world", True),
        ("contains", "hello world", "mars", False),
        ("not_contains", "hello world", "mars", True),
        ("starts_with", "hello world", "hello", True),
        ("starts_with", "hello world", "world", False),
        ("ends_with", "hello world", "world", True),
        ("regex", "hello world", r"hel+o", True),
        ("regex", "say hello", r"hello", False),  # re.match is anchored
        ("regex", "abc", "(", False),  # invalid pattern -> False, no raise
        ("less_than", "3", "10", True),
        ("less_than_or_equal", "10", "10", True),
        ("greater_than", "10", "3", True),
        ("greater_than_or_equal", "3", "10", False),
        ("greater_than", "not-a-number", "3", False),
        ("definitely_not_an_operator", "a", "a", False),
    ],
)
def test_evaluate_comparison_operator_table(operator, left, right, expected):
    assert evaluate_comparison(operator, left, right) is expected


def test_evaluate_comparison_case_insensitive():
    assert evaluate_comparison("equals", "ABC", "abc", case_sensitive=False) is True
    assert evaluate_comparison("equals", "ABC", "abc", case_sensitive=True) is False


def test_evaluate_comparison_regex_ignores_case_sensitive_flag():
    # matches Langflow: case_sensitive does not apply to regex
    assert evaluate_comparison("regex", "ABC", "abc", case_sensitive=False) is False


def test_evaluate_comparison_does_not_execute_code():
    payload = "__import__('os').system('echo pwned')"
    # treated as a literal operand, never evaluated
    assert evaluate_comparison("equals", "hi", payload) is False
    assert evaluate_comparison("contains", payload, "system") is True


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_to_true_branch_when_condition_matches():
    spec = FlowSpec.model_validate(_branch_flow_dict(operator="contains", match_text="hello"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hello there")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    # true branch goes straight to ChatOutput: the human message is the last one
    assert result["messages"][-1].content == "hello there"


@pytest.mark.asyncio
async def test_routes_to_false_branch_then_loops_back():
    # "DONE" never appears (fake model echoes), so every pass takes the false
    # branch until the bound forces default_route -> true_result (exit).
    spec = FlowSpec.model_validate(
        _branch_flow_dict(match_text="DONE", max_iterations=3, default_route="true_result")
    )
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="start")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    # multiple trips through agent-1 before the bound released the exit branch
    assert len(result["messages"]) >= 3


# ---------------------------------------------------------------------------
# R2 — the bound stops the cycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bound_forces_default_route_even_if_condition_never_matches():
    spec = FlowSpec.model_validate(
        _branch_flow_dict(match_text="NEVER_APPEARS", max_iterations=2, default_route="true_result")
    )
    graph = await FlowGraphBuilder().build(spec)

    # Without the bound this recurses until GraphRecursionError. With it, the
    # run completes well inside a generous limit.
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    assert result["messages"][-1].content is not None


@pytest.mark.asyncio
async def test_iteration_count_is_thread_scoped():
    spec = FlowSpec.model_validate(
        _branch_flow_dict(match_text="NEVER", max_iterations=2, default_route="true_result")
    )
    saver = MemorySaver()
    graph = await FlowGraphBuilder(checkpointer=saver).build(spec)

    await graph.ainvoke(
        {"messages": [HumanMessage(content="a")], "scratch": {}},
        config={"configurable": {"thread_id": "thread-a"}, "recursion_limit": 50},
    )
    # thread-b must not inherit thread-a's iteration count and exit early
    result_b = await graph.ainvoke(
        {"messages": [HumanMessage(content="b")], "scratch": {}},
        config={"configurable": {"thread_id": "thread-b"}, "recursion_limit": 50},
    )
    assert len(result_b["messages"]) >= 2


@pytest.mark.asyncio
async def test_iteration_count_resets_each_turn():
    """The bound is per turn, not per thread.

    Sibling of test_iteration_count_is_thread_scoped, which only covers two
    *different* threads and therefore passes even when the counter leaks.
    Here the same thread runs twice: turn two must get a fresh budget.
    """
    spec = FlowSpec.model_validate(
        _branch_flow_dict(match_text="NEVER", max_iterations=2, default_route="true_result")
    )
    saver = MemorySaver()
    graph = await FlowGraphBuilder(checkpointer=saver).build(spec)
    cfg = {"configurable": {"thread_id": "same-thread"}, "recursion_limit": 50}

    first = await graph.ainvoke(
        {"messages": [HumanMessage(content="a")], "scratch": {}}, config=cfg
    )
    after_first = len(first["messages"])

    second = await graph.ainvoke(
        {"messages": [HumanMessage(content="b")], "scratch": {}}, config=cfg
    )

    # Turn two adds its own human message *and* at least one agent message.
    # With a leaked counter the router would short-circuit to default_route
    # and only the human message would be appended.
    assert len(second["messages"]) >= after_first + 2
    # And the counter itself must not have carried over.
    assert second["scratch"]["_condrouter_iterations_cr-1"] <= 2


# ---------------------------------------------------------------------------
# recursion_limit is raised to fit the bound
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_raises_recursion_limit_for_bounded_loops():
    spec = FlowSpec.model_validate(
        _branch_flow_dict(match_text="NEVER", max_iterations=40, default_route="true_result")
    )
    graph = await FlowGraphBuilder().build(spec)

    # 25 + 3*40 = 145
    assert graph.config.get("recursion_limit") == 145


@pytest.mark.asyncio
async def test_true_branch_message_survives_when_condition_matches_immediately():
    spec = FlowSpec.model_validate(
        _branch_flow_dict(operator="equals", match_text="ping", case_sensitive=False)
    )
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="PING")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    assert isinstance(result["messages"][-1], HumanMessage)
    assert result["messages"][-1].content == "PING"


@pytest.mark.asyncio
async def test_strip_match_removes_the_marker_from_the_exit_message():
    spec = FlowSpec.model_validate(
        _branch_flow_dict(operator="contains", match_text="<<DONE>>", strip_match=True)
    )
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="here is the answer\n\n<<DONE>>")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    # matched -> true_result -> ChatOutput, with the marker stripped + tidied
    assert result["messages"][-1].content == "here is the answer"
    assert "<<DONE>>" not in result["messages"][-1].content


@pytest.mark.asyncio
async def test_strip_match_off_by_default_keeps_the_marker():
    spec = FlowSpec.model_validate(
        _branch_flow_dict(operator="contains", match_text="<<DONE>>")  # strip_match defaults False
    )
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="answer <<DONE>>")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    assert result["messages"][-1].content == "answer <<DONE>>"


@pytest.mark.asyncio
async def test_strip_match_is_a_noop_when_marker_absent():
    # false branch: marker never present, strip must not disturb the message
    spec = FlowSpec.model_validate(
        _branch_flow_dict(
            match_text="NEVER", max_iterations=2, default_route="true_result", strip_match=True
        )
    )
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    assert result["messages"][0].content == "go"


@pytest.mark.asyncio
async def test_missing_branch_edge_raises_flow_build_error():
    from core.exceptions import FlowBuildError

    data = _branch_flow_dict()
    # drop the false_result edge
    data["edges"] = [e for e in data["edges"] if e["id"] != "e3"]
    # and the now-orphan agent + its back-edge
    data["nodes"] = [n for n in data["nodes"] if n["id"] != "agent-1"]
    data["edges"] = [e for e in data["edges"] if e["id"] != "e4"]
    spec = FlowSpec.model_validate(data)
    graph = await FlowGraphBuilder().build(spec)

    with pytest.raises(FlowBuildError):
        await graph.ainvoke(
            {"messages": [HumanMessage(content="no false branch here")], "scratch": {}},
            config={"recursion_limit": 50},
        )


# ---------------------------------------------------------------------------
# 1.5 — input_source: compare a named variable, not only the last message
# ---------------------------------------------------------------------------


def _input_source_flow(*, input_source: str, match_text: str) -> dict:
    """ChatInput -> SetVariable(flag) -> If-Else
         -[true]-> ChatOutput
         -[false]-> Agent -> ChatOutput
    The true branch is a pure passthrough; the false branch adds an agent
    message, so message count tells the branches apart."""
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {
                "id": "set-1",
                "type": "SetVariable",
                "values": {"name": "flag", "value": "the marker is DONE"},
            },
            {
                "id": "cr-1",
                "type": "ConditionalRouter",
                "values": {
                    "operator": "contains",
                    "match_text": match_text,
                    "max_iterations": 5,
                    "default_route": "false_result",
                    "input_source": input_source,
                },
            },
            {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "set-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "set-1",
                "sourceHandle": "output",
                "target": "cr-1",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "cr-1",
                "sourceHandle": "true_result",
                "target": "out-1",
                "targetHandle": "message",
            },
            {
                "id": "e4",
                "source": "cr-1",
                "sourceHandle": "false_result",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e5",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


@pytest.mark.asyncio
async def test_conditional_router_compares_a_named_variable():
    """input_source='flag' -> the variable's text ('...DONE') is compared,
    not the latest message ('hello'), so 'contains DONE' is true."""
    spec = FlowSpec.model_validate(_input_source_flow(input_source="flag", match_text="DONE"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hello")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    # true branch is a passthrough: last message is still the human's
    assert result["messages"][-1].content == "hello"


@pytest.mark.asyncio
async def test_blank_input_source_still_compares_the_latest_message():
    """Back-compat: with input_source blank the latest message is compared,
    so 'contains DONE' against 'hello' is false and the agent branch runs."""
    spec = FlowSpec.model_validate(_input_source_flow(input_source="", match_text="DONE"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hello")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    # false branch ran -> an agent message was appended after the human's
    assert len(result["messages"]) >= 2
    assert result["messages"][-1].content != "hello"


# ---------------------------------------------------------------------------
# 1.6 — per-branch message overrides (Langflow's true/false_case_message)
# ---------------------------------------------------------------------------


def _case_message_flow(**cr_values) -> dict:
    """ChatInput -> If-Else -[true]-> ChatOutput
    -[false]-> ChatOutput   (both branches linear)."""
    values = {
        "operator": "contains",
        "match_text": "yes",
        "case_sensitive": True,
        "max_iterations": 5,
        "default_route": "false_result",
    }
    values.update(cr_values)
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "cr-1", "type": "ConditionalRouter", "values": values},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "cr-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "cr-1",
                "sourceHandle": "true_result",
                "target": "out-1",
                "targetHandle": "message",
            },
            {
                "id": "e3",
                "source": "cr-1",
                "sourceHandle": "false_result",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


@pytest.mark.asyncio
async def test_true_case_message_overrides_the_forwarded_text():
    spec = FlowSpec.model_validate(_case_message_flow(true_case_message="APPROVED"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="yes please")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    assert result["messages"][-1].content == "APPROVED"


@pytest.mark.asyncio
async def test_false_case_message_overrides_the_forwarded_text():
    spec = FlowSpec.model_validate(_case_message_flow(false_case_message="REJECTED"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="no thanks")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    assert result["messages"][-1].content == "REJECTED"


@pytest.mark.asyncio
async def test_blank_case_message_forwards_the_input_unchanged():
    spec = FlowSpec.model_validate(_case_message_flow())
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="yes please")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    assert result["messages"][-1].content == "yes please"


# ---------------------------------------------------------------------------
# Langflow parity (Phase 4.5): input_text and the case messages are ports
#
# In Langflow all three are wired inputs — `input_text` is a required
# MessageTextInput, the two case messages are MessageInputs (an inline value
# *and* a port). Ours keep their fields; a wired port simply wins.
# ---------------------------------------------------------------------------

_CR_MATCHED = "_condrouter_matched_cr-1"


def _cr_node(**values) -> FlowNode:
    base = {"operator": "equals", "match_text": "YES", "max_iterations": 10}
    base.update(values)
    return FlowNode(id="cr-1", type="ConditionalRouter", values=base)


@pytest.mark.asyncio
async def test_input_text_port_is_compared_instead_of_the_latest_message():
    fn = _make_condrouter_node(_cr_node(), port_sources={"input_text": "up-1"})
    result = await fn({"messages": [HumanMessage(content="NO")], "scratch": {"up-1": "YES"}}, None)
    assert result["scratch"][_CR_MATCHED] is True


@pytest.mark.asyncio
async def test_without_a_port_the_input_source_field_is_compared():
    fn = _make_condrouter_node(_cr_node(input_source="flag"))
    result = await fn({"messages": [HumanMessage(content="NO")], "scratch": {"flag": "YES"}}, None)
    assert result["scratch"][_CR_MATCHED] is True


@pytest.mark.asyncio
async def test_with_neither_the_latest_message_is_compared():
    fn = _make_condrouter_node(_cr_node())
    result = await fn({"messages": [HumanMessage(content="YES")], "scratch": {}}, None)
    assert result["scratch"][_CR_MATCHED] is True


@pytest.mark.asyncio
async def test_true_case_message_port_wins_over_the_field():
    fn = _make_condrouter_node(
        _cr_node(true_case_message="FROM_FIELD"),
        port_sources={"true_case_message": "up-1"},
    )
    result = await fn(
        {"messages": [HumanMessage(content="YES")], "scratch": {"up-1": "FROM_PORT"}}, None
    )
    assert [m.content for m in result["messages"]] == ["FROM_PORT"]


@pytest.mark.asyncio
async def test_false_case_message_port_wins_over_the_field():
    fn = _make_condrouter_node(
        _cr_node(false_case_message="FROM_FIELD"),
        port_sources={"false_case_message": "up-1"},
    )
    result = await fn(
        {"messages": [HumanMessage(content="NO")], "scratch": {"up-1": "FROM_PORT"}}, None
    )
    assert [m.content for m in result["messages"]] == ["FROM_PORT"]

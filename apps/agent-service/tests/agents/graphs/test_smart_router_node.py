"""Tests for Smart Router — LLM categorisation into one branch per row.

A faithful port of Langflow's Smart Router: one LLM call sorts the message
into a category, then a pure conditional edge routes on the stored choice
(the ConditionalRouter pattern: the node decides, the edge reads).
"""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from agents.graphs.flow_builder import (
    FlowGraphBuilder,
    _make_smart_router_node,
    _smart_router_result_key,
)
from core.exceptions import FlowBuildError
from models.flows import FlowNode, FlowSpec


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _node(**values) -> FlowNode:
    base = {
        "routes": [
            {"route_category": "billing", "route_description": "invoices, payments"},
            {"route_category": "support", "route_description": "technical problems"},
        ]
    }
    base.update(values)
    return FlowNode(id="sr-1", type="SmartRouter", values=base)


async def _run(node: FlowNode, model) -> dict:
    fn = _make_smart_router_node(node, model)
    return await fn(
        {"messages": [HumanMessage(content="my invoice is wrong")], "scratch": {}}, None
    )


@pytest.mark.asyncio
async def test_categorizes_once_and_records_the_matching_category():
    result = await _run(_node(), FakeListChatModel(responses=["billing"]))
    assert result["scratch"][_smart_router_result_key("sr-1")] == "billing"


@pytest.mark.asyncio
async def test_tolerates_the_llm_wrapping_the_category_in_a_sentence():
    result = await _run(_node(), FakeListChatModel(responses=["This looks like billing to me."]))
    assert result["scratch"][_smart_router_result_key("sr-1")] == "billing"


@pytest.mark.asyncio
async def test_unmatched_category_takes_else_when_enabled():
    result = await _run(_node(enable_else_output=True), FakeListChatModel(responses=["weather"]))
    assert result["scratch"][_smart_router_result_key("sr-1")] == "__else__"


@pytest.mark.asyncio
async def test_unmatched_category_without_else_is_an_error():
    with pytest.raises(FlowBuildError):
        await _run(_node(enable_else_output=False), FakeListChatModel(responses=["weather"]))


@pytest.mark.asyncio
async def test_output_value_is_stored_under_the_node_id():
    node = _node(
        routes=[
            {"route_category": "billing", "route_description": "x", "output_value": "TEAM_A"},
        ]
    )
    result = await _run(node, FakeListChatModel(responses=["billing"]))
    assert result["scratch"]["sr-1"] == "TEAM_A"


@pytest.mark.asyncio
async def test_compiles_and_routes_to_the_else_branch_with_the_fake_model():
    """End-to-end: the fake model's fixed reply matches no category, so with
    the Else output enabled the flow leaves via that branch and compiles."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {
                    "id": "sr-1",
                    "type": "SmartRouter",
                    "values": {
                        "enable_else_output": True,
                        "routes": [{"route_category": "billing", "route_description": "invoices"}],
                    },
                },
                {"id": "a", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "sr-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "sr-1",
                    "sourceHandle": "billing",
                    "target": "a",
                    "targetHandle": "input",
                },
                {
                    "id": "e3",
                    "source": "sr-1",
                    "sourceHandle": "else",
                    "target": "out-1",
                    "targetHandle": "message",
                },
                {
                    "id": "e4",
                    "source": "a",
                    "sourceHandle": "output",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )
    graph = await FlowGraphBuilder().build(spec)
    result = await graph.ainvoke({"messages": [HumanMessage(content="hello")], "scratch": {}})
    # else branch -> straight to ChatOutput, no agent message added
    assert [m.content for m in result["messages"]] == ["hello"]


# ---------------------------------------------------------------------------
# Langflow parity (Phase 4.5)
# ---------------------------------------------------------------------------


class _PromptSpy:
    """Captures the prompt so the assertions can be about content, not calls."""

    def __init__(self, reply: str = "billing"):
        self.reply = reply
        self.prompts: list[str] = []
        self.configs: list[dict] = []

    async def ainvoke(self, messages, config=None):
        self.prompts.append(messages[-1].content)
        self.configs.append(config or {})
        return AIMessage(content=self.reply)


@pytest.mark.asyncio
async def test_custom_prompt_is_appended_to_the_base_prompt_not_replacing_it():
    """Langflow calls this field 'Additional Instructions' and appends it:
    ``f"{base}\\n\\nAdditional Instructions:\\n{extra}"``. Replacing the base
    prompt would silently delete the instruction that makes the reply a bare
    category name."""
    spy = _PromptSpy()
    await _run(
        _node(custom_prompt="If unsure pick billing. In: {input_text} / Of: {routes}"),
        spy,
    )
    prompt = spy.prompts[0]
    assert "If unsure pick billing" in prompt  # the instructions survive
    assert "my invoice is wrong" in prompt  # {input_text} resolved
    assert '"billing"' in prompt  # {routes} resolved
    assert "Reply with exactly one category name" in prompt  # base NOT deleted


@pytest.mark.asyncio
async def test_no_custom_prompt_leaves_the_base_prompt_alone():
    spy = _PromptSpy()
    await _run(_node(), spy)
    assert "Additional Instructions" not in spy.prompts[0]


@pytest.mark.asyncio
async def test_the_classifier_call_is_tagged_skip_stream():
    """The category reply ("billing"/"support"/…) is an internal routing
    decision, not answer text. Without the tag it streams to the client as a
    stray assistant bubble beside the branch it only meant to pick."""
    spy = _PromptSpy()
    await _run(_node(), spy)
    assert "skip_stream" in spy.configs[0].get("tags", [])


@pytest.mark.asyncio
async def test_output_value_is_the_message_sent_down_the_branch():
    """Langflow: "Optional message to send when this route is matched."
    Storing it only in scratch made the column look wired up while changing
    nothing the branch could see."""
    node = _node(
        routes=[
            {"route_category": "billing", "route_description": "x", "output_value": "TEAM_A"},
        ]
    )
    result = await _run(node, FakeListChatModel(responses=["billing"]))
    assert [m.content for m in result["messages"]] == ["TEAM_A"]
    assert result["scratch"]["sr-1"] == "TEAM_A"


@pytest.mark.asyncio
async def test_blank_output_value_passes_the_input_through_untouched():
    result = await _run(_node(), FakeListChatModel(responses=["billing"]))
    assert "messages" not in result


@pytest.mark.asyncio
async def test_the_literal_none_counts_as_blank_like_langflow():
    node = _node(
        routes=[
            {"route_category": "billing", "route_description": "x", "output_value": "none"},
        ]
    )
    result = await _run(node, FakeListChatModel(responses=["billing"]))
    assert "messages" not in result


@pytest.mark.asyncio
async def test_override_output_replaces_every_routes_value():
    """Langflow's "Override Output": when filled it replaces both the input and
    each route's own value, for every route."""
    node = _node(
        routes=[{"route_category": "billing", "route_description": "x", "output_value": "IGNORED"}],
        message="OVERRIDDEN",
    )
    result = await _run(node, FakeListChatModel(responses=["billing"]))
    assert [m.content for m in result["messages"]] == ["OVERRIDDEN"]


@pytest.mark.asyncio
async def test_override_output_port_wins_over_the_field():
    """Langflow's field is a MessageInput — inline value *and* port. Ours is
    the same shape, and the wired port always wins."""
    node = _node(message="FROM_FIELD")
    fn = _make_smart_router_node(
        node, FakeListChatModel(responses=["billing"]), {"message": "up-1"}
    )
    result = await fn(
        {
            "messages": [HumanMessage(content="my invoice is wrong")],
            "scratch": {"up-1": "FROM_PORT"},
        },
        None,
    )
    assert [m.content for m in result["messages"]] == ["FROM_PORT"]


@pytest.mark.asyncio
async def test_no_override_leaves_the_route_value_in_charge():
    node = _node(
        routes=[{"route_category": "billing", "route_description": "x", "output_value": "TEAM_A"}],
        message="",
    )
    result = await _run(node, FakeListChatModel(responses=["billing"]))
    assert [m.content for m in result["messages"]] == ["TEAM_A"]

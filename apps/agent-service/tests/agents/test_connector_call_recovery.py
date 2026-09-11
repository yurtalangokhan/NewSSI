import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command


def test_text_call_requests_native_retry_without_executing_json():
    from agents.connector_call_recovery import recover_connector_call

    state = {
        "messages": [
            HumanMessage(content="List roles"),
            AIMessage(
                id="answer",
                content='Let us list. {"name":"connector_read","parameters":{"resource":"roles"}}',
            ),
        ]
    }
    result = recover_connector_call(state, {"connector_read"})
    assert isinstance(result, Command)
    assert result.goto == "agent"
    assert isinstance(result.update["messages"][-1], SystemMessage)


def test_retry_is_bounded_and_new_user_turn_resets_it():
    from agents.connector_call_recovery import recover_connector_call

    text = AIMessage(id="answer", content='{"name":"connector_read","parameters":{}}')
    messages = [HumanMessage(content="List roles"), text]
    first = recover_connector_call({"messages": messages}, {"connector_read"})
    messages += first.update["messages"] + [text.model_copy(update={"id": "again"})]
    result = recover_connector_call({"messages": messages}, {"connector_read"})
    assert not isinstance(result, Command)
    assert not result["messages"][-1].tool_calls
    assert "parameters" not in result["messages"][-1].content
    messages += [HumanMessage(content="Try again"), text]
    assert isinstance(recover_connector_call({"messages": messages}, {"connector_read"}), Command)


@pytest.mark.parametrize(
    "message",
    [
        AIMessage(content="There are 15 roles."),
        AIMessage(content='{"name":"unassigned_tool","parameters":{}}'),
        AIMessage(content='{"name":[],"parameters":{}}'),
        AIMessage(content="", tool_calls=[{"name": "connector_read", "args": {}, "id": "call"}]),
        HumanMessage(content='{"name":"connector_read","parameters":{}}'),
    ],
)
def test_leaves_normal_native_and_untrusted_messages_unchanged(message):
    from agents.connector_call_recovery import recover_connector_call

    assert recover_connector_call({"messages": [message]}, {"connector_read"}) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_real_graph_retries_text_call_then_executes_native_read(monkeypatch, streaming):
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.tools import tool

    from agents.configurable_mcp_agent import ConfigurableMCPAgent

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    reads = []

    @tool
    def connector_read(resource: str) -> str:
        """Read real rows."""
        reads.append(resource)
        return '{"success":true,"rows":[{"name":"agent-maintainer"}]}'

    model = Model(
        responses=[
            AIMessage(content='{"name":"connector_read","parameters":{"resource":"roles"}}'),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "connector_read", "args": {"resource": "roles"}, "id": "read"}
                ],
            ),
            AIMessage(content="agent-maintainer"),
        ]
    )
    monkeypatch.setattr("agents.configurable_mcp_agent.get_model", lambda _: model)
    monkeypatch.setattr("agents.configurable_mcp_agent.get_document_tools", lambda: [])
    graph = ConfigurableMCPAgent()._create_agent_graph(
        system_prompt="Read actual source records.",
        mcp_tool_names=["connector_read"],
        gateway_tools=[connector_read],
    )
    request = {"messages": [HumanMessage(content="List roles")]}
    if streaming:
        states = [state async for state in graph.astream(request, stream_mode="values")]
        result = states[-1]
    else:
        result = await graph.ainvoke(request)
    assert reads == ["roles"]
    assert result["messages"][-1].content == "agent-maintainer"

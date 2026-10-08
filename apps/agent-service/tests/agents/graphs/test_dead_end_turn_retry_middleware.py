"""create_agent's default routing (langchain.agents.create_agent, the
non-deprecated successor to langgraph.prebuilt.create_react_agent) decides
whether a ReAct turn is finished purely by checking `tool_calls` — it never
checks whether `content` is non-empty. A reasoning model can end its turn on
a message with empty content and no tool_calls: confirmed live against a
real checkpoint (qwen3.5:9b via Ollama, done_reason "stop", not a truncated
generation) where the model wrote its actual conclusion into
additional_kwargs.reasoning_content, intended to call a tool next, but never
attached one. Left alone, the graph treats that as a valid final answer and
the client gets a blank message.

DeadEndTurnRetryMiddleware is LangChain's documented pattern for exactly
this ("conditional retry based on response" in AgentMiddleware.wrap_model_call's
own docstring): it wraps the model call, and if the result is this exact
dead end, retries with a corrective nudge before giving up with an honest,
minimal failure message — never one fabricated from the model's private
reasoning.
"""

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from agents.graphs.middleware import DeadEndTurnRetryMiddleware


def _make_request(messages: list) -> ModelRequest:
    return ModelRequest(
        model=object(),
        system_prompt="Be helpful.",
        messages=messages,
        tool_choice=None,
        tools=[],
        response_format=None,
        state={"messages": messages},
        runtime=object(),
    )


def _handler_returning(*responses: ModelResponse):
    calls = {"count": 0, "requests": []}

    async def handler(request: ModelRequest) -> ModelResponse:
        calls["requests"].append(request)
        response = responses[min(calls["count"], len(responses) - 1)]
        calls["count"] += 1
        return response

    return handler, calls


@pytest.mark.asyncio
async def test_passes_through_a_normal_answer_untouched():
    middleware = DeadEndTurnRetryMiddleware()
    fine = ModelResponse(result=[AIMessage(content="Merhaba!")])
    handler, calls = _handler_returning(fine)

    result = await middleware.awrap_model_call(_make_request([]), handler)

    assert result is fine
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_passes_through_a_tool_call_untouched():
    middleware = DeadEndTurnRetryMiddleware()
    tool_call = ModelResponse(
        result=[
            AIMessage(
                content="",
                tool_calls=[{"name": "calculate", "args": {}, "id": "call-1"}],
            )
        ]
    )
    handler, calls = _handler_returning(tool_call)

    result = await middleware.awrap_model_call(_make_request([]), handler)

    assert result is tool_call
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_retries_a_dead_end_message_until_it_gets_real_content():
    middleware = DeadEndTurnRetryMiddleware()
    dead_end = ModelResponse(
        result=[
            AIMessage(
                content="",
                additional_kwargs={"reasoning_content": "Şimdi hesaplayacağım..."},
            )
        ]
    )
    recovered = ModelResponse(result=[AIMessage(content="Apple 310,06 dolardan kapattı.")])
    handler, calls = _handler_returning(dead_end, recovered)

    result = await middleware.awrap_model_call(_make_request([]), handler)

    assert result is recovered
    assert calls["count"] == 2
    retry_request = calls["requests"][1]
    assert isinstance(retry_request.messages[-1], HumanMessage)


@pytest.mark.asyncio
async def test_retries_a_dead_end_message_until_it_gets_a_tool_call():
    middleware = DeadEndTurnRetryMiddleware()
    dead_end = ModelResponse(result=[AIMessage(content="")])
    tool_call = ModelResponse(
        result=[
            AIMessage(
                content="",
                tool_calls=[{"name": "calculate", "args": {}, "id": "call-1"}],
            )
        ]
    )
    handler, _calls = _handler_returning(dead_end, tool_call)

    result = await middleware.awrap_model_call(_make_request([]), handler)

    assert result is tool_call


@pytest.mark.asyncio
async def test_gives_up_after_max_retries_with_an_honest_message_not_a_fabricated_one():
    middleware = DeadEndTurnRetryMiddleware(max_retries=2)
    always_dead_end = ModelResponse(
        result=[
            AIMessage(
                content="",
                additional_kwargs={"reasoning_content": "hala düşünüyorum..."},
            )
        ]
    )
    handler, calls = _handler_returning(always_dead_end)

    result = await middleware.awrap_model_call(_make_request([]), handler)

    assert calls["count"] == 1 + 2
    assert result.result[0].content
    assert "hala düşünüyorum" not in result.result[0].content


@pytest.mark.asyncio
async def test_each_retry_nudges_from_the_original_history_not_a_compounding_one():
    middleware = DeadEndTurnRetryMiddleware(max_retries=2)
    always_dead_end = ModelResponse(result=[AIMessage(content="")])
    handler, calls = _handler_returning(always_dead_end)

    original_messages = [HumanMessage(content="Apple hissesi ne kadar?")]
    await middleware.awrap_model_call(_make_request(original_messages), handler)

    for request in calls["requests"][1:]:
        assert len(request.messages) == len(original_messages) + 1


PROSE_REFERENCE = "Belgeyi oluşturup gösteriyorum:\n\n![alt text](attachment:41173987-2c0f-4279-8d39-b868ba69f8ac)"


def test_an_empty_turn_keeps_the_original_nudge():
    from agents.graphs.middleware import DEAD_END_NUDGE, dead_end_nudge

    assert dead_end_nudge(AIMessage(content="")) == DEAD_END_NUDGE


@pytest.mark.parametrize(
    "message",
    [
        AIMessage(content="Merhaba!"),
        AIMessage(content="Bir `attachment:` şeması var ama bu bir görsel değil."),
        AIMessage(content=PROSE_REFERENCE, tool_calls=[{"name": "create_document", "args": {}, "id": "c1"}]),
        AIMessage(content=[{"type": "text", "text": "Görsel yok."}]),
    ],
)
def test_a_real_answer_or_a_tool_call_is_not_a_dead_end(message):
    from agents.graphs.middleware import dead_end_nudge, is_dead_end

    assert dead_end_nudge(message) is None
    assert not is_dead_end(message)


@pytest.mark.parametrize(
    "content",
    [
        PROSE_REFERENCE,
        "![](attachment:f1)",
        "![m5.jpg]( attachment:f1 )",
        [{"type": "text", "text": PROSE_REFERENCE}],
    ],
)
def test_our_image_syntax_in_a_reply_without_a_tool_call_is_a_dead_end(content):
    from agents.graphs.middleware import ATTACHMENT_IN_PROSE_NUDGE, dead_end_nudge, is_dead_end

    message = AIMessage(content=content)

    assert dead_end_nudge(message) == ATTACHMENT_IN_PROSE_NUDGE
    assert is_dead_end(message)


@pytest.mark.asyncio
async def test_a_reply_that_pastes_an_attachment_into_the_chat_is_nudged_toward_the_document_tool():
    from agents.graphs.middleware import ATTACHMENT_IN_PROSE_NUDGE

    middleware = DeadEndTurnRetryMiddleware()
    pasted = ModelResponse(result=[AIMessage(content=PROSE_REFERENCE)])
    tool_call = ModelResponse(
        result=[AIMessage(content="", tool_calls=[{"name": "create_document", "args": {}, "id": "c1"}])]
    )
    handler, calls = _handler_returning(pasted, tool_call)

    result = await middleware.awrap_model_call(_make_request([]), handler)

    assert result is tool_call
    assert calls["count"] == 2
    nudge = calls["requests"][1].messages[-1]
    assert isinstance(nudge, HumanMessage) and nudge.content == ATTACHMENT_IN_PROSE_NUDGE
    assert "create_document" in nudge.content

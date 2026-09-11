"""Soru sorulurken iş yapılmıyor (§5.4).

Düşürülen çağrılar mesaja hiç yazılmıyor: cevapsız bir `tool_call` bazı
sağlayıcıların reddettiği bir şekil, ve model cevabı aldıktan sonra zaten
yeniden karar verecek.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.clarification.middleware import (
    AskUserAloneMiddleware,
    ask_user_alone_post_model_hook,
    drop_calls_alongside_ask_user,
)


def _call(name, id_):
    return {"name": name, "args": {}, "id": id_}


async def _run(message):
    from langchain.agents.middleware.types import ModelResponse

    async def handler(_request):
        return ModelResponse(result=[message], structured_response=None)

    response = await AskUserAloneMiddleware().awrap_model_call(None, handler)
    return response.result[-1]


@pytest.mark.asyncio
async def test_other_calls_are_dropped_when_a_question_is_asked():
    message = AIMessage(
        content="", tool_calls=[_call("ask_user", "a"), _call("create_document", "b")]
    )
    assert [tc["name"] for tc in (await _run(message)).tool_calls] == ["ask_user"]


@pytest.mark.asyncio
async def test_a_lone_question_is_left_alone():
    message = AIMessage(content="", tool_calls=[_call("ask_user", "a")])
    assert (await _run(message)).tool_calls == message.tool_calls


@pytest.mark.asyncio
async def test_a_turn_without_a_question_is_untouched():
    """Regresyon: aracı çağırmayan turlar hiç etkilenmiyor."""
    message = AIMessage(
        content="", tool_calls=[_call("create_document", "a"), _call("get_time", "b")]
    )
    assert len((await _run(message)).tool_calls) == 2


@pytest.mark.asyncio
async def test_a_plain_answer_is_untouched():
    message = AIMessage(content="Merhaba")
    assert (await _run(message)) is message


# --- post_model_hook: create_react_agent yollarının (alt agent, plan-execute)
# middleware yuvası yok, aynı korumayı buradan alıyorlar (bulgu #1). ---------


@pytest.mark.asyncio
async def test_the_hook_strips_the_other_calls_from_the_last_ai_message():
    message = AIMessage(content="", tool_calls=[_call("ask_user", "a"), _call("send_email", "b")])
    update = await ask_user_alone_post_model_hook(
        {"messages": [HumanMessage(content="rapor"), message]}
    )
    (rewritten,) = update["messages"]
    # Reducer aynı id'den eşleyip üzerine yazsın diye id korunmalı.
    assert rewritten.id == message.id
    assert [tc["name"] for tc in rewritten.tool_calls] == ["ask_user"]


@pytest.mark.asyncio
async def test_the_hook_is_a_no_op_when_the_question_stands_alone():
    message = AIMessage(content="", tool_calls=[_call("ask_user", "a")])
    assert await ask_user_alone_post_model_hook({"messages": [message]}) is None


@pytest.mark.asyncio
async def test_the_hook_is_a_no_op_without_a_question():
    message = AIMessage(content="", tool_calls=[_call("send_email", "a")])
    assert await ask_user_alone_post_model_hook({"messages": [message]}) is None


@pytest.mark.asyncio
async def test_the_hook_accepts_an_attribute_style_state():
    class _State:
        messages = [AIMessage(content="", tool_calls=[_call("ask_user", "a"), _call("x", "b")])]

    update = await ask_user_alone_post_model_hook(_State())
    assert [tc["name"] for tc in update["messages"][0].tool_calls] == ["ask_user"]


def test_the_middleware_and_the_hook_share_one_trimmer():
    """İki giriş noktası da :func:`drop_calls_alongside_ask_user`'a iniyor."""
    message = AIMessage(content="", tool_calls=[_call("ask_user", "a"), _call("x", "b")])
    trimmed = drop_calls_alongside_ask_user(message)
    assert [tc["name"] for tc in trimmed.tool_calls] == ["ask_user"]
    assert drop_calls_alongside_ask_user(AIMessage(content="düz")) is None


@pytest.mark.asyncio
async def test_a_real_react_agent_with_the_hook_never_runs_the_other_tool():
    """Uçtan uca: alt agent/plan-execute grafının kullandığı yol.

    Model ``ask_user`` + ``send_email``'i birlikte çağırıyor; hook sonrası
    yalnızca ``ask_user`` koşup duruyor, ``send_email`` hiç çalışmıyor.
    """
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.tools import tool
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.prebuilt import create_react_agent

    from agents.clarification.tool import ask_user

    class _ToolCallingFake(GenericFakeChatModel):
        # GenericFakeChatModel.bind_tools raises NotImplementedError; the
        # scripted message already carries the tool_calls, so binding is a
        # no-op here.
        def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN202
            return self

    ran: list[str] = []

    @tool
    def send_email(to: str) -> str:
        """Send an email."""
        ran.append(to)
        return "sent"

    scripted = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "ask_user",
                "args": {
                    "questions": [
                        {
                            "question": "Kime?",
                            "header": "Alıcı",
                            "options": [{"label": "Yönetim"}, {"label": "Ekip"}],
                        }
                    ]
                },
                "id": "a",
            },
            {"name": "send_email", "args": {"to": "a@b.com"}, "id": "b"},
        ],
    )
    model = _ToolCallingFake(messages=iter([scripted]))
    agent = create_react_agent(
        model=model,
        tools=[ask_user, send_email],
        post_model_hook=ask_user_alone_post_model_hook,
        checkpointer=MemorySaver(),
    )

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="bir e-posta gönder")]},
        {"configurable": {"thread_id": "t1"}},
    )

    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value["type"] == "user_clarification"
    assert ran == []

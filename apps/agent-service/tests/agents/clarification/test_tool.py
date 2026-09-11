"""`ask_user` uçtan uca: duruyor, devam ediyor, iki şey birden döndürüyor.

Gerçek graf + gerçek checkpointer kullanıyor. Sahte bir interrupt ile test
etmek, tam da doğrulamak istediğimiz şeyi (checkpoint'in duraklamayı ve
artifact'ı taşıması) atlardı.
"""

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from agents.clarification.tool import PAYLOAD_VERSION, ask_user, get_clarification_tools

QUESTIONS = [
    {
        "question": "Raporu kim okuyacak?",
        "header": "Hedef kitle",
        "options": [{"label": "Yönetim"}, {"label": "Teknik ekip"}],
    }
]


def _graph():
    builder = StateGraph(MessagesState)
    builder.add_node("tools", ToolNode([ask_user]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    return builder.compile(checkpointer=MemorySaver())


def _call(questions=QUESTIONS, call_id="c1"):
    return {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "ask_user", "args": {"questions": questions}, "id": call_id}],
            )
        ]
    }


def _config(thread="t1"):
    return {"configurable": {"thread_id": thread}}


@pytest.mark.asyncio
async def test_the_run_stops_and_publishes_the_questions():
    graph, config = _graph(), _config()
    result = await graph.ainvoke(_call(), config)

    (pending,) = result["__interrupt__"]
    assert pending.value["type"] == "user_clarification"
    assert pending.value["v"] == PAYLOAD_VERSION
    assert pending.value["questions"][0]["header"] == "Hedef kitle"
    # Duraklama gerçek: aracın sonucu henüz yok.
    assert not [m for m in (await graph.aget_state(config)).values["messages"] if m.type == "tool"]


@pytest.mark.asyncio
async def test_answering_resumes_the_run_and_reaches_the_model_as_a_tool_result():
    graph, config = _graph(), _config("t2")
    await graph.ainvoke(_call(), config)

    resumed = await graph.ainvoke(
        Command(resume={"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}}), config
    )

    message = resumed["messages"][-1]
    assert message.type == "tool"
    assert "Hedef kitle: Yönetim" in message.content


@pytest.mark.asyncio
async def test_the_structured_answer_survives_the_checkpoint():
    """§3.5: geçmiş tarafı metni değil bunu okuyor."""
    graph, config = _graph(), _config("t3")
    await graph.ainvoke(_call(), config)
    await graph.ainvoke(
        Command(resume={"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}}), config
    )

    stored = (await graph.aget_state(config)).values["messages"][-1]
    assert stored.artifact == {"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}}


@pytest.mark.asyncio
async def test_free_text_also_resumes_and_is_marked_as_not_an_answer():
    graph, config = _graph(), _config("t4")
    await graph.ainvoke(_call(), config)

    resumed = await graph.ainvoke(
        Command(resume={"answered": False, "text": "boşver, hava durumu ne?"}), config
    )

    message = resumed["messages"][-1]
    assert "did not answer" in message.content.lower()
    assert message.artifact == {"answered": False, "text": "boşver, hava durumu ne?"}


@pytest.mark.asyncio
async def test_a_rejected_call_never_reaches_the_user():
    """Doğrulama hatası duraklama açmıyor; model düzeltip tekrar çağırabiliyor."""
    graph, config = _graph(), _config("t5")
    result = await graph.ainvoke(_call(questions=[]), config)

    assert "__interrupt__" not in result
    message = result["messages"][-1]
    assert message.type == "tool"
    assert "at least one" in message.content.lower()


@pytest.mark.asyncio
async def test_resuming_a_second_time_is_a_separate_pause():
    """Aynı thread'de arka arkaya iki soru turu birbirine karışmıyor."""
    graph, config = _graph(), _config("t6")
    await graph.ainvoke(_call(), config)
    await graph.ainvoke(Command(resume={"answered": True, "answers": {}}), config)

    result = await graph.ainvoke(_call(call_id="c2"), config)
    (pending,) = result["__interrupt__"]
    assert pending.value["questions"][0]["header"] == "Hedef kitle"


def test_the_tool_is_exposed_under_the_expected_name():
    from agents.clarification import ASK_USER_TOOL_NAME, is_clarification_tool

    (exposed,) = get_clarification_tools()
    assert exposed.name == ASK_USER_TOOL_NAME
    assert is_clarification_tool(exposed.name)
    assert not is_clarification_tool("create_document")


@pytest.mark.asyncio
async def test_the_rerun_before_the_interrupt_leaves_no_trace():
    """§3.2: resume node'u baştan koşturuyor.

    Araç ``interrupt()`` öncesinde yalnızca payload kuruyor; o iş idempotent.
    Gözlenebilir sonucu bu: çağrı başına tek bir araç sonucu kalıyor.
    """
    graph, config = _graph(), _config("t7")
    await graph.ainvoke(_call(), config)
    await graph.ainvoke(Command(resume={"answered": True, "answers": {}}), config)

    messages = (await graph.aget_state(config)).values["messages"]
    assert [m.tool_call_id for m in messages if m.type == "tool"] == ["c1"]


@pytest.mark.asyncio
async def test_a_question_from_a_sub_agent_names_the_sub_agent():
    """E11: kullanıcı kimin sorduğunu görmeden karar veremez."""
    inner = StateGraph(MessagesState)
    inner.add_node("tools", ToolNode([ask_user]))
    inner.add_edge(START, "tools")
    inner.add_edge("tools", END)

    outer = StateGraph(MessagesState)
    outer.add_node("Fatura_Uzmani", inner.compile())
    outer.add_edge(START, "Fatura_Uzmani")
    outer.add_edge("Fatura_Uzmani", END)
    graph = outer.compile(checkpointer=MemorySaver())

    result = await graph.ainvoke(_call(), _config("t8"))

    (pending,) = result["__interrupt__"]
    assert pending.value["agent_path"] == ["Fatura Uzmani"]

"""Default `chatbot` agent can also ask the user what they meant.

`ask_user` rides the SAME bound-tool loop as the document tools (the user's
call: "chatbot document tool'ları nasıl kullanıyorsa bunu da öyle kullansın").
The extra care versus a `create_react_agent` graph:

- The loop is hand-rolled, so `interrupt()` must bubble out of `_run_tool_call`
  instead of being caught by its broad `except Exception`.
- A resumed node re-runs from the top, and everything it wrote before the
  `interrupt()` is discarded. So the pause lives in its own `clarify` node:
  the model node commits its reasoning and tool call first, and only then does
  the run park. Without that split a reloaded chat lost the whole timeline.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agents import chatbot as chatbot_module

_ASK_CALL = {
    "name": "ask_user",
    "args": {
        "questions": [
            {
                "question": "Raporu kim okuyacak?",
                "header": "Hedef kitle",
                "options": [{"label": "Yönetim"}, {"label": "Teknik ekip"}],
            }
        ]
    },
    "id": "ask-1",
}

_DOC_CALL = {
    "name": "create_document",
    "args": {"filename": "rapor", "format": "txt", "content": "gövde"},
    "id": "doc-1",
}


@pytest.fixture(autouse=True)
def _clear_file_store():
    from service.FileService import _STORE

    _STORE.clear()
    yield
    _STORE.clear()


@pytest.fixture(autouse=True)
def _stub_persistence(monkeypatch):
    monkeypatch.setattr("service.MinioService.upload_file", lambda **kwargs: "object-key")

    class _NoopRepo:
        async def create(self, **kwargs):
            return {}

    monkeypatch.setattr(
        "core.db.repositories.document_repo.DocumentRepository", lambda: _NoopRepo()
    )


@pytest.fixture(autouse=True)
def _checkpointer_present(monkeypatch):
    """`ask_user` is only offered when a resume is possible (design 5.3, E13).

    In prod the chatbot graph is handed the global checkpointer at request
    time; here we just say one exists.
    """
    monkeypatch.setattr(chatbot_module, "get_checkpointer", lambda: object(), raising=False)


class _ScriptedModel:
    """Emits a fixed sequence of AI messages, one per `ainvoke`."""

    def __init__(self, *responses: AIMessage) -> None:
        self._responses = list(responses)
        self.bound = False
        self.bound_tool_names: list = []
        self.calls = 0
        self.seen_messages: list = []

    def bind_tools(self, tools):
        self.bound = True
        self.bound_tool_names = [getattr(t, "name", None) for t in tools]
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        self.seen_messages.append(list(messages))
        return self._responses[min(self.calls - 1, len(self._responses) - 1)]


class _AsksUntilAnswered:
    """Repeats one `ask_user` call until it sees the answer, then replies.

    Models a temperature-0 model: a resumed node re-runs and the model
    reproduces the same tool call, so `interrupt()` lines up with its resume
    value on the second pass.
    """

    def __init__(self, final_text: str) -> None:
        self._final = final_text
        self.bound_tool_names: list = []

    def bind_tools(self, tools):
        self.bound_tool_names = [getattr(t, "name", None) for t in tools]
        return self

    async def ainvoke(self, messages):
        answered = any(isinstance(m, ToolMessage) and m.name == "ask_user" for m in messages)
        if answered:
            return AIMessage(content=self._final)
        return AIMessage(content="", tool_calls=[_ASK_CALL])


def _graph():
    return chatbot_module.workflow.compile(checkpointer=MemorySaver())


def _cfg(thread="t1"):
    return {"configurable": {"thread_id": thread}}


@pytest.mark.asyncio
async def test_ask_user_is_bound_alongside_the_document_tools(monkeypatch):
    model = _ScriptedModel(AIMessage(content="merhaba"))
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    await chatbot_module.call_model(
        {"messages": [HumanMessage(content="selam")]}, {"configurable": {}}, store=None
    )

    assert "ask_user" in model.bound_tool_names
    assert "create_document" in model.bound_tool_names


@pytest.mark.asyncio
async def test_without_a_checkpointer_ask_user_is_not_offered(monkeypatch):
    monkeypatch.setattr(chatbot_module, "get_checkpointer", lambda: None, raising=False)
    model = _ScriptedModel(AIMessage(content="merhaba"))
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    await chatbot_module.call_model(
        {"messages": [HumanMessage(content="selam")]}, {"configurable": {}}, store=None
    )

    assert "ask_user" not in (model.bound_tool_names or [])


@pytest.mark.asyncio
async def test_the_prompt_is_appended_when_ask_user_is_offered(monkeypatch):
    from agents.clarification.prompt import ASK_USER_PROMPT

    model = _ScriptedModel(AIMessage(content="merhaba"))
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    await chatbot_module.call_model(
        {"messages": [HumanMessage(content="selam")]}, {"configurable": {}}, store=None
    )

    assert any(ASK_USER_PROMPT in getattr(m, "content", "") for m in model.seen_messages[0])


@pytest.mark.asyncio
async def test_ask_user_as_the_first_action_pauses_the_run(monkeypatch):
    model = _ScriptedModel(
        AIMessage(content="", tool_calls=[_ASK_CALL]),
        AIMessage(content="Yönetim için hazırlıyorum."),
    )
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    result = await _graph().ainvoke({"messages": [HumanMessage(content="rapor hazırla")]}, _cfg())

    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value["type"] == "user_clarification"
    # Nothing answered yet.
    assert not [m for m in result["messages"] if isinstance(m, ToolMessage)]


@pytest.mark.asyncio
async def test_the_paused_turn_keeps_its_reasoning_in_the_checkpoint(monkeypatch):
    """A reload must still find what the model thought before it asked.

    Everything a node writes before `interrupt()` is DISCARDED — measured on a
    real paused thread, whose newest checkpoint held only the user's message.
    The reasoning, the recalled memories and the tool call were all gone, so a
    reloaded chat showed the question card floating on its own while the live
    stream had shown a full timeline.

    The pause therefore has to happen in a superstep of its own, which is what
    a react graph gets for free from model -> tools.
    """
    model = _ScriptedModel(
        AIMessage(
            content="",
            additional_kwargs={"reasoning_content": "Hangi veriyi istiyor?"},
            tool_calls=[_ASK_CALL],
        ),
        AIMessage(content="tamam"),
    )
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )
    graph = _graph()

    await graph.ainvoke({"messages": [HumanMessage(content="rapor hazırla")]}, _cfg("t-reload"))

    committed = (await graph.aget_state(_cfg("t-reload"))).values["messages"]
    asked = next(
        (
            m
            for m in committed
            if isinstance(m, AIMessage)
            and any(c.get("name") == "ask_user" for c in (m.tool_calls or []))
        ),
        None,
    )
    assert asked is not None, "the asking AIMessage never reached the checkpoint"
    assert asked.additional_kwargs.get("reasoning_content") == "Hangi veriyi istiyor?"
    # Still genuinely paused: the answer has not been produced.
    assert not [m for m in committed if isinstance(m, ToolMessage)]


@pytest.mark.asyncio
async def test_answering_resumes_the_loop_and_the_model_finishes(monkeypatch):
    model = _AsksUntilAnswered("Yönetim için kısa tutuyorum.")
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )
    graph = _graph()
    await graph.ainvoke({"messages": [HumanMessage(content="rapor hazırla")]}, _cfg("t2"))

    resumed = await graph.ainvoke(
        Command(resume={"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}}),
        _cfg("t2"),
    )

    tool_msg = next(m for m in resumed["messages"] if isinstance(m, ToolMessage))
    assert "Hedef kitle: Yönetim" in tool_msg.content
    assert tool_msg.artifact == {"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}}
    assert resumed["messages"][-1].content == "Yönetim için kısa tutuyorum."


@pytest.mark.asyncio
async def test_ask_user_called_with_other_tools_runs_alone(monkeypatch):
    model = _ScriptedModel(
        AIMessage(content="", tool_calls=[_ASK_CALL, _DOC_CALL]),
        AIMessage(content="tamam"),
    )
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    result = await _graph().ainvoke(
        {"messages": [HumanMessage(content="rapor hazırla")]}, _cfg("t3")
    )

    assert "__interrupt__" in result
    # The document was never created — no generated-file marker anywhere.
    assert not any("__generated_file__" in getattr(m, "content", "") for m in result["messages"])


@pytest.mark.asyncio
async def test_a_late_ask_user_is_honoured_without_redoing_the_work(monkeypatch):
    """Asking after some work is done used to be refused, and no longer is.

    The refusal existed only because a resumed node re-ran its own writes: a
    document written before the pause would have been created twice. Now the
    model node is committed before the run parks, so the question is honoured
    and the document is made exactly once.
    """
    doc_calls = 0
    real_run_tool_call = chatbot_module._run_tool_call

    async def _counting_run_tool_call(tool, call, config):
        nonlocal doc_calls
        if call.get("name") == "create_document":
            doc_calls += 1
            return "written"
        return await real_run_tool_call(tool, call, config)

    monkeypatch.setattr(chatbot_module, "_run_tool_call", _counting_run_tool_call)

    class _WritesThenAsks:
        """Writes a document, then asks — and after the answer, replies."""

        def __init__(self) -> None:
            self.bound_tool_names: list = []

        def bind_tools(self, tools):
            self.bound_tool_names = [getattr(t, "name", None) for t in tools]
            return self

        async def ainvoke(self, messages):
            answered = any(isinstance(m, ToolMessage) and m.name == "ask_user" for m in messages)
            if answered:
                return AIMessage(content="Yönetim için hazırladım.")
            wrote = any(
                isinstance(m, ToolMessage) and m.name == "create_document" for m in messages
            )
            if wrote:
                return AIMessage(content="", tool_calls=[_ASK_CALL])
            return AIMessage(content="", tool_calls=[_DOC_CALL])

    monkeypatch.setattr(
        chatbot_module,
        "get_model_from_config",
        lambda configurable, default_model: _WritesThenAsks(),
    )
    graph = _graph()

    paused = await graph.ainvoke(
        {"messages": [HumanMessage(content="rapor hazırla")]}, _cfg("t-late")
    )
    assert paused["__interrupt__"][0].value["type"] == "user_clarification"

    resumed = await graph.ainvoke(
        Command(resume={"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}}),
        _cfg("t-late"),
    )

    assert resumed["messages"][-1].content == "Yönetim için hazırladım."
    assert doc_calls == 1, "the resume re-ran the document write"


@pytest.mark.asyncio
async def test_run_tool_call_never_swallows_a_bubble_up(monkeypatch):
    from langgraph.errors import GraphInterrupt

    from agents.chatbot import _run_tool_call

    class _Boom:
        name = "ask_user"

        async def ainvoke(self, args, config):
            raise GraphInterrupt(("stop",))

    with pytest.raises(GraphInterrupt):
        await _run_tool_call(_Boom(), {"name": "ask_user", "args": {}, "id": "x"}, {})

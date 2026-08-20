"""Tests for the default chatbot's document-tool loop with graceful fallback.

The plain chatbot graph (persona_id=0) is a single model.ainvoke() call with no
tool-calling loop. Document tools must still be available there, but a model
that doesn't support tool binding must keep working exactly as before.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents import chatbot as chatbot_module
from agents import document_tools


class _NoToolSupportModel:
    """Mimics a model whose bind_tools raises, like some local Ollama models."""

    def __init__(self) -> None:
        self.ainvoke_calls: list[list] = []

    def bind_tools(self, tools):
        raise NotImplementedError("this model does not support tools")

    async def ainvoke(self, messages):
        self.ainvoke_calls.append(list(messages))
        return AIMessage(content="ok")


class _ToolCallingModel:
    """Mimics a model that calls create_document once, then answers."""

    def __init__(self, tool_call_id: str = "call-1") -> None:
        self.tool_call_id = tool_call_id
        self.bound = False
        self.ainvoke_calls: list[list] = []

    def bind_tools(self, tools):
        self.bound = True
        return self

    async def ainvoke(self, messages):
        self.ainvoke_calls.append(list(messages))
        if not any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_document",
                        "args": {
                            "filename": "rapor",
                            "format": "txt",
                            "content": "gövde",
                        },
                        "id": self.tool_call_id,
                    }
                ],
            )
        return AIMessage(content="İşte dosyanız.")


@pytest.fixture(autouse=True)
def _clear_file_store():
    from service.FileService import _STORE

    _STORE.clear()
    yield
    _STORE.clear()


@pytest.fixture(autouse=True)
def _stub_persistence(monkeypatch):
    """Document tools must not touch real MinIO/DB during these tests."""
    monkeypatch.setattr("service.MinioService.upload_file", lambda **kwargs: "object-key")

    class _NoopRepo:
        async def create(self, **kwargs):
            return {}

    monkeypatch.setattr(
        "core.db.repositories.document_repo.DocumentRepository", lambda: _NoopRepo()
    )


@pytest.mark.asyncio
async def test_falls_back_to_plain_ainvoke_when_model_lacks_tool_support(monkeypatch):
    model = _NoToolSupportModel()
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    result = await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Merhaba")]},
        {"configurable": {}},
        store=None,
    )

    assert len(model.ainvoke_calls) == 1
    assert [type(m).__name__ for m in result["messages"]] == ["AIMessage"]
    assert result["messages"][0].content == "ok"


@pytest.mark.asyncio
async def test_executes_document_tool_and_returns_all_new_messages(monkeypatch):
    model = _ToolCallingModel()
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    result = await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Bana bir rapor hazırla")]},
        {"configurable": {"thread_id": "thread-1", "user_id": "user-1"}},
        store=None,
    )

    assert model.bound is True
    message_types = [type(m).__name__ for m in result["messages"]]
    assert message_types == ["AIMessage", "ToolMessage", "AIMessage"]

    tool_message = result["messages"][1]
    assert "__generated_file__" in tool_message.content

    final_message = result["messages"][-1]
    assert final_message.content == "İşte dosyanız."


@pytest.mark.asyncio
async def test_document_tool_prompt_is_injected_only_when_tools_enabled(monkeypatch):
    model = _ToolCallingModel()
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Merhaba")]},
        {"configurable": {}},
        store=None,
    )

    first_call_messages = model.ainvoke_calls[0]
    assert any(
        document_tools.DOCUMENT_TOOL_PROMPT in getattr(m, "content", "")
        for m in first_call_messages
    )


@pytest.mark.asyncio
async def test_skips_tool_loop_entirely_when_document_tools_disabled(monkeypatch):
    monkeypatch.setattr(document_tools.settings, "DOCUMENT_TOOLS_ENABLED", False)
    model = _ToolCallingModel()
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    result = await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Merhaba")]},
        {"configurable": {}},
        store=None,
    )

    assert model.bound is False
    assert len(model.ainvoke_calls) == 1
    assert len(result["messages"]) == 1


class _InvalidThenValidModel:
    """First call omits the required `content`, then corrects itself."""

    def __init__(self) -> None:
        self.bound = False
        self.tool_results: list[str] = []

    def bind_tools(self, tools):
        self.bound = True
        return self

    async def ainvoke(self, messages):
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        self.tool_results = [m.content for m in tool_messages]

        if not tool_messages:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_document",
                        "args": {"filename": "rapor", "format": "txt"},
                        "id": "call-1",
                    }
                ],
            )
        if len(tool_messages) == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_document",
                        "args": {
                            "filename": "rapor",
                            "format": "txt",
                            "content": "gövde",
                        },
                        "id": "call-2",
                    }
                ],
            )
        return AIMessage(content="İşte dosyanız.")


class _AlwaysCallsToolsModel:
    """A model that never stops calling tools, exhausting the loop budget."""

    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if any(isinstance(m, ToolMessage) for m in messages) and self.calls > 4:
            return AIMessage(content="son cevap")
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "create_document",
                    "args": {"filename": "rapor", "format": "txt"},
                    "id": f"call-{self.calls}",
                }
            ],
        )


@pytest.mark.asyncio
async def test_invalid_tool_arguments_are_reported_back_instead_of_crashing(monkeypatch):
    """A rejected tool call must not tear down the run — the model retries."""
    model = _InvalidThenValidModel()
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    result = await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Bana bir rapor hazırla")]},
        {"configurable": {"thread_id": "thread-1", "user_id": "user-1"}},
        store=None,
    )

    message_types = [type(m).__name__ for m in result["messages"]]
    assert message_types == [
        "AIMessage",
        "ToolMessage",
        "AIMessage",
        "ToolMessage",
        "AIMessage",
    ]

    # The first result names the missing argument so the retry can fix it.
    first_error = result["messages"][1].content
    assert "content" in first_error
    assert first_error.startswith("Error:")

    # The retry produced a real file and the model got to answer.
    assert "__generated_file__" in result["messages"][3].content
    assert result["messages"][-1].content == "İşte dosyanız."


@pytest.mark.asyncio
async def test_unexpected_tool_failure_is_reported_back_to_the_model(monkeypatch):
    model = _ToolCallingModel()
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("disk dolu")

    # Raised outside the tool's own error handling, so it escapes the call.
    monkeypatch.setattr(document_tools.docgen, "sanitize_filename", _boom)

    result = await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Bana bir rapor hazırla")]},
        {"configurable": {}},
        store=None,
    )

    tool_message = result["messages"][1]
    assert tool_message.content == "Error: create_document failed: disk dolu"
    assert result["messages"][-1].content == "İşte dosyanız."


@pytest.mark.asyncio
async def test_exhausted_tool_loop_still_ends_with_a_text_answer(monkeypatch):
    """Otherwise the reply would be a raw tool result with no assistant text."""
    model = _AlwaysCallsToolsModel()
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    result = await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Bana bir rapor hazırla")]},
        {"configurable": {}},
        store=None,
    )

    final_message = result["messages"][-1]
    assert type(final_message).__name__ == "AIMessage"
    assert final_message.content == "son cevap"


class _WrappedContentModel:
    """Puts the body as <content>…</content> inside an unrelated argument."""

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if not any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_document",
                        "args": {
                            "filename": "rapor",
                            "format": "txt",
                            "title": "<content># Başlık\n\nGövde</content>",
                        },
                        "id": "call-1",
                    }
                ],
            )
        return AIMessage(content="İşte dosyanız.")


@pytest.mark.asyncio
async def test_body_passed_under_the_wrong_key_is_recovered(monkeypatch):
    """Rejecting this would cost the user a full regeneration of the document."""
    model = _WrappedContentModel()
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    result = await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Bana bir rapor hazırla")]},
        {"configurable": {"thread_id": "thread-1", "user_id": "user-1"}},
        store=None,
    )

    tool_message = result["messages"][1]
    assert "__generated_file__" in tool_message.content
    assert result["messages"][-1].content == "İşte dosyanız."


class _NoToolsSupportModel:
    """Simulates a model like qwen2.5vl:3b that accepts bind_tools in memory but rejects tools at runtime."""

    def __init__(self) -> None:
        self.plain_calls: list = []

    def bind_tools(self, tools):
        bound = MagicMock()
        bound.ainvoke = AsyncMock(
            side_effect=Exception(
                "registry.ollama.ai/library/qwen2.5vl:3b does not support tools (status code: 400)"
            )
        )
        return bound

    async def ainvoke(self, messages):
        self.plain_calls.append(messages)
        return AIMessage(content="Merhaba, size nasıl yardımcı olabilirim?")


@pytest.mark.asyncio
async def test_model_without_runtime_tool_support_falls_back_to_plain_chat(monkeypatch):
    """When a model like qwen2.5vl:3b raises does not support tools, fall back to plain chat gracefully."""
    model = _NoToolsSupportModel()
    monkeypatch.setattr(
        chatbot_module, "get_model_from_config", lambda configurable, default_model: model
    )

    result = await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Fotoğrafı analiz et")]},
        {"configurable": {"thread_id": "thread-1", "user_id": "user-1"}},
        store=None,
    )

    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "Merhaba, size nasıl yardımcı olabilirim?"
    assert len(model.plain_calls) == 1

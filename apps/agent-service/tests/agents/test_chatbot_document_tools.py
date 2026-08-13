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

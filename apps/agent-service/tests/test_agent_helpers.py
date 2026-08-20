"""Tests for agent helper configuration resolution."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from schema import UserInput
from service.AgentHelpers import _handle_input, get_graph_and_config


class DummyAgent:
    async def aget_state(self, config=None, **kwargs):
        return SimpleNamespace(tasks=[], values={})


@pytest.mark.asyncio
async def test_handle_input_keeps_runtime_long_term_memory_for_builtin_persona():
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
        agent_config={"long_term_memory": True},
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("service.PersonaRepository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("service.PersonaRepository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    assert kwargs["config"]["configurable"]["long_term_memory"] is True


@pytest.mark.asyncio
async def test_handle_input_raises_recursion_limit_above_langgraph_default():
    """LangGraph's own default (25 graph steps) is too low for a deep-research
    turn doing several rounds of parallel search/fetch tool calls — it must
    be overridden, not left at the default, or the turn dies mid-stream with
    GraphRecursionError."""
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
        agent_config={},
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("service.PersonaRepository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("service.PersonaRepository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    assert kwargs["config"]["recursion_limit"] > 25


@pytest.mark.asyncio
async def test_handle_input_forwards_mail_attachments_to_runtime_config():
    user_input = UserInput(
        message="mail this file",
        thread_id="thread-mail-attachments",
        agent_id="configurable-mcp-agent",
        mail_attachments=[
            {
                "id": "file-1",
                "filename": "report.txt",
                "mime_type": "text/plain",
                "content_base64": "UmVwb3J0",
            }
        ],
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("service.PersonaRepository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("service.PersonaRepository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    assert kwargs["config"]["configurable"]["mail_attachments"] == [
        {
            "id": "file-1",
            "filename": "report.txt",
            "mime_type": "text/plain",
            "content_base64": "UmVwb3J0",
        }
    ]


@pytest.mark.asyncio
async def test_handle_input_stamps_persona_id_and_model_on_the_human_message():
    """Retry needs to know which agent/model actually produced a turn, but
    that was only ever tracked at the thread level (last-write-wins). Stamp
    it onto the outgoing HumanMessage's additional_kwargs — mirroring how
    files_metadata is already persisted per message — so chat history can
    report the correct value per turn regardless of what runs later."""
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
        model="gpt-4o",
        agent_config={"_persona_id": 7},
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("service.PersonaRepository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("service.PersonaRepository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    human_message = kwargs["input"]["messages"][0]
    assert human_message.additional_kwargs["persona_id"] == 7
    assert human_message.additional_kwargs["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_handle_input_defaults_persona_id_to_zero_for_default_agent():
    """No agent_config/_persona_id at all means the default (model-chat)
    persona was used — this must still be stamped as 0, not omitted, so chat
    history can distinguish "default persona" from "unknown/legacy"."""
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="chatbot",
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("service.PersonaRepository.PersonaDB.get", return_value=None),
        patch("service.PersonaRepository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    human_message = kwargs["input"]["messages"][0]
    assert human_message.additional_kwargs["persona_id"] == 0


@pytest.mark.asyncio
async def test_handle_input_stamps_is_regenerate_on_the_human_message():
    """A retry resends via the same send-chat-message path, producing a
    duplicate HumanMessage. It must be marked is_regenerate=True so history
    reconstruction (get_chat_session) can treat the response that follows
    as a sibling of the original instead of a new conversation turn."""
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
        is_regenerate=True,
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("service.PersonaRepository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("service.PersonaRepository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    human_message = kwargs["input"]["messages"][0]
    assert human_message.additional_kwargs["is_regenerate"] is True


@pytest.mark.asyncio
async def test_handle_input_omits_is_regenerate_for_a_normal_send():
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("service.PersonaRepository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("service.PersonaRepository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    human_message = kwargs["input"]["messages"][0]
    assert "is_regenerate" not in human_message.additional_kwargs


@pytest.mark.asyncio
async def test_get_graph_and_config_preserves_dynamic_persona_owner_id(monkeypatch):
    async def fake_get(persona_id: int):
        assert persona_id == 23
        return {
            "is_builtin": False,
            "user_id": "owner-user",
            "base_agent": "dynamic-agent",
            "mcp_tools": ["send_email"],
            "mcp_tool_configs": {"send_email": {"mail_config_id": "mail-config-1"}},
            "rag_config": {},
        }

    class FakeDefinition:
        id = "definition-1"

        def to_config(self):
            return {
                "mcp_tools": ["send_email"],
                "mcp_tool_configs": {"send_email": {"mail_config_id": "mail-config-1"}},
            }

    class FakeDefinitionRepository:
        async def get_by_persona_id(self, persona_id: int):
            assert persona_id == 23
            return FakeDefinition()

    monkeypatch.setattr("service.PersonaRepository.PersonaDB.get", fake_get)
    monkeypatch.setattr(
        "agents.storage.repository.AgentDefinitionRepository",
        FakeDefinitionRepository,
    )
    monkeypatch.setattr(
        "service.StoreService.get_assistant_from_store", AsyncMock(return_value=None)
    )

    graph_id, config = await get_graph_and_config(23)

    assert graph_id == "definition-1"
    assert config["owner_user_id"] == "owner-user"


@pytest.mark.asyncio
async def test_handle_input_enables_long_term_memory_without_user_toggle():
    user_input = UserInput(
        message="hello",
        thread_id="thread-2",
        agent_id="configurable-mcp-agent",
        agent_config={"long_term_memory": True},
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("service.PersonaRepository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("service.PersonaRepository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    assert kwargs["config"]["configurable"]["long_term_memory"] is True

"""Tests for agent helper configuration resolution."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from schema import UserInput
from service.AgentHelpers import _handle_input


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

    with patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}), patch(
        "service.StoreService.add_thread", new=AsyncMock()
    ), patch("service.UserServiceClient.get_user_settings", return_value={"long_term_memory_enabled": False, "extract_memory": True}), patch(
        "service.PersonaRepository.PersonaDB.get", return_value={"is_builtin": True}
    ), patch("service.PersonaRepository.PersonaDB.get_by_builtin_key", return_value=None):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    assert kwargs["config"]["configurable"]["long_term_memory"] is True


@pytest.mark.asyncio
async def test_handle_input_enables_long_term_memory_without_user_toggle():
    user_input = UserInput(
        message="hello",
        thread_id="thread-2",
        agent_id="configurable-mcp-agent",
        agent_config={"long_term_memory": True},
    )

    with patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}), patch(
        "service.StoreService.add_thread", new=AsyncMock()
    ), patch("service.UserServiceClient.get_user_settings", return_value={"long_term_memory_enabled": False, "extract_memory": True}), patch(
        "service.PersonaRepository.PersonaDB.get", return_value={"is_builtin": True}
    ), patch("service.PersonaRepository.PersonaDB.get_by_builtin_key", return_value=None):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    assert kwargs["config"]["configurable"]["long_term_memory"] is True

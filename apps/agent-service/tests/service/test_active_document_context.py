"""Task 16a: the document open in the client's side panel must reach agents
as run context (`configurable["active_document"]`) without ever being
injected into the conversation history — a note stitched into the
HumanMessage would pollute history and, as a mid-conversation "system-ish"
addition, some providers reject it outright.
"""

from __future__ import annotations
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from schemas.chat import DocumentContext, UserInput
from service.orchestration.agent_runner_coordinator import _active_document, _handle_input


class DummyAgent:
    async def aget_state(self, config=None, **kwargs):
        from types import SimpleNamespace

        return SimpleNamespace(tasks=[], values={})


def test_active_document_is_none_without_document_context():
    user_input = UserInput(message="hello", thread_id="thread-1")

    assert _active_document(user_input) is None


def test_active_document_projects_document_id_and_revision_no():
    document_id = uuid4()
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        document_context=DocumentContext(document_id=document_id, revision_no=2),
    )

    assert _active_document(user_input) == {
        "document_id": str(document_id),
        "revision_no": 2,
    }


def test_active_document_allows_revision_no_to_be_absent():
    document_id = uuid4()
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        document_context=DocumentContext(document_id=document_id),
    )

    assert _active_document(user_input) == {
        "document_id": str(document_id),
        "revision_no": None,
    }


@pytest.mark.asyncio
async def test_handle_input_exposes_active_document_without_touching_the_message():
    """The coordinator must place the open document at
    configurable["active_document"] while leaving the HumanMessage content
    exactly as the user typed it -- no note, no wrapper, no prefix."""
    document_id = uuid4()
    user_input = UserInput(
        message="x",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
        document_context=DocumentContext(document_id=document_id, revision_no=2),
    )

    with (
        patch("service.runtime.store_service.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.runtime.store_service.add_thread", new=AsyncMock()),
        patch(
            "integrations.user_service_client.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
            return_value={"is_builtin": True},
        ),
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.get_by_builtin_key",
            return_value=None,
        ),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), authenticated_user_id="user-1")

    assert kwargs["config"]["configurable"]["active_document"] == {
        "document_id": str(document_id),
        "revision_no": 2,
    }
    human_message = kwargs["input"]["messages"][0]
    assert human_message.content == "x"


@pytest.mark.asyncio
async def test_handle_input_omits_active_document_when_not_sent():
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
    )

    with (
        patch("service.runtime.store_service.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.runtime.store_service.add_thread", new=AsyncMock()),
        patch(
            "integrations.user_service_client.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
            return_value={"is_builtin": True},
        ),
        patch(
            "infrastructure.db.repositories.persona_repo.PersonaRepository.get_by_builtin_key",
            return_value=None,
        ),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), authenticated_user_id="user-1")

    assert "active_document" not in kwargs["config"]["configurable"]

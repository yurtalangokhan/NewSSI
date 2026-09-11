"""Tests for agent helper configuration resolution."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.types import Command

from schema import UserInput
from service.AgentHelpers import _handle_input, get_graph_and_config


class DummyAgent:
    async def aget_state(self, config=None, **kwargs):
        return SimpleNamespace(tasks=[], values={})


@pytest.mark.asyncio
async def test_handle_input_disables_memory_when_user_recall_setting_is_off():
    """The user's "Depolanan Belleğe Başvur" setting is the master switch: when
    it is off, a default assistant does not recall or save, even if the request
    carries long_term_memory=True."""
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
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    configurable = kwargs["config"]["configurable"]
    assert configurable["long_term_memory"] is False
    assert configurable["extract_memory"] is False


@pytest.mark.asyncio
async def test_handle_input_enables_memory_for_default_assistant_when_user_opts_in():
    """With the user setting on, the default assistant / plain chatbot recalls
    and (when "Belleği Güncelle" is on) saves — no agent toggle required."""
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="chatbot",
        agent_config={},
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": True, "extract_memory": True},
        ),
        patch("repository.persona_repository.PersonaDB.get", return_value=None),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    configurable = kwargs["config"]["configurable"]
    assert configurable["long_term_memory"] is True
    assert configurable["extract_memory"] is True


@pytest.mark.asyncio
async def test_handle_input_recall_on_but_update_off_disables_save_only():
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="chatbot",
        agent_config={},
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": True, "extract_memory": False},
        ),
        patch("repository.persona_repository.PersonaDB.get", return_value=None),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    configurable = kwargs["config"]["configurable"]
    assert configurable["long_term_memory"] is True
    assert configurable["extract_memory"] is False


@pytest.mark.asyncio
async def test_handle_input_custom_agent_with_ltm_off_ignores_user_recall_setting():
    """A custom persona that did not opt into long-term memory stays silent even
    when the user's recall setting is on."""
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="42",
        agent_config={"_persona_id": 42},
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": True, "extract_memory": True},
        ),
        patch(
            "repository.persona_repository.PersonaDB.get",
            return_value={"is_builtin": False, "long_term_memory": False},
        ),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    configurable = kwargs["config"]["configurable"]
    assert configurable["long_term_memory"] is False
    assert configurable["extract_memory"] is False


@pytest.mark.asyncio
async def test_handle_input_custom_agent_with_ltm_on_requires_user_recall_setting():
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="42",
        agent_config={"_persona_id": 42},
    )

    for recall, expected in ((True, True), (False, False)):
        with (
            patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
            patch("service.StoreService.add_thread", new=AsyncMock()),
            patch(
                "service.UserServiceClient.get_user_settings",
                return_value={"long_term_memory_enabled": recall, "extract_memory": True},
            ),
            patch(
                "repository.persona_repository.PersonaDB.get",
                return_value={"is_builtin": False, "long_term_memory": True},
            ),
            patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
        ):
            kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

        assert kwargs["config"]["configurable"]["long_term_memory"] is expected


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
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
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
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
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
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
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
        patch("repository.persona_repository.PersonaDB.get", return_value=None),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
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
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
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
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    human_message = kwargs["input"]["messages"][0]
    assert "is_regenerate" not in human_message.additional_kwargs


class DummyAgentWithHistory(DummyAgent):
    """Adds aget_state_history for fork-point resolution tests."""

    def __init__(self, snapshots):
        self._snapshots = snapshots
        self.update_state_calls: list[tuple] = []

    async def aget_state_history(self, config):
        for snapshot in self._snapshots:
            yield snapshot

    async def aupdate_state(self, config, values, **kwargs):
        self.update_state_calls.append((config, values))
        return {"configurable": {"thread_id": "thread-1", "checkpoint_id": "edited-1"}}


class _FakeSnapshot:
    def __init__(self, messages, checkpoint_id):
        self.values = {"messages": messages}
        self.config = {"configurable": {"thread_id": "thread-1", "checkpoint_id": checkpoint_id}}


@pytest.mark.asyncio
async def test_handle_input_forks_the_checkpoint_for_a_resolvable_retry():
    """When the fork point resolves, the graph must be invoked from that
    historical checkpoint with NO new human message — the forked state
    already ends at the target human message, so appending a duplicate
    would put it back in context, defeating the whole point of forking."""
    from langchain_core.messages import AIMessage, HumanMessage

    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
        is_regenerate=True,
        retry_target_message_id=1,
    )

    snapshots = [
        _FakeSnapshot(
            [HumanMessage(content="hello"), AIMessage(content="rejected answer")],
            checkpoint_id="2",
        ),
        _FakeSnapshot([HumanMessage(content="hello")], checkpoint_id="1"),
    ]

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(
            user_input, DummyAgentWithHistory(snapshots), api_key_user_id="user-1"
        )

    assert kwargs["config"]["configurable"]["checkpoint_id"] == "1"
    assert kwargs["input"] is None


@pytest.mark.asyncio
async def test_handle_input_falls_back_to_duplicate_message_when_fork_point_unresolvable():
    """No matching checkpoint (e.g. legacy thread, or the target message
    doesn't exist) must fall back to the original append-to-tip behavior —
    a retry must never hard-fail."""
    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
        is_regenerate=True,
        retry_target_message_id=99,
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(
            user_input, DummyAgentWithHistory([]), api_key_user_id="user-1"
        )

    human_message = kwargs["input"]["messages"][0]
    assert human_message.additional_kwargs["is_regenerate"] is True
    assert kwargs["config"]["configurable"].get("checkpoint_id") is None


@pytest.mark.asyncio
async def test_handle_input_forks_and_replaces_the_message_for_a_resolvable_edit():
    """Editing a previous message must fork the checkpoint at that message
    (same as a retry) AND replace its content in place via aupdate_state —
    so the new response's context excludes the old response and anything
    sent after it, while the old branch stays reachable via history."""
    from langchain_core.messages import AIMessage, HumanMessage

    user_input = UserInput(
        message="edited hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
        is_edit=True,
        edit_target_message_id=1,
    )

    snapshots = [
        _FakeSnapshot(
            [HumanMessage(content="hello", id="h1"), AIMessage(content="old answer")],
            checkpoint_id="2",
        ),
        _FakeSnapshot([HumanMessage(content="hello", id="h1")], checkpoint_id="1"),
    ]
    agent = DummyAgentWithHistory(snapshots)

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, agent, api_key_user_id="user-1")

    # The forked checkpoint (right after message id=1) must have its
    # HumanMessage replaced in place (same id -> add_messages reducer
    # replaces rather than appends) with the edited text.
    assert len(agent.update_state_calls) == 1
    fork_config, values = agent.update_state_calls[0]
    assert fork_config["configurable"]["checkpoint_id"] == "1"
    replaced_message = values["messages"][0]
    assert replaced_message.id == "h1"
    assert replaced_message.content == "edited hello"

    # The graph must then be invoked from aupdate_state's returned config
    # with no new message — the edit is already applied.
    assert kwargs["config"]["configurable"]["checkpoint_id"] == "edited-1"
    assert kwargs["input"] is None


class _InterruptedAgentWithHistory(DummyAgentWithHistory):
    """A retry target that ALSO has a pending interrupt on its live tip.

    Reproduces design E8: a run paused on an `ask_user` question, then the
    user retries an earlier message instead of answering. The fork branches
    from a checkpoint before the interrupt, so the pending question belongs
    to the branch being abandoned and must never be resumed.
    """

    async def aget_state(self, config=None, **kwargs):
        task = SimpleNamespace(interrupts=[SimpleNamespace(value={"type": "user_clarification"})])
        return SimpleNamespace(tasks=[task], values={})


@pytest.mark.asyncio
async def test_handle_input_never_resumes_a_pending_interrupt_when_it_forks():
    """E8: fork + bekleyen interrupt → resume YOK, fork yolu kazanır.

    `resume_payload` dolu olsa bile: retry daha eski bir checkpoint'e
    dallanıyor, bekleyen soru terk edilen dalda kalıyor.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    user_input = UserInput(
        message="hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
        is_regenerate=True,
        retry_target_message_id=1,
        resume_payload={"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}},
    )

    snapshots = [
        _FakeSnapshot(
            [HumanMessage(content="hello"), AIMessage(content="rejected answer")],
            checkpoint_id="2",
        ),
        _FakeSnapshot([HumanMessage(content="hello")], checkpoint_id="1"),
    ]

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(
            user_input, _InterruptedAgentWithHistory(snapshots), api_key_user_id="user-1"
        )

    # Fork resolved to checkpoint 1, and the run starts there with NO input —
    # not a Command(resume=...).
    assert kwargs["config"]["configurable"]["checkpoint_id"] == "1"
    assert kwargs["input"] is None
    assert not isinstance(kwargs["input"], Command)


@pytest.mark.asyncio
async def test_handle_input_falls_back_to_append_when_edit_fork_point_unresolvable():
    """No matching checkpoint for the edited message (e.g. it no longer
    exists) must fall back to the original append-to-tip behavior — an
    edit must never hard-fail."""
    user_input = UserInput(
        message="edited hello",
        thread_id="thread-1",
        agent_id="configurable-mcp-agent",
        is_edit=True,
        edit_target_message_id=99,
    )
    agent = DummyAgentWithHistory([])

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": False, "extract_memory": True},
        ),
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, agent, api_key_user_id="user-1")

    assert not agent.update_state_calls
    human_message = kwargs["input"]["messages"][0]
    assert human_message.content == "edited hello"
    assert kwargs["config"]["configurable"].get("checkpoint_id") is None


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

    monkeypatch.setattr("repository.persona_repository.PersonaDB.get", fake_get)
    monkeypatch.setattr(
        "repository.agent_definition_repository.AgentDefinitionRepository",
        FakeDefinitionRepository,
    )
    monkeypatch.setattr(
        "service.StoreService.get_assistant_from_store", AsyncMock(return_value=None)
    )

    graph_id, config = await get_graph_and_config(23)

    assert graph_id == "definition-1"
    assert config["owner_user_id"] == "owner-user"


@pytest.mark.asyncio
async def test_handle_input_dynamic_agent_without_long_term_memory_type_does_not_participate():
    """A dynamic AgentDefinition agent that did not set memory_type == "long_term"
    stays out of memory even when the user's recall setting is on."""
    user_input = UserInput(
        message="hello",
        thread_id="thread-2",
        agent_id="8f0c4d1e-2b3a-4c5d-6e7f-8a9b0c1d2e3f",
        agent_config={},
    )

    with (
        patch("service.StoreService.get_thread_from_store", return_value={"metadata": {}}),
        patch("service.StoreService.add_thread", new=AsyncMock()),
        patch(
            "service.UserServiceClient.get_user_settings",
            return_value={"long_term_memory_enabled": True, "extract_memory": True},
        ),
        patch("repository.persona_repository.PersonaDB.get", return_value={"is_builtin": True}),
        patch("repository.persona_repository.PersonaDB.get_by_builtin_key", return_value=None),
    ):
        kwargs, _ = await _handle_input(user_input, DummyAgent(), api_key_user_id="user-1")

    assert kwargs["config"]["configurable"]["long_term_memory"] is False

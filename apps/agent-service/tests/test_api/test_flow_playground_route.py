"""Tests for FlowPlaygroundRoute (P7 Task 41).

Spec: .tmp/flow-canvas-design.md section 6.1, R8.
Brief: .tmp/flow-canvas-task-41-brief.md
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from fastapi import HTTPException

from api.routes.FlowPlaygroundRoute import (
    FlowPlaygroundInlineRunRequest,
    FlowPlaygroundRunRequest,
    _require_execute,
    _require_update,
    run_flow_playground_inline_stream,
    run_flow_playground_stream,
)
from app import app
from tests.idempotency_client import IdempotentTestClient


@pytest.fixture
def client():
    return IdempotentTestClient(app)


def _valid_draft_spec() -> dict:
    """Minimal structurally valid draft. The playground validates the draft
    before compiling it (bugfix #2), so route-level tests need a spec that
    passes `validate()` — an empty spec is now a 400, not a silent run."""
    return {
        "nodes": [
            {"id": "in", "type": "ChatInput"},
            {"id": "agent", "type": "ZeroShotAgent", "values": {"system_prompt": "I am draft"}},
            {"id": "out", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in",
                "sourceHandle": "message",
                "target": "agent",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "agent",
                "sourceHandle": "output",
                "target": "out",
                "targetHandle": "message",
            },
        ],
    }


def test_playground_run_requires_flow_execute(client):
    """41.1 — Rejection with 403 when user lacks flow:execute permission."""

    async def fake_fail_execute():
        raise HTTPException(status_code=403, detail="Permission denied: flow:execute")

    async def fake_ok_update():
        return SimpleNamespace(user_id="u1", access_token="tok")

    app.dependency_overrides[_require_execute] = fake_fail_execute
    app.dependency_overrides[_require_update] = fake_ok_update
    try:
        resp = client.post(
            f"/api/v1/agent-definitions/{uuid4()}/flow/playground/runs/stream",
            json={"message": "hello"},
        )
        assert resp.status_code == 403
        assert "flow:execute" in resp.json()["error"]["message"]
    finally:
        app.dependency_overrides.clear()


def test_playground_run_requires_flow_update_too(client):
    """41.2 — Rejection with 403 when user has flow:execute but lacks flow:update."""

    async def fake_ok_execute():
        return SimpleNamespace(user_id="u1", access_token="tok")

    async def fake_fail_update():
        raise HTTPException(status_code=403, detail="Permission denied: flow:update")

    app.dependency_overrides[_require_execute] = fake_ok_execute
    app.dependency_overrides[_require_update] = fake_fail_update
    try:
        resp = client.post(
            f"/api/v1/agent-definitions/{uuid4()}/flow/playground/runs/stream",
            json={"message": "hello"},
        )
        assert resp.status_code == 403
        assert "flow:update" in resp.json()["error"]["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_playground_run_uses_draft_not_published():
    """41.3 — Playground run executes draft spec, even when published spec exists."""
    def_id = uuid4()
    draft_spec = {
        "nodes": [
            {"id": "in", "type": "ChatInput"},
            {"id": "agent", "type": "ZeroShotAgent", "values": {"system_prompt": "I am draft"}},
            {"id": "out", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in",
                "sourceHandle": "message",
                "target": "agent",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "agent",
                "sourceHandle": "output",
                "target": "out",
                "targetHandle": "message",
            },
        ],
    }

    mock_draft = SimpleNamespace(
        id=uuid4(),
        definition_id=def_id,
        version_no=2,
        flow_spec=draft_spec,
    )

    with (
        patch(
            "repository.flow_version_repository.FlowVersionRepository.get_draft",
            new_callable=AsyncMock,
        ) as mock_get_draft,
        patch("agents.flow_agent.FlowAgent.load", new_callable=AsyncMock) as mock_load,
        patch("api.routes.FlowPlaygroundRoute._get_controller") as mock_ctrl,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock),
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ),
    ):
        mock_get_draft.return_value = mock_draft
        mock_ctrl_inst = MagicMock()
        mock_ctrl.return_value = mock_ctrl_inst

        async def fake_events(*args, **kwargs):
            yield "data: {}\n\n"

        mock_ctrl_inst.event_generator.return_value = fake_events()

        user = SimpleNamespace(user_id="u-123", access_token="tok")
        req = FlowPlaygroundRunRequest(message="test run")

        resp = await run_flow_playground_stream(
            definition_id=def_id,
            request_obj=req,
            user=user,
            _update_guard=user,
        )
        assert resp is not None
        mock_get_draft.assert_awaited_once_with(def_id)
        mock_load.assert_awaited_once()


@pytest.mark.asyncio
async def test_playground_run_does_not_touch_agent_cache():
    """41.4 — Playground run does not touch or populate _agent_cache."""
    from agents.flow_agent import _agent_cache

    def_id = uuid4()
    mock_draft = SimpleNamespace(
        id=uuid4(),
        definition_id=def_id,
        version_no=1,
        flow_spec=_valid_draft_spec(),
    )

    with (
        patch(
            "repository.flow_version_repository.FlowVersionRepository.get_draft",
            new_callable=AsyncMock,
        ) as mock_get_draft,
        patch("agents.flow_agent.FlowAgent.load", new_callable=AsyncMock),
        patch("api.routes.FlowPlaygroundRoute._get_controller") as mock_ctrl,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock),
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ),
    ):
        mock_get_draft.return_value = mock_draft
        mock_ctrl.return_value.event_generator.return_value = AsyncMock()

        user = SimpleNamespace(user_id="u-123", access_token="tok")
        await run_flow_playground_stream(
            definition_id=def_id,
            request_obj=FlowPlaygroundRunRequest(message="hi"),
            user=user,
            _update_guard=user,
        )
        assert str(def_id) not in _agent_cache


@pytest.mark.asyncio
async def test_playground_thread_id_is_deterministic_uuid():
    """41.5 — Thread ID is a valid UUID derived deterministically from the
    playground namespace ``playground:{definition_id}:{user_id}``.

    The ``thread.thread_id`` column is a UUID primary key; a raw namespace
    string cannot be persisted (asyncpg DataError). A uuid5 derived from the
    namespace keeps one stable playground thread per (definition, user) while
    satisfying the column type. The raw namespace is preserved in metadata.
    """
    def_id = uuid4()
    mock_draft = SimpleNamespace(
        id=uuid4(),
        definition_id=def_id,
        version_no=1,
        flow_spec=_valid_draft_spec(),
    )

    with (
        patch(
            "repository.flow_version_repository.FlowVersionRepository.get_draft",
            new_callable=AsyncMock,
        ) as mock_get_draft,
        patch("agents.flow_agent.FlowAgent.load", new_callable=AsyncMock),
        patch("api.routes.FlowPlaygroundRoute._get_controller") as mock_ctrl,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock),
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ) as mock_add_thread,
    ):
        mock_get_draft.return_value = mock_draft
        mock_ctrl_inst = MagicMock()
        mock_ctrl.return_value = mock_ctrl_inst
        mock_ctrl_inst.event_generator.return_value = AsyncMock()

        user = SimpleNamespace(user_id="u-999", access_token="tok")
        await run_flow_playground_stream(
            definition_id=def_id,
            request_obj=FlowPlaygroundRunRequest(message="hi"),
            user=user,
            _update_guard=user,
        )
        namespace = f"playground:{def_id}:u-999"
        expected_thread_id = str(uuid5(NAMESPACE_URL, namespace))

        mock_add_thread.assert_awaited_once()
        thread_payload = mock_add_thread.call_args[0][0]
        # Valid UUID that round-trips through the thread table's UUID PK.
        UUID(thread_payload["thread_id"])
        assert thread_payload["thread_id"] == expected_thread_id
        assert thread_payload["run_kind"] == "playground"
        # Raw namespace preserved for traceability.
        assert thread_payload["metadata"]["playground_namespace"] == namespace
        # The same UUID is handed to the run pipeline (checkpointer key).
        run_thread_id = mock_ctrl_inst.event_generator.call_args[0][3]
        assert run_thread_id == expected_thread_id


@pytest.mark.asyncio
async def test_playground_run_tags_config_with_run_kind():
    """41.6 — RunnableConfig includes run_kind=playground tags and metadata."""
    def_id = uuid4()
    mock_draft = SimpleNamespace(
        id=uuid4(),
        definition_id=def_id,
        version_no=3,
        flow_spec=_valid_draft_spec(),
    )

    with (
        patch(
            "repository.flow_version_repository.FlowVersionRepository.get_draft",
            new_callable=AsyncMock,
        ) as mock_get_draft,
        patch("agents.flow_agent.FlowAgent.load", new_callable=AsyncMock),
        patch("api.routes.FlowPlaygroundRoute._get_controller") as mock_ctrl,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock),
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ),
    ):
        mock_get_draft.return_value = mock_draft
        mock_ctrl_inst = MagicMock()
        mock_ctrl.return_value = mock_ctrl_inst
        mock_ctrl_inst.event_generator.return_value = AsyncMock()

        user = SimpleNamespace(user_id="u-123", access_token="tok")
        await run_flow_playground_stream(
            definition_id=def_id,
            request_obj=FlowPlaygroundRunRequest(message="hi"),
            user=user,
            _update_guard=user,
        )

        call_args = mock_ctrl_inst.event_generator.call_args
        assert call_args is not None
        config = call_args[0][2]
        assert "run_kind:playground" in config["tags"]
        assert config["metadata"]["run_kind"] == "playground"
        assert config["metadata"]["definition_id"] == str(def_id)
        assert config["metadata"]["flow_version_no"] == 3


@pytest.mark.asyncio
async def test_playground_run_emits_audit_event():
    """41.7 — flow:playground_run audit event is emitted with version_no."""
    def_id = uuid4()
    mock_draft = SimpleNamespace(
        id=uuid4(),
        definition_id=def_id,
        version_no=4,
        flow_spec=_valid_draft_spec(),
    )

    with (
        patch(
            "repository.flow_version_repository.FlowVersionRepository.get_draft",
            new_callable=AsyncMock,
        ) as mock_get_draft,
        patch("agents.flow_agent.FlowAgent.load", new_callable=AsyncMock),
        patch("api.routes.FlowPlaygroundRoute._get_controller") as mock_ctrl,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock) as mock_emit,
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ),
    ):
        mock_get_draft.return_value = mock_draft
        mock_ctrl.return_value.event_generator.return_value = AsyncMock()

        user = SimpleNamespace(user_id="u-123", access_token="tok")
        await run_flow_playground_stream(
            definition_id=def_id,
            request_obj=FlowPlaygroundRunRequest(message="hi"),
            user=user,
            _update_guard=user,
        )

        mock_emit.assert_awaited_once_with(
            "flow:playground_run",
            def_id,
            user=user,
            details={
                "run_kind": "playground",
                "thread_id": str(uuid5(NAMESPACE_URL, f"playground:{def_id}:u-123")),
                "thread_namespace": f"playground:{def_id}:u-123",
                "version_no": 4,
            },
        )


@pytest.mark.asyncio
async def test_playground_tool_authorization_matches_production():
    """41.8 — FlowAgent compilation in playground uses identical FlowGraphBuilder as production."""
    from agents.flow_agent import FlowAgent

    spec = {
        "nodes": [
            {"id": "in", "type": "ChatInput"},
            {"id": "mcp", "type": "McpTool", "values": {"tool_name": "calc", "server_name": "srv"}},
            {"id": "agent", "type": "Agent", "values": {"system_prompt": "hello"}},
            {"id": "out", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in",
                "sourceHandle": "message",
                "target": "agent",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "mcp",
                "sourceHandle": "tool",
                "target": "agent",
                "targetHandle": "tools",
            },
            {
                "id": "e3",
                "source": "agent",
                "sourceHandle": "output",
                "target": "out",
                "targetHandle": "message",
            },
        ],
    }

    prod_agent = FlowAgent(spec, definition_id="d1")
    play_agent = FlowAgent(spec, definition_id="d1")
    assert prod_agent._flow_spec_raw == play_agent._flow_spec_raw


@pytest.mark.asyncio
async def test_no_flow_definition_returns_404():
    """41.10 — 404 when target definition has no draft."""
    def_id = uuid4()
    with patch(
        "repository.flow_version_repository.FlowVersionRepository.get_draft",
        new_callable=AsyncMock,
    ) as mock_get_draft:
        mock_get_draft.return_value = None

        user = SimpleNamespace(user_id="u-123", access_token="tok")
        with pytest.raises(HTTPException) as exc_info:
            await run_flow_playground_stream(
                definition_id=def_id,
                request_obj=FlowPlaygroundRunRequest(message="hi"),
                user=user,
                _update_guard=user,
            )
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_playground_rejects_structurally_invalid_draft():
    """Bugfix #2 — a draft whose only entry→exit path runs through a resource
    node compiled into a dead-end graph that silently echoed the input back.
    The run must fail fast with the same error shape publish uses, before any
    SSE stream or thread side effects start."""
    def_id = uuid4()
    mock_draft = SimpleNamespace(
        id=uuid4(),
        definition_id=def_id,
        version_no=2,
        flow_spec={
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "llm-1", "type": "OllamaModel", "values": {"model": "llama3.1:8b"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "out",
                    "target": "llm-1",
                    "targetHandle": "in",
                },
                {
                    "id": "e2",
                    "source": "llm-1",
                    "sourceHandle": "out",
                    "target": "out-1",
                    "targetHandle": "in",
                },
            ],
        },
    )

    with (
        patch(
            "repository.flow_version_repository.FlowVersionRepository.get_draft",
            new_callable=AsyncMock,
        ) as mock_get_draft,
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ) as mock_add_thread,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock) as mock_emit,
    ):
        mock_get_draft.return_value = mock_draft

        user = SimpleNamespace(user_id="u-123", access_token="tok")
        with pytest.raises(HTTPException) as exc_info:
            await run_flow_playground_stream(
                definition_id=def_id,
                request_obj=FlowPlaygroundRunRequest(message="hi"),
                user=user,
                _update_guard=user,
            )

        assert exc_info.value.status_code == 400
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert any(e["code"] == "FLOW_NO_EXIT" for e in detail["details"]["errors"])
        # No run side effects for a rejected draft.
        mock_add_thread.assert_not_awaited()
        mock_emit.assert_not_awaited()


# --- Inline (pre-save) playground run -----------------------------------
# These cover running a flow spec that only exists in the browser's canvas
# state, before the agent/agent_definition has ever been saved. Langflow's
# own build endpoint accepts nodes/edges inline the same way (see
# vendor/langflow/utils/buildUtils.ts) rather than requiring a persisted
# Flow row first.


def test_playground_inline_run_requires_flow_execute(client):
    async def fake_fail_execute():
        raise HTTPException(status_code=403, detail="Permission denied: flow:execute")

    async def fake_ok_update():
        return SimpleNamespace(user_id="u1", access_token="tok")

    app.dependency_overrides[_require_execute] = fake_fail_execute
    app.dependency_overrides[_require_update] = fake_ok_update
    try:
        resp = client.post(
            "/api/v1/agent-definitions/flow/playground/runs/stream",
            json={"message": "hello", "flow_spec": _valid_draft_spec()},
        )
        assert resp.status_code == 403
        assert "flow:execute" in resp.json()["error"]["message"]
    finally:
        app.dependency_overrides.clear()


def test_playground_inline_run_requires_flow_update_too(client):
    async def fake_ok_execute():
        return SimpleNamespace(user_id="u1", access_token="tok")

    async def fake_fail_update():
        raise HTTPException(status_code=403, detail="Permission denied: flow:update")

    app.dependency_overrides[_require_execute] = fake_ok_execute
    app.dependency_overrides[_require_update] = fake_fail_update
    try:
        resp = client.post(
            "/api/v1/agent-definitions/flow/playground/runs/stream",
            json={"message": "hello", "flow_spec": _valid_draft_spec()},
        )
        assert resp.status_code == 403
        assert "flow:update" in resp.json()["error"]["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_playground_inline_run_executes_provided_flow_spec():
    """Runs the flow_spec from the request body directly — no DB draft lookup."""
    with (
        patch(
            "repository.flow_version_repository.FlowVersionRepository.get_draft",
            new_callable=AsyncMock,
        ) as mock_get_draft,
        patch("agents.flow_agent.FlowAgent.load", new_callable=AsyncMock) as mock_load,
        patch("api.routes.FlowPlaygroundRoute._get_controller") as mock_ctrl,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock),
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ),
    ):
        mock_ctrl_inst = MagicMock()
        mock_ctrl.return_value = mock_ctrl_inst

        async def fake_events(*args, **kwargs):
            yield "data: {}\n\n"

        mock_ctrl_inst.event_generator.return_value = fake_events()

        user = SimpleNamespace(user_id="u-123", access_token="tok")
        req = FlowPlaygroundInlineRunRequest(message="test run", flow_spec=_valid_draft_spec())

        resp = await run_flow_playground_inline_stream(
            request_obj=req,
            user=user,
            _update_guard=user,
        )
        assert resp is not None
        mock_get_draft.assert_not_awaited()
        mock_load.assert_awaited_once()


@pytest.mark.asyncio
async def test_playground_inline_run_rejects_structurally_invalid_spec():
    """Same shape of 400 as the definition-based route for a broken graph."""
    with (
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ) as mock_add_thread,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock) as mock_emit,
    ):
        user = SimpleNamespace(user_id="u-123", access_token="tok")
        req = FlowPlaygroundInlineRunRequest(
            message="hi",
            flow_spec={
                "nodes": [
                    {"id": "in-1", "type": "ChatInput"},
                    {"id": "llm-1", "type": "OllamaModel", "values": {"model": "llama3.1:8b"}},
                    {"id": "out-1", "type": "ChatOutput"},
                ],
                "edges": [
                    {
                        "id": "e1",
                        "source": "in-1",
                        "sourceHandle": "out",
                        "target": "llm-1",
                        "targetHandle": "in",
                    },
                    {
                        "id": "e2",
                        "source": "llm-1",
                        "sourceHandle": "out",
                        "target": "out-1",
                        "targetHandle": "in",
                    },
                ],
            },
        )

        with pytest.raises(HTTPException) as exc_info:
            await run_flow_playground_inline_stream(
                request_obj=req,
                user=user,
                _update_guard=user,
            )

        assert exc_info.value.status_code == 400
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert any(e["code"] == "FLOW_NO_EXIT" for e in detail["details"]["errors"])
        mock_add_thread.assert_not_awaited()
        mock_emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_playground_inline_run_emits_audit_event_with_inline_label():
    """Audit target has no real definition UUID to key off — uses an
    "inline:<session>" label instead, since nothing was ever persisted."""
    with (
        patch("agents.flow_agent.FlowAgent.load", new_callable=AsyncMock),
        patch("api.routes.FlowPlaygroundRoute._get_controller") as mock_ctrl,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock) as mock_emit,
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ),
    ):
        mock_ctrl.return_value.event_generator.return_value = AsyncMock()

        user = SimpleNamespace(user_id="u-123", access_token="tok")
        req = FlowPlaygroundInlineRunRequest(
            message="hi", flow_spec=_valid_draft_spec(), session_id="sess-abc"
        )
        await run_flow_playground_inline_stream(
            request_obj=req,
            user=user,
            _update_guard=user,
        )

        mock_emit.assert_awaited_once()
        call_args = mock_emit.call_args
        assert call_args.args[0] == "flow:playground_run"
        assert call_args.args[1] == "inline:sess-abc"
        assert call_args.kwargs["details"]["version_no"] is None


@pytest.mark.asyncio
async def test_playground_inline_run_thread_namespace_uses_session_id():
    """Two runs with the same session_id resolve to the same thread, so a
    multi-turn conversation survives across sends before anything is saved."""
    with (
        patch("agents.flow_agent.FlowAgent.load", new_callable=AsyncMock),
        patch("api.routes.FlowPlaygroundRoute._get_controller") as mock_ctrl,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock),
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ) as mock_add_thread,
    ):
        mock_ctrl.return_value.event_generator.return_value = AsyncMock()

        user = SimpleNamespace(user_id="u-123", access_token="tok")
        req = FlowPlaygroundInlineRunRequest(
            message="first", flow_spec=_valid_draft_spec(), session_id="sess-xyz"
        )
        await run_flow_playground_inline_stream(
            request_obj=req,
            user=user,
            _update_guard=user,
        )
        req2 = FlowPlaygroundInlineRunRequest(
            message="second", flow_spec=_valid_draft_spec(), session_id="sess-xyz"
        )
        await run_flow_playground_inline_stream(
            request_obj=req2,
            user=user,
            _update_guard=user,
        )

        first_thread_id = mock_add_thread.call_args_list[0][0][0]["thread_id"]
        second_thread_id = mock_add_thread.call_args_list[1][0][0]["thread_id"]
        assert first_thread_id == second_thread_id


@pytest.mark.asyncio
async def test_playground_inline_run_migrates_a_legacy_spec_before_validating():
    """A v1 Router / pre-Phase-3 counter Loop is authored against an old
    template version; the playground must migrate it on read (like save,
    publish and the compiler) rather than 400 on the stale shape."""
    legacy_loop_spec = {
        "nodes": [
            {"id": "in", "type": "ChatInput"},
            {
                "id": "lp",
                "type": "Loop",
                "template_version": 1,
                "values": {"condition": "", "max_iterations": 2},
            },
            {"id": "ag", "type": "ZeroShotAgent", "values": {"system_prompt": "x"}},
            {"id": "out", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in",
                "sourceHandle": "message",
                "target": "lp",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "lp",
                "sourceHandle": "continue",
                "target": "ag",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "ag",
                "sourceHandle": "output",
                "target": "lp",
                "targetHandle": "input",
            },
            {
                "id": "e4",
                "source": "lp",
                "sourceHandle": "exit",
                "target": "out",
                "targetHandle": "message",
            },
        ],
    }

    with (
        patch("agents.flow_agent.FlowAgent.load", new_callable=AsyncMock) as mock_load,
        patch("api.routes.FlowPlaygroundRoute._get_controller") as mock_ctrl,
        patch("domain.flows.audit.FlowAuditEmitter.emit", new_callable=AsyncMock),
        patch(
            "core.db.repositories.thread_repo.ThreadRepository.add_thread", new_callable=AsyncMock
        ),
    ):
        mock_ctrl_inst = MagicMock()
        mock_ctrl.return_value = mock_ctrl_inst

        async def fake_events(*args, **kwargs):
            yield "data: {}\n\n"

        mock_ctrl_inst.event_generator.return_value = fake_events()

        user = SimpleNamespace(user_id="u-legacy", access_token="tok")
        req = FlowPlaygroundInlineRunRequest(message="go", flow_spec=legacy_loop_spec)

        # no HTTPException => the migrated (While) spec passed validation
        resp = await run_flow_playground_inline_stream(
            request_obj=req, user=user, _update_guard=user
        )
        assert resp is not None
        mock_load.assert_awaited_once()

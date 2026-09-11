"""Tests for flow:created / flow:deleted audit emission on the classic
CRUD endpoints (P3 Task 19).

A flow-backed agent is created/deleted through the SAME generic
POST/DELETE /agent-definitions endpoints classic agents use — there is no
dedicated "create a flow" endpoint (Task 15's finding: FlowService.save_flow
is never called from any route). These endpoints must only emit flow:*
events when graph_schema == "flow", and must never emit for classic agents
(constraint #1 applied to audit noise).

Brief: .tmp/flow-canvas-task-19-brief.md
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import api.routes.AgentDefinitionsRoute as agent_definitions_route
from app import app
from service.AuthService import AuthenticatedUser, require_user
from tests.idempotency_client import IdempotentTestClient


def _fake_dev_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="dev-user", email="dev-user@local.dev")


@pytest.fixture
def authorized_client():
    app.dependency_overrides[require_user] = _fake_dev_user
    try:
        yield IdempotentTestClient(app)
    finally:
        app.dependency_overrides.pop(require_user, None)


class _FakeAuditEmitter:
    def __init__(self) -> None:
        self.emitted: list[dict] = []

    async def emit(self, action, definition_id, *, user, details=None):
        self.emitted.append(
            {"action": action, "definition_id": definition_id, "details": details or {}}
        )

    def should_emit_draft_update(self, definition_id: str) -> bool:
        return True


@pytest.fixture
def fake_audit_emitter(monkeypatch):
    # get_flow_audit_emitter is imported locally inside the route handlers
    # (from domain.flows.audit import ...), re-resolving the module attribute
    # on every call — patching the origin module is what the lazy import sees.
    emitter = _FakeAuditEmitter()
    monkeypatch.setattr("domain.flows.audit.get_flow_audit_emitter", lambda: emitter)
    return emitter


class _FakeAgentDefService:
    def __init__(self, definition, versions=None) -> None:
        self.definition = definition
        self.versions = versions or []
        self.delete_called_with = None

    async def create_agent_definition(self, **kwargs):
        return self.definition

    async def get_agent_definition(self, _id):
        return self.definition

    async def delete_agent_definition(self, definition_id):
        self.delete_called_with = definition_id
        return True


@pytest.fixture
def fake_agent_def_service(monkeypatch):
    def _install(definition, versions=None):
        service = _FakeAgentDefService(definition, versions)
        monkeypatch.setattr(agent_definitions_route, "_get_service", lambda: service)
        return service

    return _install


def _minimal_create_body(graph_schema: str) -> dict:
    return {"name": f"agent-{uuid4()}", "graph_schema": graph_schema}


# ---------------------------------------------------------------------------
# flow:created
# ---------------------------------------------------------------------------


def test_creating_flow_backed_agent_emits_flow_created(
    authorized_client, fake_agent_def_service, fake_audit_emitter
):
    definition_id = uuid4()
    definition = SimpleNamespace(
        id=definition_id,
        persona_id=None,
        name="x",
        agent_type="dynamic",
        graph_schema="flow",
        brain_type="llm",
        memory_type="none",
        description=None,
        system_prompt=None,
        model=None,
        mcp_tools=[],
        rag_config={},
        sub_agents=[],
        sub_agent_ids=[],
        supervisor_prompt=None,
        stages=[],
        pipeline_prompt=None,
        reflection_prompt=None,
        max_iterations=3,
        version="1.0.0",
        tags=[],
        is_active=True,
        created_at=None,
        updated_at=None,
    )
    fake_agent_def_service(definition)

    authorized_client.post("/api/v1/agent-definitions", json=_minimal_create_body("flow"))

    assert fake_audit_emitter.emitted[0]["action"] == "flow:created"
    assert fake_audit_emitter.emitted[0]["definition_id"] == definition_id
    assert fake_audit_emitter.emitted[0]["details"] == {"node_count": 0, "edge_count": 0}


def test_creating_classic_agent_does_not_emit_flow_created(
    authorized_client, fake_agent_def_service, fake_audit_emitter
):
    definition = SimpleNamespace(
        id=uuid4(),
        persona_id=None,
        name="x",
        agent_type="dynamic",
        graph_schema="react",
        brain_type="llm",
        memory_type="none",
        description=None,
        system_prompt=None,
        model=None,
        mcp_tools=[],
        rag_config={},
        sub_agents=[],
        sub_agent_ids=[],
        supervisor_prompt=None,
        stages=[],
        pipeline_prompt=None,
        reflection_prompt=None,
        max_iterations=3,
        version="1.0.0",
        tags=[],
        is_active=True,
        created_at=None,
        updated_at=None,
    )
    fake_agent_def_service(definition)

    authorized_client.post("/api/v1/agent-definitions", json=_minimal_create_body("react"))

    assert fake_audit_emitter.emitted == []


# ---------------------------------------------------------------------------
# flow:deleted
# ---------------------------------------------------------------------------


def test_deleting_flow_backed_agent_emits_flow_deleted_with_last_version_no(
    authorized_client, fake_agent_def_service, fake_audit_emitter, monkeypatch
):
    definition_id = uuid4()
    definition = SimpleNamespace(id=definition_id, graph_schema="flow")
    fake_agent_def_service(definition)

    class _FakeVersionRepo:
        async def list_versions(self, _definition_id):
            return [SimpleNamespace(version_no=3), SimpleNamespace(version_no=2)]

    monkeypatch.setattr(
        "repository.flow_version_repository.FlowVersionRepository", _FakeVersionRepo
    )

    authorized_client.delete(f"/api/v1/agent-definitions/{definition_id}")

    assert fake_audit_emitter.emitted[0]["action"] == "flow:deleted"
    assert fake_audit_emitter.emitted[0]["definition_id"] == definition_id
    assert fake_audit_emitter.emitted[0]["details"] == {"last_version_no": 3}


def test_deleting_classic_agent_does_not_emit_flow_deleted(
    authorized_client, fake_agent_def_service, fake_audit_emitter
):
    definition_id = uuid4()
    definition = SimpleNamespace(id=definition_id, graph_schema="react")
    fake_agent_def_service(definition)

    authorized_client.delete(f"/api/v1/agent-definitions/{definition_id}")

    assert fake_audit_emitter.emitted == []

"""Tests for the flow-versions HTTP surface (draft/versions/publish).

Auth pattern matches test_flow_components_route.py exactly (Task 6): this
dev environment has KEYCLOAK_ENABLED=true, so there is no dev-mode bypass —
override the shared require_user dependency, which require_permission
already special-cases for user_id == "dev-user".

The route layer is tested against a FAKE FlowService (monkeypatching the
module's own _get_service() seam) rather than a real database — persistence
correctness (atomicity, constraint enforcement, cache invalidation) is
already proven against a real SQLite engine in
tests/agents/storage/test_publish_transaction.py and
tests/domain/flows/test_service_publish.py. This test file's job is HTTP
shape: status codes, auth, and error-body format.

Spec: .tmp/flow-canvas-design.md sections 5, 10.
Brief: .tmp/flow-canvas-task-16-brief.md
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

import api.routes.FlowVersionsRoute as flow_versions_route
from api import dependencies as auth_service
from app import app
from core.exceptions import (
    FlowValidationError,
    FlowVersionConflictError,
    UnknownComponentError,
)
from domain.flows.validator import ValidationIssue
from service.AuthService import AuthenticatedUser, require_user
from tests.idempotency_client import IdempotentTestClient


def _fake_dev_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="dev-user", email="dev-user@local.dev")


@pytest.fixture
def auth_enforced(monkeypatch):
    """Make the 401 assertions independent of the developer's `.env`.

    These tests used to rely on `KEYCLOAK_ENABLED=true` being set ambiently.
    The checked-in `configs/.env` has it `false`, and with no API keys
    configured `require_user` then hands out a `dev-user` to anyone — so the
    tests that exist to prove "no token is rejected" instead exercised the dev
    bypass and failed. Forcing the enforcing branch on states the intent.
    """
    monkeypatch.setattr(auth_service, "_is_keycloak_enabled", lambda: True)


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


@pytest.fixture(autouse=True)
def fake_audit_emitter(monkeypatch):
    """Every route test gets a no-network fake by default — publish/rollback/
    save_draft must never attempt a real call to user-service in this suite;
    tests that care about emitted events read fake_audit_emitter.emitted."""
    emitter = _FakeAuditEmitter()
    monkeypatch.setattr(flow_versions_route, "get_flow_audit_emitter", lambda: emitter)
    return emitter


class _FakeFlowService:
    def __init__(self) -> None:
        self.draft_spec = None
        self.versions: list = []
        self.publish_result = None
        self.publish_error: Exception | None = None
        self.saved_drafts: list = []
        self.save_draft_error: Exception | None = None
        self.publish_calls: list = []
        self.rollback_result = None
        self.rollback_error: Exception | None = None
        self.rollback_calls: list = []
        self.version_detail = None

    async def load_draft(self, definition_id):
        return self.draft_spec

    async def save_draft(self, *, definition_id, flow_spec, user_id):
        self.saved_drafts.append(
            {"definition_id": definition_id, "flow_spec": flow_spec, "user_id": user_id}
        )
        if self.save_draft_error is not None:
            raise self.save_draft_error
        return SimpleNamespace(
            id=uuid4(),
            definition_id=definition_id,
            version_no=1,
            status="draft",
            created_by=user_id,
            published_by=None,
            created_at=datetime.utcnow(),
            published_at=None,
            notes=None,
        )

    async def list_versions(self, definition_id):
        return self.versions

    async def load_version(self, definition_id, version_no):
        return self.version_detail

    async def publish_flow(
        self,
        *,
        definition_id,
        published_by,
        context,
        expected_version_no=None,
        notes=None,
    ):
        self.publish_calls.append(
            {
                "definition_id": definition_id,
                "published_by": published_by,
                "expected_version_no": expected_version_no,
                "notes": notes,
            }
        )
        if self.publish_error is not None:
            raise self.publish_error
        return self.publish_result

    async def rollback_flow(self, *, definition_id, target_version_no, published_by):
        self.rollback_calls.append(
            {
                "definition_id": definition_id,
                "target_version_no": target_version_no,
                "published_by": published_by,
            }
        )
        if self.rollback_error is not None:
            raise self.rollback_error
        return self.rollback_result


@pytest.fixture
def fake_service(monkeypatch):
    service = _FakeFlowService()
    monkeypatch.setattr(flow_versions_route, "_get_service", lambda: service)
    return service


def _valid_flow_dict() -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [],
    }


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


def test_get_draft_requires_authentication(auth_enforced):
    response = IdempotentTestClient(app).get(f"/api/v1/agent-definitions/{uuid4()}/flow/draft")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET draft
# ---------------------------------------------------------------------------


def test_get_draft_returns_404_when_absent(authorized_client, fake_service):
    fake_service.draft_spec = None

    response = authorized_client.get(f"/api/v1/agent-definitions/{uuid4()}/flow/draft")

    assert response.status_code == 404


def test_get_draft_returns_200_with_spec(authorized_client, fake_service):
    from models.flows import FlowSpec

    fake_service.draft_spec = FlowSpec.model_validate(_valid_flow_dict())

    response = authorized_client.get(f"/api/v1/agent-definitions/{uuid4()}/flow/draft")

    assert response.status_code == 200
    body = response.json()
    assert body["nodes"][0]["type"] == "ChatInput"


# ---------------------------------------------------------------------------
# PUT draft
# ---------------------------------------------------------------------------


def test_save_draft_returns_200_and_records_user(authorized_client, fake_service):
    definition_id = uuid4()

    response = authorized_client.put(
        f"/api/v1/agent-definitions/{definition_id}/flow/draft",
        json={"flow_spec": _valid_flow_dict()},
    )

    assert response.status_code == 200
    assert fake_service.saved_drafts[0]["user_id"] == "dev-user"
    assert fake_service.saved_drafts[0]["definition_id"] == definition_id


def test_save_draft_returns_400_for_invalid_body(authorized_client, fake_service):
    response = authorized_client.put(
        f"/api/v1/agent-definitions/{uuid4()}/flow/draft",
        json={"flow_spec": {"nodes": "not-a-list"}},
    )

    assert response.status_code == 400


def test_save_draft_maps_unknown_component_to_400(authorized_client, fake_service):
    """A draft referencing an unregistered component type must be a 400
    validation response, never a 500 (live incident: saving a draft with a
    node of type 'Agent' blew up in migrate_flow)."""
    fake_service.save_draft_error = UnknownComponentError("Agent")

    response = authorized_client.put(
        f"/api/v1/agent-definitions/{uuid4()}/flow/draft",
        json={"flow_spec": _valid_flow_dict()},
    )

    assert response.status_code == 400
    assert "Agent" in response.json()["error"]["message"]


# ---------------------------------------------------------------------------
# GET versions
# ---------------------------------------------------------------------------


def test_list_versions_returns_200_with_history(authorized_client, fake_service):
    fake_service.versions = [
        SimpleNamespace(
            id=uuid4(),
            definition_id=uuid4(),
            version_no=2,
            status="published",
            created_by="u1",
            published_by="publisher-1",
            created_at=datetime.utcnow(),
            published_at=datetime.utcnow(),
            notes=None,
        )
    ]

    response = authorized_client.get(f"/api/v1/agent-definitions/{uuid4()}/flow/versions")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["version_no"] == 2
    assert body[0]["status"] == "published"


# ---------------------------------------------------------------------------
# POST publish
# ---------------------------------------------------------------------------


def test_publish_returns_200_with_published_version(authorized_client, fake_service):
    fake_service.publish_result = SimpleNamespace(
        id=uuid4(),
        definition_id=uuid4(),
        version_no=1,
        status="published",
        created_by="designer-1",
        published_by="dev-user",
        created_at=datetime.utcnow(),
        published_at=datetime.utcnow(),
        notes=None,
    )

    response = authorized_client.post(f"/api/v1/agent-definitions/{uuid4()}/flow/publish")

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert fake_service.publish_calls[0]["published_by"] == "dev-user"


def test_publish_returns_409_on_conflict(authorized_client, fake_service):
    fake_service.publish_error = FlowVersionConflictError("No draft exists")

    response = authorized_client.post(f"/api/v1/agent-definitions/{uuid4()}/flow/publish")

    assert response.status_code == 409


def test_publish_returns_400_with_issue_shape_on_validation_failure(
    authorized_client, fake_service
):
    fake_service.publish_error = FlowValidationError(
        [ValidationIssue(code="FLOW_NO_ENTRY", message="Flow has no Chat Input node")]
    )

    response = authorized_client.post(f"/api/v1/agent-definitions/{uuid4()}/flow/publish")

    assert response.status_code == 400
    body = response.json()["error"]["details"]
    assert any(e["code"] == "FLOW_NO_ENTRY" for e in body["errors"])


def test_publish_passes_expected_version_no_through(authorized_client, fake_service):
    fake_service.publish_result = SimpleNamespace(
        id=uuid4(),
        definition_id=uuid4(),
        version_no=4,
        status="published",
        created_by="designer-1",
        published_by="dev-user",
        created_at=datetime.utcnow(),
        published_at=datetime.utcnow(),
        notes=None,
    )

    response = authorized_client.post(
        f"/api/v1/agent-definitions/{uuid4()}/flow/publish",
        json={"expected_version_no": 3},
    )

    assert response.status_code == 200
    assert fake_service.publish_calls[0]["expected_version_no"] == 3


# ---------------------------------------------------------------------------
# POST rollback
# ---------------------------------------------------------------------------


def test_rollback_returns_200_with_restored_version(authorized_client, fake_service):
    fake_service.rollback_result = SimpleNamespace(
        id=uuid4(),
        definition_id=uuid4(),
        version_no=3,
        status="published",
        created_by="designer-1",
        published_by="dev-user",
        created_at=datetime.utcnow(),
        published_at=datetime.utcnow(),
        notes="Rolled back to version 1",
    )

    response = authorized_client.post(
        f"/api/v1/agent-definitions/{uuid4()}/flow/rollback",
        json={"target_version_no": 1},
    )

    assert response.status_code == 200
    assert response.json()["version_no"] == 3
    assert fake_service.rollback_calls[0]["target_version_no"] == 1
    assert fake_service.rollback_calls[0]["published_by"] == "dev-user"


def test_rollback_returns_400_when_target_version_no_missing(authorized_client, fake_service):
    response = authorized_client.post(f"/api/v1/agent-definitions/{uuid4()}/flow/rollback", json={})

    assert response.status_code == 400


def test_rollback_returns_409_on_conflict(authorized_client, fake_service):
    fake_service.rollback_error = FlowVersionConflictError("No version 99 exists")

    response = authorized_client.post(
        f"/api/v1/agent-definitions/{uuid4()}/flow/rollback",
        json={"target_version_no": 99},
    )

    assert response.status_code == 409


def test_rollback_requires_authentication(auth_enforced):
    response = IdempotentTestClient(app).post(
        f"/api/v1/agent-definitions/{uuid4()}/flow/rollback", json={"target_version_no": 1}
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Audit events (P3 Task 19)
# ---------------------------------------------------------------------------


def test_save_draft_emits_flow_updated(authorized_client, fake_service, fake_audit_emitter):
    definition_id = uuid4()

    authorized_client.put(
        f"/api/v1/agent-definitions/{definition_id}/flow/draft",
        json={"flow_spec": _valid_flow_dict()},
    )

    assert fake_audit_emitter.emitted[0]["action"] == "flow:updated"
    assert fake_audit_emitter.emitted[0]["definition_id"] == definition_id


def test_publish_emits_flow_published_with_from_and_to_version(
    authorized_client, fake_service, fake_audit_emitter
):
    fake_service.versions = [
        SimpleNamespace(id=uuid4(), version_no=2, status="published"),
        SimpleNamespace(id=uuid4(), version_no=1, status="archived"),
    ]
    fake_service.publish_result = SimpleNamespace(
        id=uuid4(),
        definition_id=uuid4(),
        version_no=3,
        status="published",
        created_by="designer-1",
        published_by="dev-user",
        created_at=datetime.utcnow(),
        published_at=datetime.utcnow(),
        notes=None,
    )
    definition_id = uuid4()

    authorized_client.post(f"/api/v1/agent-definitions/{definition_id}/flow/publish")

    event = fake_audit_emitter.emitted[0]
    assert event["action"] == "flow:published"
    assert event["definition_id"] == definition_id
    assert event["details"] == {"from_version": 2, "to_version": 3}


def test_publish_emits_from_version_none_for_first_ever_publish(
    authorized_client, fake_service, fake_audit_emitter
):
    fake_service.versions = []  # nothing published yet
    fake_service.publish_result = SimpleNamespace(
        id=uuid4(),
        definition_id=uuid4(),
        version_no=1,
        status="published",
        created_by="designer-1",
        published_by="dev-user",
        created_at=datetime.utcnow(),
        published_at=datetime.utcnow(),
        notes=None,
    )

    authorized_client.post(f"/api/v1/agent-definitions/{uuid4()}/flow/publish")

    assert fake_audit_emitter.emitted[0]["details"] == {"from_version": None, "to_version": 1}


def test_publish_does_not_emit_on_failure(authorized_client, fake_service, fake_audit_emitter):
    fake_service.publish_error = FlowVersionConflictError("No draft exists")

    authorized_client.post(f"/api/v1/agent-definitions/{uuid4()}/flow/publish")

    assert fake_audit_emitter.emitted == []


def test_rollback_emits_flow_rolled_back_with_restored_from_version(
    authorized_client, fake_service, fake_audit_emitter
):
    fake_service.rollback_result = SimpleNamespace(
        id=uuid4(),
        definition_id=uuid4(),
        version_no=3,
        status="published",
        created_by="designer-1",
        published_by="dev-user",
        created_at=datetime.utcnow(),
        published_at=datetime.utcnow(),
        notes="Rolled back to version 1",
    )
    definition_id = uuid4()

    authorized_client.post(
        f"/api/v1/agent-definitions/{definition_id}/flow/rollback",
        json={"target_version_no": 1},
    )

    event = fake_audit_emitter.emitted[0]
    assert event["action"] == "flow:rolled_back"
    assert event["definition_id"] == definition_id
    assert event["details"] == {"restored_from_version": 1}


def test_rollback_does_not_emit_on_failure(authorized_client, fake_service, fake_audit_emitter):
    fake_service.rollback_error = FlowVersionConflictError("No version 99 exists")

    authorized_client.post(
        f"/api/v1/agent-definitions/{uuid4()}/flow/rollback",
        json={"target_version_no": 99},
    )

    assert fake_audit_emitter.emitted == []


# ---------------------------------------------------------------------------
# GET version detail (Task 45 — powers the canvas version preview + export)
# ---------------------------------------------------------------------------


def _version_row(version_no: int = 2, status: str = "published"):
    return SimpleNamespace(
        id=uuid4(),
        definition_id=None,
        version_no=version_no,
        status=status,
        created_by="user-1",
        published_by="user-1" if status == "published" else None,
        created_at=datetime.utcnow(),
        published_at=datetime.utcnow() if status == "published" else None,
        notes=None,
        flow_spec=_valid_flow_dict(),
    )


def test_get_version_detail_returns_metadata_and_spec(authorized_client, fake_service):
    fake_service.version_detail = _version_row(version_no=3)

    response = authorized_client.get(f"/api/v1/agent-definitions/{uuid4()}/flow/versions/3")

    assert response.status_code == 200
    body = response.json()
    assert body["version_no"] == 3
    assert body["status"] == "published"
    assert body["flow_spec"] == _valid_flow_dict()


def test_get_version_detail_returns_404_for_unknown_version(authorized_client, fake_service):
    fake_service.version_detail = None

    response = authorized_client.get(f"/api/v1/agent-definitions/{uuid4()}/flow/versions/99")

    assert response.status_code == 404


def test_get_version_detail_requires_authentication(auth_enforced):
    response = IdempotentTestClient(app).get(f"/api/v1/agent-definitions/{uuid4()}/flow/versions/1")

    assert response.status_code == 401

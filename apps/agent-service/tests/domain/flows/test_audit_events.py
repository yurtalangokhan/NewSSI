"""Tests for FlowAuditEmitter — flow lifecycle audit events (design spec
9.2, P3 Task 19, option B: emits to user-service's audit_logs table via a
new internal endpoint, since agent-service has no audit infra of its own).

Never raises into the caller: an audit failure must not fail a publish,
rollback, or draft save.

Brief: .tmp/flow-canvas-task-19-brief.md
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.flows.audit import FlowAuditEmitter
from service.AuthService import AuthenticatedUser


def _user(claims: dict | None = None, user_id: str = "keycloak-sub-123") -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id, email="u@local.dev", claims=claims or {}, access_token="tok"
    )


# ---------------------------------------------------------------------------
# 19.1 — identity resolution: real UUID wins, else raw identity in details
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_uses_resolved_user_service_id_when_available(monkeypatch):
    captured = {}

    async def fake_create_audit_log(action, resource, *, user_id, details, access_token):
        captured.update(
            action=action,
            resource=resource,
            user_id=user_id,
            details=details,
            access_token=access_token,
        )

    import service.UserServiceClient as client_module

    monkeypatch.setattr(client_module, "create_audit_log", fake_create_audit_log)

    emitter = FlowAuditEmitter()
    user = _user(claims={"user_service_user": {"id": "real-uuid-1"}})
    definition_id = uuid4()

    await emitter.emit("flow:published", definition_id, user=user, details={"to_version": 2})

    assert captured["user_id"] == "real-uuid-1"
    assert captured["resource"] == f"flow:{definition_id}"
    assert "actor_identity" not in captured["details"]


@pytest.mark.asyncio
async def test_emit_falls_back_to_raw_identity_when_no_real_id(monkeypatch):
    captured = {}

    async def fake_create_audit_log(action, resource, *, user_id, details, access_token):
        captured.update(user_id=user_id, details=details)

    import service.UserServiceClient as client_module

    monkeypatch.setattr(client_module, "create_audit_log", fake_create_audit_log)

    emitter = FlowAuditEmitter()
    user = _user(claims={}, user_id="dev-user")

    await emitter.emit("flow:published", uuid4(), user=user, details={})

    assert captured["user_id"] is None
    assert captured["details"]["actor_identity"] == "dev-user"


# ---------------------------------------------------------------------------
# 19.4 — audit failure never breaks the caller
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_failure_does_not_raise(monkeypatch):
    async def failing_create_audit_log(*args, **kwargs):
        raise RuntimeError("user-service is down")

    import service.UserServiceClient as client_module

    monkeypatch.setattr(client_module, "create_audit_log", failing_create_audit_log)

    emitter = FlowAuditEmitter()

    await emitter.emit("flow:published", uuid4(), user=_user(), details={})  # must not raise


# ---------------------------------------------------------------------------
# Draft-update coalescing
# ---------------------------------------------------------------------------


def test_should_emit_draft_update_coalesces_rapid_saves():
    emitter = FlowAuditEmitter()
    definition_id = "def-1"

    assert emitter.should_emit_draft_update(definition_id) is True
    assert emitter.should_emit_draft_update(definition_id) is False  # too soon


def test_should_emit_draft_update_is_independent_per_definition():
    emitter = FlowAuditEmitter()

    assert emitter.should_emit_draft_update("def-a") is True
    assert emitter.should_emit_draft_update("def-b") is True


def test_should_emit_draft_update_allows_after_interval_elapses(monkeypatch):
    import domain.flows.audit as audit_module

    emitter = FlowAuditEmitter()
    definition_id = "def-1"
    clock = {"now": 1000.0}
    monkeypatch.setattr(audit_module.time, "monotonic", lambda: clock["now"])

    assert emitter.should_emit_draft_update(definition_id) is True
    clock["now"] += audit_module.DRAFT_UPDATE_COALESCE_SECONDS + 1
    assert emitter.should_emit_draft_update(definition_id) is True

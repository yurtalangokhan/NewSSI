"""Tests for the internal audit-log write endpoint (P3 Task 19, option B).

Lets agent-service (which has no audit infra of its own) write flow
lifecycle events into user-service's existing audit_logs table.

Brief: .tmp/flow-canvas-task-19-brief.md
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from src.api.dependencies import require_auth_or_internal_service_token
from src.controller.audit_controller import AuditController
from src.schema.audit import AuditLogRequest
from src.main import create_app
from src.service import audit_service as audit_service_module


def _authorized_client(app):
    app.dependency_overrides[require_auth_or_internal_service_token] = lambda: "caller"
    return TestClient(app)


# ---------------------------------------------------------------------------
# AuditController — the FK-safety logic (actor ids are external references)
# ---------------------------------------------------------------------------


async def _logged_call(monkeypatch, user_id):
    fake_service = AsyncMock()
    fake_service.log.return_value = {"id": "log-x"}
    monkeypatch.setattr(audit_service_module, "_audit_service", fake_service)
    request = AuditLogRequest(action="flow:published", resource="flow:abc", user_id=user_id)
    await AuditController().create_log(request)
    return fake_service.log.call_args.kwargs


async def test_controller_accepts_a_real_uuid(monkeypatch):
    real_id = str(uuid.uuid4())

    kwargs = await _logged_call(monkeypatch, real_id)

    assert str(kwargs["user_id"]) == real_id
    assert kwargs["details"] == {}


async def test_controller_falls_back_for_non_uuid_identifiers(monkeypatch):
    kwargs = await _logged_call(monkeypatch, "dev-user")

    assert kwargs["user_id"] is None
    assert kwargs["details"]["actor_identity"] == "dev-user"


async def test_controller_handles_missing_identifier(monkeypatch):
    kwargs = await _logged_call(monkeypatch, None)

    assert kwargs["user_id"] is None
    assert kwargs["details"] == {}


# ---------------------------------------------------------------------------
# The route itself
# ---------------------------------------------------------------------------


def test_create_audit_log_requires_authentication():
    response = TestClient(create_app()).post(
        "/api/v1/internal/audit-logs",
        json={"action": "flow:published", "resource": "flow:abc"},
    )

    assert response.status_code == 401


def test_create_audit_log_forwards_to_audit_service(monkeypatch):
    fake_service = AsyncMock()
    fake_service.log.return_value = {"id": "log-1", "action": "flow:published"}
    monkeypatch.setattr(audit_service_module, "_audit_service", fake_service)

    app = create_app()
    client = _authorized_client(app)

    real_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/internal/audit-logs",
        json={
            "action": "flow:published",
            "resource": f"flow:{uuid.uuid4()}",
            "user_id": real_id,
            "details": {"from_version": 1, "to_version": 2},
        },
    )

    assert response.status_code == 200
    fake_service.log.assert_awaited_once()
    call_kwargs = fake_service.log.call_args.kwargs
    assert str(call_kwargs["user_id"]) == real_id
    assert call_kwargs["details"] == {"from_version": 1, "to_version": 2}


def test_create_audit_log_records_raw_identity_for_non_uuid_user(monkeypatch):
    fake_service = AsyncMock()
    fake_service.log.return_value = {"id": "log-2"}
    monkeypatch.setattr(audit_service_module, "_audit_service", fake_service)

    app = create_app()
    client = _authorized_client(app)

    response = client.post(
        "/api/v1/internal/audit-logs",
        json={
            "action": "flow:published",
            "resource": f"flow:{uuid.uuid4()}",
            "user_id": "dev-user",
        },
    )

    assert response.status_code == 200
    call_kwargs = fake_service.log.call_args.kwargs
    assert call_kwargs["user_id"] is None
    assert call_kwargs["details"]["actor_identity"] == "dev-user"

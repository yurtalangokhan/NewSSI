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
from src.api.routes.audit_route import _resolve_user_id
from src.main import create_app
from src.service import audit_service as audit_service_module


def _authorized_client(app):
    app.dependency_overrides[require_auth_or_internal_service_token] = lambda: "caller"
    return TestClient(app)


# ---------------------------------------------------------------------------
# _resolve_user_id — the FK-safety logic
# ---------------------------------------------------------------------------


def test_resolve_user_id_accepts_a_real_uuid():
    real_id = str(uuid.uuid4())
    details: dict = {}

    resolved = _resolve_user_id(real_id, details)

    assert str(resolved) == real_id
    assert details == {}


def test_resolve_user_id_falls_back_for_non_uuid_identifiers():
    details: dict = {}

    resolved = _resolve_user_id("dev-user", details)

    assert resolved is None
    assert details["actor_identity"] == "dev-user"


def test_resolve_user_id_handles_missing_identifier():
    details: dict = {}

    resolved = _resolve_user_id(None, details)

    assert resolved is None
    assert details == {}


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

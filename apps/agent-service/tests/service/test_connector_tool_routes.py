import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

ID = "e22ef0bf-3c16-4591-a254-7c48cb16fc55"


def test_secret_resolution_is_never_cached_by_idempotency():
    from core.http.idempotency import build_idempotency_exclude_paths

    excluded = build_idempotency_exclude_paths()
    assert "/internal/connector-tools/resolve" in excluded
    assert "/api/v1/internal/connector-tools/resolve" in excluded


def client():
    from api.routes.connector_tools_route import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_resolver_requires_internal_token_even_with_user_header(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-token")
    response = client().post(
        "/internal/connector-tools/resolve",
        headers={"x-user-id": "user-1"},
        json={"persona_id": 5, "datasource_id": ID, "operation": "read"},
    )
    assert response.status_code == 403


def test_resolver_requires_forwarded_identity(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-token")
    response = client().post(
        "/internal/connector-tools/resolve",
        headers={"X-Internal-Service-Token": "test-token"},
        json={"persona_id": 5, "datasource_id": ID, "operation": "read"},
    )
    assert response.status_code == 403


def test_resolution_has_a_total_timeout_and_no_replayable_response(monkeypatch):
    async def slow_resolve(*args):
        await asyncio.sleep(0.1)
        return {"config": {"password": "never-returned-secret"}}

    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-token")
    with (
        patch("api.routes.connector_tools_route.RESOLUTION_TIMEOUT_SECONDS", 0.001, create=True),
        patch(
            "api.routes.connector_tools_route.get_connector_tool_service",
            return_value=SimpleNamespace(resolve=slow_resolve),
        ),
    ):
        response = client().post(
            "/internal/connector-tools/resolve",
            headers={
                "X-Internal-Service-Token": "test-token",
                "x-user-id": "user-1",
            },
            json={"persona_id": 5, "datasource_id": ID, "operation": "read"},
        )
    assert response.status_code == 504
    assert "never-returned-secret" not in response.text


@pytest.mark.asyncio
async def test_service_checks_agent_access_before_resolving_credentials():
    from service.orchestration.connector_tool_service import ConnectorToolService
    from service.personas.persona_access import PersonaAccessPolicy

    access_policy = SimpleNamespace(
        load_visibility=AsyncMock(return_value=({5}, set())),
        can_manage_all=AsyncMock(return_value=False),
        can_access=PersonaAccessPolicy().can_access,
    )
    svc = SimpleNamespace(resolve=AsyncMock())
    service = ConnectorToolService(svc, access_policy)
    with patch(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        new=AsyncMock(
            return_value={
                "id": 5,
                "user_id": "owner",
                "is_public": True,
            }
        ),
    ):
        with pytest.raises(Exception) as error:
            await service.resolve(5, ID, "read", "stranger")
    assert error.value.status_code == 403
    svc.resolve.assert_not_awaited()

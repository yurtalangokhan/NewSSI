import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ID = "e22ef0bf-3c16-4591-a254-7c48cb16fc55"


def test_secret_resolution_is_never_cached_by_idempotency():
    from core.idempotency import build_idempotency_exclude_paths

    excluded = build_idempotency_exclude_paths()
    assert "/internal/connector-tools/resolve" in excluded
    assert "/api/v1/internal/connector-tools/resolve" in excluded


def client():
    from api.routes.ConnectorToolsRoute import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_resolver_requires_internal_token_even_with_user_header():
    with patch(
        "api.routes.ConnectorToolsRoute.settings",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="test-token"),
    ):
        response = client().post(
            "/internal/connector-tools/resolve",
            headers={"x-user-id": "user-1"},
            json={"persona_id": 5, "datasource_id": ID, "operation": "read"},
        )
    assert response.status_code == 403


def test_resolver_requires_forwarded_identity():
    with patch(
        "api.routes.ConnectorToolsRoute.settings",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="test-token"),
    ):
        response = client().post(
            "/internal/connector-tools/resolve",
            headers={"X-Internal-Service-Token": "test-token"},
            json={"persona_id": 5, "datasource_id": ID, "operation": "read"},
        )
    assert response.status_code == 403


def test_resolution_has_a_total_timeout_and_no_replayable_response():
    async def slow_resolve(*args):
        await asyncio.sleep(0.1)
        return {"config": {"password": "never-returned-secret"}}

    with (
        patch(
            "api.routes.ConnectorToolsRoute.settings",
            SimpleNamespace(INTERNAL_SERVICE_TOKEN="test-token"),
        ),
        patch("api.routes.ConnectorToolsRoute.RESOLUTION_TIMEOUT_SECONDS", 0.001, create=True),
        patch(
            "api.routes.ConnectorToolsRoute.get_connector_tool_controller",
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
async def test_controller_checks_agent_access_before_resolving_credentials():
    from controller.connector_tool_controller import ConnectorToolController

    personas = SimpleNamespace(
        _load_agent_group_visibility=AsyncMock(return_value=({5}, set())),
        _can_manage_all_personas=AsyncMock(return_value=False),
    )
    from controller.persona_controller import PersonaController

    personas._can_access_persona = PersonaController()._can_access_persona
    svc = SimpleNamespace(resolve=AsyncMock())
    controller = ConnectorToolController(svc, personas)
    with patch(
        "controller.connector_tool_controller.PersonaDB.get",
        new=AsyncMock(
            return_value={
                "id": 5,
                "user_id": "owner",
                "is_public": True,
            }
        ),
    ):
        with pytest.raises(Exception) as error:
            await controller.resolve(5, ID, "read", "stranger")
    assert error.value.status_code == 403
    svc.resolve.assert_not_awaited()

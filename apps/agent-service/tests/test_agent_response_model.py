from unittest.mock import AsyncMock

import pytest
from error_contract import AgentNotFoundError
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from localization import LocalizationMiddleware

from api.routes import agents_route
from service.personas.persona_service import PersonaService


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(LocalizationMiddleware)
    paths = {"/agents/catalog", "/agents/{agent_id}", "/agents/composition/catalog"}
    for route in agents_route.router.routes:
        if isinstance(route, APIRoute) and route.path in paths:
            for dependency in route.dependant.dependencies:
                app.dependency_overrides[dependency.call] = lambda: object()
    app.include_router(agents_route.router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "locale,message", [("en", "Agent not found."), ("tr", "Ajan bulunamadı.")]
)
def test_detail_error_reaches_response_model(
    monkeypatch, client, locale, message
):
    service = AsyncMock()
    service.get_agent_detail.side_effect = AgentNotFoundError()
    monkeypatch.setattr(agents_route, "get_persona_service", lambda: service)

    result = client.get("/agents/missing", headers={"X-Language": locale})
    assert result.status_code == 404
    assert result.json() == {
        "statusCode": 404,
        "message": message,
        "data": None,
        "error": {"code": "agent.not_found", "message": message, "details": None},
    }
    service.get_agent_detail.assert_awaited_once()


@pytest.mark.parametrize(
    "path", ["/agents/catalog", "/agents/composition/catalog", "/agents/42"]
)
def test_catalog_success_returns_data_inside_response_model(monkeypatch, client, path):
    service = AsyncMock()
    service.get_agent_catalog.return_value = []
    detail = {
        "id": 42, "name": "Example", "description": None,
        "tools": [], "capabilities": {}, "availability": None,
    }
    service.get_agent_detail.return_value = detail
    monkeypatch.setattr(agents_route, "get_persona_service", lambda: service)
    composition = {"components": [], "kinds": []}
    monkeypatch.setattr(agents_route, "get_composition_catalog", lambda kind: composition)

    result = client.get(path)
    assert result.status_code == 200
    expected_data = {
        "/agents/catalog": [],
        "/agents/composition/catalog": composition,
        "/agents/42": detail,
    }
    assert result.json() == {
        "statusCode": 200,
        "message": None,
        "data": expected_data[path],
        "error": None,
    }


@pytest.mark.asyncio
async def test_invalid_agent_identifier_raises_keyed_error():
    with pytest.raises(AgentNotFoundError) as error:
        await PersonaService().get_agent_detail("missing")
    assert error.value.message_key == "errors.agent.not_found"
    assert error.value.status_code == 404

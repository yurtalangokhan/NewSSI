"""Tests for shared organization layout API routes."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import organizations_route


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Create an organization router app with permission checks bypassed."""
    app = FastAPI()
    app.include_router(organizations_route.router)
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant:
            for dependency in dependant.dependencies:
                app.dependency_overrides[dependency.call] = lambda: str(uuid.uuid4())

    controller = MagicMock()
    controller.get_layout = AsyncMock(
        return_value={
            "positions": [
                {"organization_id": "00000000-0000-0000-0000-000000000001", "x": 1.0, "y": 2.0}
            ],
            "writable_organization_ids": ["00000000-0000-0000-0000-000000000001"],
        }
    )
    async def save_layout(_actor_id: uuid.UUID, positions: list[dict]) -> dict:
        return {"positions": positions, "count": len(positions)}

    controller.save_layout = AsyncMock(side_effect=save_layout)
    monkeypatch.setattr(
        organizations_route,
        "get_organization_layout_controller",
        lambda: controller,
        raising=False,
    )
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a test client for the router app."""
    return TestClient(app)


def test_layout_routes_are_registered_before_dynamic_organization_routes(app: FastAPI) -> None:
    """Static layout paths must win before the generic organization ID path."""
    paths = [route.path for route in app.routes]

    assert paths.index("/organizations/layout") < paths.index("/organizations/{org_id}")


def test_get_layout_returns_shared_positions_and_writable_ids_in_stable_order(
    client: TestClient,
) -> None:
    """Read endpoint returns the shared layout contract."""
    response = client.get("/organizations/layout")

    assert response.status_code == 200
    assert response.json() == {
        "positions": [
            {"organization_id": "00000000-0000-0000-0000-000000000001", "x": 1.0, "y": 2.0}
        ],
        "writable_organization_ids": ["00000000-0000-0000-0000-000000000001"],
    }


def test_put_layout_accepts_empty_positions_as_a_successful_no_op(client: TestClient) -> None:
    """Empty saves are successful and don't require a special client path."""
    response = client.put("/organizations/layout", json={"positions": []})

    assert response.status_code == 200
    assert response.json() == {"positions": [], "count": 0}


@pytest.mark.parametrize(
    "payload",
    [
        {"positions": [{"organization_id": str(uuid.uuid4()), "x": "Infinity", "y": 0.0}]},
        {"positions": [{"organization_id": str(uuid.uuid4()), "x": 100_000_000.1, "y": 0.0}]},
        {"positions": [{"organization_id": str(uuid.uuid4()), "x": 0.0, "y": -100_000_000.1}]},
        {"positions": [{"organization_id": str(uuid.uuid4()), "x": 0.0, "y": 0.0}] * 100_001},
    ],
)
def test_put_layout_rejects_invalid_coordinate_batches(client: TestClient, payload: dict) -> None:
    """Pydantic enforces finite bounded coordinates and the batch limit."""
    response = client.put("/organizations/layout", json=payload)

    assert response.status_code == 422

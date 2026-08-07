import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.dependencies import require_auth_or_internal_service_token
from src.api.routes import user_route
from src.schema.users import InternalUserBatchRequest
from src.service.user_service import UserService


def _user(user_id: uuid.UUID, email: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        email=email,
        username=email.split("@", 1)[0],
        first_name="Test",
        last_name="User",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        role="enduser",
        invited=False,
        password_configured=False,
        is_external_keycloak_user=False,
        groups=[],
        team_name=None,
        keycloak_id=None,
        created_at=datetime(2026, 8, 5),
        updated_at=datetime(2026, 8, 5),
    )


def test_batch_request_rejects_more_than_100_user_ids() -> None:
    with pytest.raises(ValidationError):
        InternalUserBatchRequest(user_ids=[uuid.uuid4() for _ in range(101)])


def test_batch_request_rejects_duplicate_user_ids() -> None:
    user_id = uuid.uuid4()

    with pytest.raises(ValidationError):
        InternalUserBatchRequest(user_ids=[user_id, user_id])


@pytest.mark.asyncio
async def test_get_users_by_ids_serializes_matches_from_one_repository_call() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    users = [_user(first_id, "first@example.com"), _user(second_id, "second@example.com")]
    service = UserService()
    service.user_repo = SimpleNamespace(get_by_ids=AsyncMock(return_value=users))

    result = await service.get_users_by_ids([first_id, second_id])

    assert [(item["id"], item["email"]) for item in result] == [
        (str(first_id), "first@example.com"),
        (str(second_id), "second@example.com"),
    ]
    service.user_repo.get_by_ids.assert_awaited_once_with([first_id, second_id])


def test_batch_route_requires_internal_auth_and_returns_matching_users(monkeypatch) -> None:
    user_id = uuid.uuid4()
    controller = SimpleNamespace(
        get_users_by_ids=AsyncMock(return_value=[{"id": str(user_id), "email": "user@example.com"}])
    )
    monkeypatch.setattr(user_route, "get_user_controller", lambda: controller)

    app = FastAPI()
    app.dependency_overrides[require_auth_or_internal_service_token] = lambda: "internal-service"
    app.include_router(user_route.internal_router)

    response = TestClient(app).post("/internal/users/batch", json={"user_ids": [str(user_id)]})

    assert response.status_code == 200
    assert response.json() == [{"id": str(user_id), "email": "user@example.com"}]
    controller.get_users_by_ids.assert_awaited_once_with([user_id])
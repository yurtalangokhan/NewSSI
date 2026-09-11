from types import SimpleNamespace

import pytest
from starlette.requests import Request

from controller.persona_controller import PersonaController
from service.AuthService import AuthenticatedUser


@pytest.mark.asyncio
async def test_resolve_persona_owner_id_uses_local_user_service_id(monkeypatch) -> None:
    controller = PersonaController()
    keycloak_id = "11111111-1111-4111-8111-111111111111"
    local_user_id = "22222222-2222-4222-8222-222222222222"
    user = AuthenticatedUser(
        user_id=keycloak_id,
        email="owner@example.com",
        roles=["admin"],
        claims={"sub": keycloak_id},
        access_token="token",
    )
    request = Request({"type": "http", "headers": []})

    async def resolve_user_identity(*, token, user_id, user):
        assert user_id == keycloak_id
        return {"primary_user_id": local_user_id}

    auth_service = SimpleNamespace(resolve_user_identity=resolve_user_identity)
    monkeypatch.setattr("controller.persona_controller.get_auth_service", lambda: auth_service)

    assert await controller.resolve_owner_user_id(request, user) == local_user_id


@pytest.mark.asyncio
async def test_resolve_persona_owner_id_falls_back_to_authenticated_id(monkeypatch) -> None:
    controller = PersonaController()
    user = AuthenticatedUser(
        user_id="dev-user",
        email="dev@local.dev",
        roles=["admin"],
    )
    request = Request({"type": "http", "headers": []})

    async def resolve_user_identity(*, token, user_id, user):
        return {"primary_user_id": None}

    auth_service = SimpleNamespace(resolve_user_identity=resolve_user_identity)
    monkeypatch.setattr("controller.persona_controller.get_auth_service", lambda: auth_service)

    assert await controller.resolve_owner_user_id(request, user) == "dev-user"

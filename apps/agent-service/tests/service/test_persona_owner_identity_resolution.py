from types import SimpleNamespace

import pytest

from service.auth.auth_service import AuthenticatedUser
from service.personas.persona_service import PersonaService


@pytest.mark.asyncio
async def test_resolve_persona_owner_id_uses_local_user_service_id(monkeypatch) -> None:
    service = PersonaService()
    keycloak_id = "11111111-1111-4111-8111-111111111111"
    local_user_id = "22222222-2222-4222-8222-222222222222"
    user = AuthenticatedUser(
        user_id=keycloak_id,
        email="owner@example.com",
        roles=["admin"],
        claims={"sub": keycloak_id},
        access_token="token",
    )

    async def resolve_user_identity(*, token, user_id, user):
        assert user_id == keycloak_id
        return {"primary_user_id": local_user_id}

    auth_service = SimpleNamespace(resolve_user_identity=resolve_user_identity)
    monkeypatch.setattr("service.personas.persona_service.get_auth_service", lambda: auth_service)

    assert await service.resolve_owner_user_id("token", user) == local_user_id


@pytest.mark.asyncio
async def test_resolve_persona_owner_id_falls_back_to_authenticated_id(monkeypatch) -> None:
    service = PersonaService()
    user = AuthenticatedUser(
        user_id="dev-user",
        email="dev@local.dev",
        roles=["admin"],
    )

    async def resolve_user_identity(*, token, user_id, user):
        return {"primary_user_id": None}

    auth_service = SimpleNamespace(resolve_user_identity=resolve_user_identity)
    monkeypatch.setattr("service.personas.persona_service.get_auth_service", lambda: auth_service)

    assert await service.resolve_owner_user_id("token", user) == "dev-user"

import pytest
from fastapi import HTTPException

from api.routes.ChatRoute import _resolve_effective_chat_user_id
from service.AuthService import AuthenticatedUser, AuthService, get_primary_user_id


def test_get_primary_user_id_prefers_identity_primary() -> None:
    identity = {"primary_user_id": "internal-user", "known_user_ids": ["internal-user", "kc-sub"]}

    assert get_primary_user_id(identity, "kc-sub") == "internal-user"


def test_resolve_effective_chat_user_id_uses_primary_user_id() -> None:
    identity = {"primary_user_id": "internal-user", "known_user_ids": ["internal-user", "kc-sub"]}

    assert _resolve_effective_chat_user_id(identity, "kc-sub") == "internal-user"


def test_resolve_effective_chat_user_id_raises_without_any_user_id() -> None:
    with pytest.raises(HTTPException):
        _resolve_effective_chat_user_id({}, None)


@pytest.mark.asyncio
async def test_resolve_user_identity_fetches_local_user_when_keycloak_sub_matches_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keycloak_id = "6b2d0c3f-7a6c-4d30-a61b-b5efe840c6e4"
    local_user_id = "f8263659-f37c-4bb1-946f-cb50e9f9cfb1"
    token = "keycloak-access-token"

    monkeypatch.setattr(AuthService, "is_keycloak_enabled", staticmethod(lambda: True))
    monkeypatch.setattr(
        AuthService,
        "decode_keycloak_token",
        staticmethod(lambda _token: {"sub": keycloak_id}),
    )

    async def fake_get_user_by_keycloak_id(resolved_keycloak_id: str, access_token: str | None):
        assert resolved_keycloak_id == keycloak_id
        assert access_token == token
        return {"id": local_user_id, "keycloak_id": keycloak_id, "email": "demo@demo.com"}

    monkeypatch.setattr(
        "service.UserServiceClient.get_user_by_keycloak_id",
        fake_get_user_by_keycloak_id,
    )

    identity = await AuthService().resolve_user_identity(
        token=token,
        user_id=keycloak_id,
        user=AuthenticatedUser(
            user_id=keycloak_id,
            email="demo@demo.com",
            claims={"sub": keycloak_id},
            access_token=token,
        ),
    )

    assert identity["primary_user_id"] == local_user_id
    assert identity["known_user_ids"] == [local_user_id, keycloak_id]

from types import SimpleNamespace, TracebackType
from typing import Self

import pytest
from fastapi import HTTPException
from i18n.core import set_locale

from langconnect import auth


def _request(
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    host: str = "127.0.0.1",
):
    return SimpleNamespace(
        headers=headers or {},
        cookies=cookies or {},
        client=SimpleNamespace(host=host),
    )


def _credentials(token: str):
    return SimpleNamespace(scheme="Bearer", credentials=token)


@pytest.fixture(autouse=True)
def clear_auth_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "VALID_API_KEYS", set())


async def _unresolved_user(_token: str) -> None:
    return None


def test_verify_api_key_uses_bearer_identity_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", False)
    assert auth.verify_api_key("user1") == "user1"
    assert auth.verify_api_key("api-key:user2") == "user2"


def test_claim_permissions_supports_permissions_claim_and_client_roles(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth.config, "KEYCLOAK_CLIENT_ID", "agenticai-web")

    assert auth._claims_have_permission(
        {"permissions": ["collection:create"]},
        "collection:create",
    )
    assert auth._claims_have_permission(
        {"resource_access": {"agenticai-web": {"roles": ["document:read"]}}},
        "document:read",
    )
    assert auth._claims_have_permission(
        {"realm_access": {"roles": ["*"]}},
        "graph:read",
    )


async def test_resolve_user_requires_credentials_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        await auth.resolve_user(_request(), None)

    assert exc.value.status_code == 401


async def test_resolve_user_does_not_trust_localhost_without_flag(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", False)
    monkeypatch.setattr(auth, "VALID_API_KEYS", {"expected-key"})

    with pytest.raises(HTTPException) as exc:
        await auth.resolve_user(
            _request(headers={"User-Agent": "python-httpx/0.28.1"}),
            None,
        )

    assert exc.value.status_code == 403


async def test_resolve_user_accepts_internal_service_token(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "internal-token")
    user = await auth.resolve_user(
        _request(headers={"X-Internal-Service-Token": "internal-token"}),
        None,
    )
    assert user is not None
    assert user.identity == "internal-service"


async def test_resolve_user_uses_bearer_identity_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(auth, "_get_user_service_user", _unresolved_user)
    user = await auth.resolve_user(_request(), _credentials("user-123"))
    assert user is not None
    assert user.identity == "user-123"
    assert user.access_token == "user-123"


async def test_resolve_user_uses_access_token_cookie_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(auth, "_get_user_service_user", _unresolved_user)
    user = await auth.resolve_user(
        _request(cookies={"access_token": "cookie-user"}),
        None,
    )
    assert user is not None
    assert user.identity == "cookie-user"
    assert user.access_token == "cookie-user"


async def test_resolve_user_falls_back_to_local_keycloak_validation(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ISSUER_URL", "https://issuer")

    def _decode_token(token: str):
        assert token == "jwt-token"
        return {"sub": "keycloak-sub", "email": "demo@example.com"}

    async def _get_user(token: str) -> None:
        assert token == "jwt-token"

    monkeypatch.setattr(auth, "decode_keycloak_token", _decode_token)
    monkeypatch.setattr(auth, "_get_user_service_user", _get_user)

    user = await auth.resolve_user(_request(), _credentials("jwt-token"))

    assert user is not None
    assert user.identity == "keycloak-sub"
    assert user.display_name == "demo@example.com"
    assert user.access_token == "jwt-token"


def test_decode_keycloak_token_translates_invalid_token_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth.config, "KEYCLOAK_ISSUER_URL", "https://issuer")

    class _FakeJWKSClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def get_signing_key_from_jwt(self, token):
            raise auth.InvalidTokenError("Signature verification failed")

    monkeypatch.setattr(auth, "PyJWKClient", _FakeJWKSClient)

    with pytest.raises(HTTPException) as exc:
        auth.decode_keycloak_token("bad-token")

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid bearer token: Signature verification failed"


def test_decode_keycloak_token_error_is_translated_for_turkish_locale(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth.config, "KEYCLOAK_ISSUER_URL", "https://issuer")

    class _FakeJWKSClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def get_signing_key_from_jwt(self, token):
            raise auth.InvalidTokenError("Signature verification failed")

    monkeypatch.setattr(auth, "PyJWKClient", _FakeJWKSClient)

    set_locale("tr")
    try:
        with pytest.raises(HTTPException) as exc:
            auth.decode_keycloak_token("bad-token")
    finally:
        set_locale("en")

    assert exc.value.detail == "Geçersiz taşıyıcı token: Signature verification failed"


async def test_require_permission_translates_missing_permission_detail(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", False)

    async def _deny_permission(self, user_id, permission, access_token=None):
        return False

    monkeypatch.setattr(
        "langconnect.authorization.AuthorizationClient.has_permission", _deny_permission
    )

    check = auth.require_permission("collection:create")
    with pytest.raises(HTTPException) as exc:
        await check(_request(), _credentials("some-user"))

    assert exc.value.status_code == 403
    assert exc.value.detail == "Missing required permission: collection:create"


async def test_resolve_user_uses_user_service_before_local_jwt_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User-service is authoritative for bearer-token identity."""
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ISSUER_URL", "https://internal-issuer")

    async def _get_user(token: str) -> dict[str, str]:
        assert token == "external-jwt"
        return {"id": "local-user-id", "email": "external@example.com"}

    def _unexpected_local_decode(_token: str) -> dict[str, str]:
        raise AssertionError("local JWT validation must not run first")

    monkeypatch.setattr(auth, "_get_user_service_user", _get_user)
    monkeypatch.setattr(auth, "decode_keycloak_token", _unexpected_local_decode)

    user = await auth.resolve_user(_request(), _credentials("external-jwt"))

    assert user is not None
    assert user.identity == "local-user-id"
    assert user.display_name == "external@example.com"
    assert user.access_token == "external-jwt"


async def test_get_user_service_user_uses_api_v1_auth_me_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {"id": "user-1", "email": "demo@example.com"}

    class _AsyncClient:
        captured_url = ""

        def __init__(self, timeout: float) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str]) -> _Response:
            self.__class__.captured_url = url
            assert headers == {"Authorization": "Bearer jwt-token"}
            return _Response()

    monkeypatch.setattr(auth.config, "USER_SERVICE_URL", "http://user-service:8090")
    monkeypatch.setattr("httpx.AsyncClient", _AsyncClient)

    assert await auth._get_user_service_user("jwt-token") == {
        "id": "user-1",
        "email": "demo@example.com",
    }
    assert _AsyncClient.captured_url == "http://user-service:8090/api/v1/auth/me"

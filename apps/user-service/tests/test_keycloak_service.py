from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.service import keycloak_service
from src.service.keycloak_service import KeycloakService


def test_client_credentials_payload_omits_empty_secret(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "test-client")
    monkeypatch.delenv("KEYCLOAK_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(keycloak_service._settings, "KEYCLOAK_CLIENT_SECRET", None)

    payload = KeycloakService()._client_credentials_payload()

    assert payload == {"client_id": "test-client"}


def test_client_credentials_payload_includes_secret(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "test-client")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "  test-secret  ")

    payload = KeycloakService()._client_credentials_payload()

    assert payload == {
        "client_id": "test-client",
        "client_secret": "test-secret",
    }


@pytest.mark.asyncio
async def test_refresh_token_grant_uses_login_client_credentials(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_BASE_URL", "http://keycloak:8080")
    monkeypatch.setenv("KEYCLOAK_REALM", "agenticai")
    monkeypatch.setenv("KEYCLOAK_LOGIN_CLIENT_ID", "agenticai-web")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "user-service")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "service-secret")
    captured: dict[str, object] = {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, data: dict[str, str]) -> httpx.Response:
            captured["url"] = url
            captured["data"] = data
            return httpx.Response(
                200,
                json={"access_token": "new-access-token"},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(keycloak_service.httpx, "AsyncClient", Client)

    result = await KeycloakService().refresh_token_grant("refresh-token")

    assert result == {"access_token": "new-access-token"}
    assert captured["url"] == (
        "http://keycloak:8080/realms/agenticai/protocol/openid-connect/token"
    )
    assert captured["data"] == {
        "grant_type": "refresh_token",
        "client_id": "agenticai-web",
        "refresh_token": "refresh-token",
    }


@pytest.mark.asyncio
async def test_logout_user_sessions_uses_keycloak_admin_logout_endpoint(monkeypatch):
    service = KeycloakService()
    response = SimpleNamespace(status_code=204)
    request = AsyncMock(return_value=response)
    monkeypatch.setattr(service, "_keycloak_request", request)

    assert await service.logout_user_sessions("kc-user-id") is True

    request.assert_awaited_once_with("POST", "/users/kc-user-id/logout")


def test_external_idp_payload_uses_frontend_issuer_and_backend_endpoints(monkeypatch):
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_CLIENT_ID", "idp-client")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_CLIENT_SECRET", "idp-secret")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_ISSUER_URL", "http://localhost:8081/realms/idp")
    monkeypatch.setenv(
        "EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL",
        "http://keycloak-idp:8080/realms/idp",
    )

    payload = KeycloakService()._external_idp_payload()

    assert payload["storeToken"] is True
    assert payload["config"]["syncMode"] == "FORCE"
    assert (
        payload["config"]["authorizationUrl"]
        == "http://localhost:8081/realms/idp/protocol/openid-connect/auth"
    )
    assert (
        payload["config"]["tokenUrl"]
        == "http://keycloak-idp:8080/realms/idp/protocol/openid-connect/token"
    )
    assert payload["config"]["issuer"] == "http://localhost:8081/realms/idp"


def test_external_idp_payload_prefers_env_over_runtime_settings(monkeypatch):
    KeycloakService.set_runtime_settings(
        {
            "EXTERNAL_KEYCLOAK_CLIENT_ID": "database-client",
            "EXTERNAL_KEYCLOAK_CLIENT_SECRET": "database-secret",
            "EXTERNAL_KEYCLOAK_ISSUER_URL": "http://database-idp/realms/db",
        }
    )
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_CLIENT_ID", "env-client")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_CLIENT_SECRET", "env-secret")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_ISSUER_URL", "http://env-idp/realms/env")

    payload = KeycloakService()._external_idp_payload()

    assert payload["config"]["clientId"] == "env-client"
    assert payload["config"]["clientSecret"] == "env-secret"
    assert payload["config"]["issuer"] == "http://env-idp/realms/env"
    KeycloakService.set_runtime_settings({})


@pytest.mark.asyncio
async def test_get_oidc_authorize_url_includes_keycloak_idp_hint(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_BASE_URL", "http://keycloak:8080")
    monkeypatch.setenv("KEYCLOAK_REALM", "agenticai")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "agenticai-web")

    url = await KeycloakService().get_oidc_authorize_url(
        "http://localhost:3000/auth/oidc/callback",
        state="state-123",
        idp_hint="external-keycloak",
    )

    assert "kc_idp_hint=external-keycloak" in url
    assert "state=state-123" in url


@pytest.mark.asyncio
async def test_get_oidc_authorize_url_includes_prompt_login(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_BASE_URL", "http://keycloak:8080")
    monkeypatch.setenv("KEYCLOAK_REALM", "agenticai")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "agenticai-web")

    url = await KeycloakService().get_oidc_authorize_url(
        "http://localhost:3000/auth/oidc/callback",
        prompt="login",
    )

    assert "prompt=login" in url


@pytest.mark.asyncio
async def test_follow_broker_redirects_ignores_intermediate_idp_code_state(monkeypatch):
    service = KeycloakService()
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_ISSUER_URL", "http://keycloak/realms/agenticai")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL", "http://keycloak/realms/agenticai")
    callback_uri = "http://localhost:3000/auth/oidc/callback"
    broker_url = (
        "http://keycloak/realms/agenticai/broker/external-keycloak/endpoint"
        "?code=idp-code&state=broker-state"
    )
    callback_url = f"{callback_uri}?code=sp-code&state=expected-state"

    first_response = httpx.Response(
        302,
        headers={"location": broker_url},
        request=httpx.Request("GET", "http://keycloak/auth"),
    )
    callback_response = httpx.Response(
        302,
        headers={"location": callback_url},
        request=httpx.Request("GET", broker_url),
    )

    class Client:
        async def get(self, url: str, follow_redirects: bool = False) -> httpx.Response:
            assert url == broker_url
            assert follow_redirects is False
            return callback_response

    code, _ = await service._follow_broker_redirects(
        Client(),
        first_response,
        callback_uri,
        "expected-state",
    )

    assert code == "sp-code"


@pytest.mark.asyncio
async def test_follow_broker_redirects_reports_sp_redirect_uri_rejection(monkeypatch):
    service = KeycloakService()
    monkeypatch.setenv("KEYCLOAK_BASE_URL", "http://keycloak")
    monkeypatch.setenv("KEYCLOAK_REALM", "agenticai")
    monkeypatch.setenv("KEYCLOAK_LOGIN_CLIENT_ID", "agenticai-web")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_ISSUER_URL", "http://external/realms/idp")
    callback_uri = "http://localhost:3000/auth/oidc/callback"
    auth_url = (
        "http://keycloak/realms/agenticai/protocol/openid-connect/auth"
        "?client_id=agenticai-web"
        f"&redirect_uri={callback_uri}"
    )
    response = httpx.Response(
        400,
        text="<html>Invalid parameter: redirect_uri</html>",
        request=httpx.Request("GET", auth_url),
    )

    class Client:
        async def get(self, url: str, follow_redirects: bool = False) -> httpx.Response:
            raise AssertionError("No redirects should be followed for a 400 response")

    with pytest.raises(ValueError, match="SP Keycloak rejected redirect_uri"):
        await service._follow_broker_redirects(
            Client(),
            response,
            callback_uri,
            "expected-state",
        )


@pytest.mark.asyncio
async def test_external_broker_password_login_ensures_runtime_callback_uri(monkeypatch):
    service = KeycloakService()
    callback_uri = "http://localhost:3000/auth/oidc/callback"
    authorize_url = "http://keycloak/realms/agenticai/protocol/openid-connect/auth"
    callback_url = f"{callback_uri}?code=sp-code&state=expected-state"
    calls: list[str] = []

    monkeypatch.setenv("EXTERNAL_KEYCLOAK", "true")
    monkeypatch.setattr(
        "src.service.keycloak_broker.secrets.token_urlsafe",
        lambda _: "expected-state",
    )
    monkeypatch.setattr(service, "_default_oidc_redirect_uri", lambda: callback_uri)
    monkeypatch.setattr(service, "get_external_keycloak_alias", lambda: "external-keycloak")
    monkeypatch.setattr(service, "_rewrite_keycloak_url_for_backend", lambda url: url)
    monkeypatch.setattr(
        service,
        "get_oidc_authorize_url",
        AsyncMock(return_value=authorize_url),
    )
    monkeypatch.setattr(
        service,
        "handle_oidc_callback",
        AsyncMock(return_value={"access_token": "sp-access-token"}),
    )

    async def ensure_redirect_uri(uri: str) -> dict[str, str]:
        calls.append(f"ensure:{uri}")
        return {"status": "updated"}

    monkeypatch.setattr(service, "ensure_login_client_redirect_uri", ensure_redirect_uri)

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url: str, follow_redirects: bool = False) -> httpx.Response:
            calls.append(f"get:{url}")
            return httpx.Response(
                302,
                headers={"location": callback_url},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(keycloak_service.httpx, "AsyncClient", Client)

    result = await service.external_broker_password_login(
        "external@example.com",
        "secret",
        redirect_uri=callback_uri,
    )

    assert result == {"access_token": "sp-access-token"}
    assert calls == [
        f"ensure:{callback_uri}",
        f"get:{authorize_url}",
    ]


@pytest.mark.asyncio
async def test_external_broker_password_login_requires_explicit_redirect_uri(monkeypatch):
    service = KeycloakService()
    ensure_redirect_uri = AsyncMock()

    monkeypatch.setenv("EXTERNAL_KEYCLOAK", "true")
    monkeypatch.setattr(service, "ensure_login_client_redirect_uri", ensure_redirect_uri)

    with pytest.raises(ValueError, match="redirect_uri is required"):
        await service.external_broker_password_login("external@example.com", "secret")

    ensure_redirect_uri.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_enduser_default_realm_role_adds_composite(monkeypatch):
    service = KeycloakService()
    monkeypatch.setenv("KEYCLOAK_REALM", "agenticai")
    monkeypatch.setattr(service, "create_realm_role", AsyncMock(return_value=True))
    monkeypatch.setattr(
        service,
        "get_realm_role",
        AsyncMock(
            side_effect=[
                {"id": "enduser-id", "name": "enduser"},
                {"id": "default-id", "name": "default-roles-agenticai"},
                {"id": "enduser-id", "name": "enduser"},
            ]
        ),
    )
    monkeypatch.setattr(service, "get_realm_role_composites", AsyncMock(return_value=[]))
    response = SimpleNamespace(status_code=204, raise_for_status=lambda: None)
    request = AsyncMock(return_value=response)
    monkeypatch.setattr(service, "_keycloak_request", request)

    result = await service._ensure_enduser_default_realm_role()

    assert result == {
        "status": "updated",
        "role": "default-roles-agenticai",
        "child_role": "enduser",
    }
    request.assert_awaited_once_with(
        "POST",
        "/roles-by-id/default-id/composites",
        json=[{"id": "enduser-id", "name": "enduser"}],
    )


@pytest.mark.asyncio
async def test_get_client_uuid_fetches_and_caches_keycloak_internal_client_id(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "agenticai-web")
    service = KeycloakService()
    service._client_uuid_cache = None
    service._client_uuid_cache_key = None

    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: [{"id": "client-uuid", "clientId": "agenticai-web"}],
    )
    request = AsyncMock(return_value=response)
    monkeypatch.setattr(service, "_keycloak_request", request)

    assert await service.get_client_uuid() == "client-uuid"
    assert await service.get_client_uuid() == "client-uuid"

    request.assert_awaited_once_with(
        "GET",
        "/clients?clientId=agenticai-web",
        token=None,
    )


@pytest.mark.asyncio
async def test_ensure_login_client_config_enables_direct_access_grants(monkeypatch):
    service = KeycloakService()
    monkeypatch.setenv("KEYCLOAK_LOGIN_CLIENT_ID", "agenticai-web")
    monkeypatch.setenv("KEYCLOAK_REDIRECT_URIS", "http://localhost:3000/*,*")
    monkeypatch.setenv("KEYCLOAK_WEB_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("KEYCLOAK_POST_LOGOUT_REDIRECT_URIS", "+")
    monkeypatch.setattr(service, "get_client_uuid", AsyncMock(return_value="client-uuid"))

    get_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "id": "client-uuid",
            "clientId": "agenticai-web",
            "name": "Agentic AI Web",
            "protocol": "openid-connect",
            "enabled": False,
            "publicClient": False,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "attributes": {"existing": "kept"},
        },
    )
    put_response = SimpleNamespace(status_code=204, raise_for_status=lambda: None)
    request = AsyncMock(side_effect=[get_response, put_response])
    monkeypatch.setattr(service, "_keycloak_request", request)

    result = await service.ensure_login_client_config()

    assert result["status"] == "updated"
    assert result["client_id"] == "agenticai-web"
    assert result["direct_access_grants_enabled"] is True
    request.assert_any_await("GET", "/clients/client-uuid")
    put_call = request.await_args_list[1]
    assert put_call.args == ("PUT", "/clients/client-uuid")
    payload = put_call.kwargs["json"]
    assert payload["enabled"] is True
    assert payload["publicClient"] is True
    assert payload["standardFlowEnabled"] is True
    assert payload["directAccessGrantsEnabled"] is True
    assert payload["serviceAccountsEnabled"] is False
    assert payload["redirectUris"] == ["http://localhost:3000/*", "*"]
    assert payload["webOrigins"] == ["http://localhost:3000"]
    assert payload["attributes"]["existing"] == "kept"
    assert payload["attributes"]["post.logout.redirect.uris"] == "+"
    assert "secret" not in payload


@pytest.mark.asyncio
async def test_ensure_login_client_config_preserves_existing_redirects(monkeypatch):
    service = KeycloakService()
    monkeypatch.setenv("KEYCLOAK_LOGIN_CLIENT_ID", "agenticai-web")
    monkeypatch.setenv(
        "KEYCLOAK_REDIRECT_URIS",
        "http://localhost:3000/*, http://app.example.com/auth/oidc/callback",
    )
    monkeypatch.setenv("KEYCLOAK_WEB_ORIGINS", "http://localhost:3000")
    monkeypatch.setattr(service, "get_client_uuid", AsyncMock(return_value="client-uuid"))

    get_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "id": "client-uuid",
            "clientId": "agenticai-web",
            "name": "Agentic AI Web",
            "protocol": "openid-connect",
            "redirectUris": [
                "http://manual.example.com/auth/oidc/callback",
                "http://localhost:3000/*",
            ],
            "webOrigins": ["http://manual.example.com", "http://localhost:3000"],
            "attributes": {},
        },
    )
    put_response = SimpleNamespace(status_code=204, raise_for_status=lambda: None)
    request = AsyncMock(side_effect=[get_response, put_response])
    monkeypatch.setattr(service, "_keycloak_request", request)

    await service.ensure_login_client_config()

    payload = request.await_args_list[1].kwargs["json"]
    assert payload["redirectUris"] == [
        "http://manual.example.com/auth/oidc/callback",
        "http://localhost:3000/*",
        "http://app.example.com/auth/oidc/callback",
    ]
    assert payload["webOrigins"] == [
        "http://manual.example.com",
        "http://localhost:3000",
    ]


@pytest.mark.asyncio
async def test_ensure_login_client_config_preserves_existing_post_logout_redirects(
    monkeypatch,
):
    service = KeycloakService()
    monkeypatch.setenv("KEYCLOAK_LOGIN_CLIENT_ID", "agenticai-web")
    monkeypatch.setenv("KEYCLOAK_REDIRECT_URIS", "http://localhost:3000/*")
    monkeypatch.setenv("KEYCLOAK_WEB_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv(
        "KEYCLOAK_POST_LOGOUT_REDIRECT_URIS",
        "+##http://localhost:8126/auth/ee/login",
    )
    monkeypatch.setattr(service, "get_client_uuid", AsyncMock(return_value="client-uuid"))

    get_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "id": "client-uuid",
            "clientId": "agenticai-web",
            "name": "Agentic AI Web",
            "protocol": "openid-connect",
            "redirectUris": ["http://localhost:3000/*"],
            "webOrigins": ["http://localhost:3000"],
            "attributes": {
                "post.logout.redirect.uris": "http://manual.example.com/auth/login##+",
            },
        },
    )
    put_response = SimpleNamespace(status_code=204, raise_for_status=lambda: None)
    request = AsyncMock(side_effect=[get_response, put_response])
    monkeypatch.setattr(service, "_keycloak_request", request)

    await service.ensure_login_client_config()

    payload = request.await_args_list[1].kwargs["json"]
    assert payload["attributes"]["post.logout.redirect.uris"] == (
        "http://manual.example.com/auth/login##+##http://localhost:8126/auth/ee/login"
    )


@pytest.mark.asyncio
async def test_ensure_login_client_redirect_uri_adds_new_runtime_origin(monkeypatch):
    service = KeycloakService()
    monkeypatch.setenv("KEYCLOAK_LOGIN_CLIENT_ID", "agenticai-web")
    monkeypatch.setattr(service, "get_client_uuid", AsyncMock(return_value="client-uuid"))

    get_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "id": "client-uuid",
            "clientId": "agenticai-web",
            "redirectUris": ["http://localhost:3000/auth/oidc/callback"],
            "webOrigins": ["http://localhost:3000"],
            "attributes": {},
        },
    )
    put_response = SimpleNamespace(status_code=204, raise_for_status=lambda: None)
    request = AsyncMock(side_effect=[get_response, put_response])
    monkeypatch.setattr(service, "_keycloak_request", request)

    result = await service.ensure_login_client_redirect_uri(
        "http://localhost:8126/auth/oidc/callback"
    )

    assert result == {
        "status": "updated",
        "client_id": "agenticai-web",
        "redirect_uri": "http://localhost:8126/auth/oidc/callback",
        "web_origin": "http://localhost:8126",
    }
    payload = request.await_args_list[1].kwargs["json"]
    assert payload["redirectUris"] == [
        "http://localhost:3000/auth/oidc/callback",
        "http://localhost:8126/auth/oidc/callback",
    ]
    assert payload["webOrigins"] == ["http://localhost:3000", "http://localhost:8126"]


@pytest.mark.asyncio
async def test_ensure_login_client_redirect_uri_adds_post_logout_uri(monkeypatch):
    service = KeycloakService()
    monkeypatch.setattr(service, "get_client_uuid", AsyncMock(return_value="client-uuid"))

    get_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "id": "client-uuid",
            "clientId": "agenticai-web",
            "redirectUris": ["http://localhost:8126/auth/oidc/callback"],
            "webOrigins": ["http://localhost:8126"],
            "attributes": {
                "post.logout.redirect.uris": "http://localhost:3000/auth/login"
            },
        },
    )
    put_response = SimpleNamespace(status_code=204, raise_for_status=lambda: None)
    request = AsyncMock(side_effect=[get_response, put_response])
    monkeypatch.setattr(service, "_keycloak_request", request)

    await service.ensure_login_client_redirect_uri(
        "http://localhost:8126/auth/oidc/callback",
        post_logout_redirect_uri="http://localhost:8126/auth/ee/login",
    )

    payload = request.await_args_list[1].kwargs["json"]
    assert payload["attributes"]["post.logout.redirect.uris"] == (
        "http://localhost:3000/auth/login##http://localhost:8126/auth/ee/login"
    )


@pytest.mark.asyncio
async def test_ensure_login_client_redirect_uri_adds_exact_post_logout_uri_when_plus_exists(
    monkeypatch,
):
    service = KeycloakService()
    monkeypatch.setattr(service, "get_client_uuid", AsyncMock(return_value="client-uuid"))

    get_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "id": "client-uuid",
            "clientId": "agenticai-web",
            "redirectUris": ["http://localhost:8126/auth/oidc/callback"],
            "webOrigins": ["+"],
            "attributes": {"post.logout.redirect.uris": "+"},
        },
    )
    put_response = SimpleNamespace(status_code=204, raise_for_status=lambda: None)
    request = AsyncMock(side_effect=[get_response, put_response])
    monkeypatch.setattr(service, "_keycloak_request", request)

    await service.ensure_login_client_redirect_uri(
        "http://localhost:8126/auth/oidc/callback",
        post_logout_redirect_uri="http://localhost:8126/auth/ee/login",
    )

    payload = request.await_args_list[1].kwargs["json"]
    assert payload["attributes"]["post.logout.redirect.uris"] == (
        "+##http://localhost:8126/auth/ee/login"
    )


@pytest.mark.asyncio
async def test_ensure_login_client_redirect_uri_skips_when_wildcard_covers_uri(monkeypatch):
    service = KeycloakService()
    monkeypatch.setattr(service, "get_client_uuid", AsyncMock(return_value="client-uuid"))

    get_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "id": "client-uuid",
            "clientId": "agenticai-web",
            "redirectUris": ["http://localhost:8126/*"],
            "webOrigins": ["+"],
        },
    )
    request = AsyncMock(return_value=get_response)
    monkeypatch.setattr(service, "_keycloak_request", request)

    result = await service.ensure_login_client_redirect_uri(
        "http://localhost:8126/auth/oidc/callback"
    )

    assert result["status"] == "exists"
    assert request.await_count == 1


@pytest.mark.asyncio
async def test_ensure_external_identity_provider_removes_legacy_mapper(monkeypatch):
    service = KeycloakService()
    monkeypatch.setenv("EXTERNAL_KEYCLOAK", "true")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_CLIENT_ID", "external-client")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_CLIENT_SECRET", "external-secret")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_ISSUER_URL", "http://idp/realms/external")

    get_response = SimpleNamespace(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: {"alias": "external-keycloak"},
    )
    put_response = SimpleNamespace(status_code=204, raise_for_status=lambda: None)
    request = AsyncMock(side_effect=[get_response, put_response])
    monkeypatch.setattr(service, "_keycloak_request", request)
    monkeypatch.setattr(
        service,
        "_ensure_enduser_default_realm_role",
        AsyncMock(return_value={"status": "exists"}),
    )
    remove_mapper = AsyncMock(return_value={"status": "deleted", "name": "assign-enduser-role"})
    monkeypatch.setattr(service, "_remove_external_enduser_mapper", remove_mapper)
    ensure_groups_mappers = AsyncMock(
        return_value={
            "identity_provider": {"status": "created"},
            "client": {"status": "created"},
        }
    )
    monkeypatch.setattr(service, "_ensure_external_groups_mappers", ensure_groups_mappers)
    monkeypatch.setattr(
        service,
        "ensure_external_client_redirect_uri",
        AsyncMock(return_value={"status": "skipped"}),
    )

    result = await service.ensure_external_identity_provider()

    assert result["mapper"] == {"status": "deleted", "name": "assign-enduser-role"}
    assert result["groups_mapper"] == {
        "identity_provider": {"status": "created"},
        "client": {"status": "created"},
    }
    remove_mapper.assert_awaited_once_with("external-keycloak")
    ensure_groups_mappers.assert_awaited_once_with("external-keycloak")


@pytest.mark.asyncio
async def test_remove_external_enduser_mapper_deletes_hardcoded_role_mapper(monkeypatch):
    service = KeycloakService()
    get_response = SimpleNamespace(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: [
            {
                "id": "mapper-id",
                "name": "role mapper",
                "identityProviderMapper": "oidc-hardcoded-role-idp-mapper",
                "config": {"role": "enduser"},
            }
        ],
    )
    delete_response = SimpleNamespace(status_code=204, raise_for_status=lambda: None)
    request = AsyncMock(side_effect=[get_response, delete_response])
    monkeypatch.setattr(service, "_keycloak_request", request)

    result = await service._remove_external_enduser_mapper("external-keycloak")

    assert result == {"status": "deleted", "name": "assign-enduser-role"}
    request.assert_any_await(
        "DELETE",
        "/identity-provider/instances/external-keycloak/mappers/mapper-id",
    )


@pytest.mark.asyncio
async def test_ensure_external_groups_claim_mapper_creates_attribute_importer(monkeypatch):
    service = KeycloakService()
    get_response = SimpleNamespace(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: [],
    )
    create_response = SimpleNamespace(status_code=201, raise_for_status=lambda: None)
    request = AsyncMock(side_effect=[get_response, create_response])
    monkeypatch.setattr(service, "_keycloak_request", request)

    result = await service._ensure_external_groups_claim_mapper("external-keycloak")

    assert result == {"status": "created", "name": "import-groups-claim"}
    create_call = request.await_args_list[1]
    assert create_call.args == (
        "POST",
        "/identity-provider/instances/external-keycloak/mappers",
    )
    assert create_call.kwargs["json"] == {
        "name": "import-groups-claim",
        "identityProviderAlias": "external-keycloak",
        "identityProviderMapper": "oidc-user-attribute-idp-mapper",
        "config": {
            "claim": "groups",
            "user.attribute": "groups",
            "syncMode": "INHERIT",
        },
    }


@pytest.mark.asyncio
async def test_ensure_login_client_groups_protocol_mapper_creates_claim_mapper(monkeypatch):
    service = KeycloakService()
    monkeypatch.setenv("KEYCLOAK_LOGIN_CLIENT_ID", "agenticai-web")
    monkeypatch.setattr(service, "get_client_uuid", AsyncMock(return_value="client-uuid"))
    get_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: [],
    )
    create_response = SimpleNamespace(status_code=201, raise_for_status=lambda: None)
    request = AsyncMock(side_effect=[get_response, create_response])
    monkeypatch.setattr(service, "_keycloak_request", request)

    result = await service._ensure_login_client_groups_protocol_mapper()

    assert result == {"status": "created", "name": "groups", "client_id": "agenticai-web"}
    create_call = request.await_args_list[1]
    assert create_call.args == (
        "POST",
        "/clients/client-uuid/protocol-mappers/models",
    )
    payload = create_call.kwargs["json"]
    assert payload["protocolMapper"] == "oidc-usermodel-attribute-mapper"
    assert payload["config"]["user.attribute"] == "groups"
    assert payload["config"]["claim.name"] == "groups"
    assert payload["config"]["id.token.claim"] == "true"


@pytest.mark.asyncio
async def test_set_client_role_replaces_existing_direct_client_role_mappings(monkeypatch):
    service = KeycloakService()
    monkeypatch.setattr(
        service,
        "get_user_client_roles",
        AsyncMock(return_value=[{"name": "enduser"}, {"name": "enterprise-admin"}]),
    )
    remove_client_role = AsyncMock(return_value=True)
    assign_client_role = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "remove_client_role", remove_client_role)
    monkeypatch.setattr(service, "assign_client_role", assign_client_role)

    assert await service.set_client_role("kc-user-id", "enterprise-admin") is True

    remove_client_role.assert_awaited_once_with("kc-user-id", "enduser", client_id=None)
    assign_client_role.assert_awaited_once_with(
        "kc-user-id",
        "enterprise-admin",
        client_id=None,
    )

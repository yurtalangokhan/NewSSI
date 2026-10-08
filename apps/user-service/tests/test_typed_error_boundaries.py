from unittest.mock import AsyncMock

import httpx
import pytest
from error_contract import (
    DatabaseConnectionError,
    DependencyRateLimitedError,
    DependencyResponseError,
    DependencyTimeoutError,
    DependencyUnavailableError,
    NotFoundError,
)
from fastapi import Request, Response

from src.api import dependencies
from src.controller.auth_controller import AuthController
from src.service import keycloak_service
from src.service.keycloak_service import KeycloakService


def _response(status_code: int, payload) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("GET", "https://keycloak.test/admin/clients"),
    )


@pytest.mark.asyncio
async def test_get_client_uuid_distinguishes_missing_from_malformed(monkeypatch):
    service = KeycloakService()
    service._client_uuid_cache.clear()
    request = AsyncMock(side_effect=[_response(200, []), _response(200, {"id": "bad"})])
    monkeypatch.setattr(service, "_keycloak_request", request)

    with pytest.raises(NotFoundError):
        await service.get_client_uuid(client_id="missing")
    with pytest.raises(DependencyResponseError):
        await service.get_client_uuid(client_id="malformed")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (
            httpx.ReadTimeout("slow", request=httpx.Request("POST", "https://kc/token")),
            DependencyTimeoutError,
        ),
        (
            httpx.ConnectError("offline", request=httpx.Request("POST", "https://kc/token")),
            DependencyUnavailableError,
        ),
    ],
)
async def test_password_grant_maps_transport_failures(monkeypatch, failure, expected):
    monkeypatch.setenv("KEYCLOAK_BASE_URL", "https://keycloak.test")
    monkeypatch.setenv("KEYCLOAK_REALM", "agenticai")
    monkeypatch.setenv("KEYCLOAK_LOGIN_CLIENT_ID", "agenticai-web")

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *_args, **_kwargs):
            raise failure

    monkeypatch.setattr(
        keycloak_service, "get_shared_client", lambda _name, **_kwargs: Client()
    )

    with pytest.raises(expected):
        await KeycloakService().password_grant("user", "password")


@pytest.mark.asyncio
async def test_password_grant_maps_upstream_throttling(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_BASE_URL", "https://keycloak.test")
    monkeypatch.setenv("KEYCLOAK_REALM", "agenticai")
    monkeypatch.setenv("KEYCLOAK_LOGIN_CLIENT_ID", "agenticai-web")

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **_kwargs):
            return httpx.Response(429, request=httpx.Request("POST", url))

    monkeypatch.setattr(
        keycloak_service, "get_shared_client", lambda _name, **_kwargs: Client()
    )

    with pytest.raises(DependencyRateLimitedError):
        await KeycloakService().password_grant("user", "password")


@pytest.mark.asyncio
async def test_auth_controller_does_not_convert_dependency_failure_to_bad_request():
    controller = AuthController()
    controller.auth_service = AsyncMock()
    controller.auth_service.handle_oidc_callback.side_effect = DependencyUnavailableError()

    with pytest.raises(DependencyUnavailableError):
        await controller.oidc_callback(
            request=Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/auth/oidc/callback",
                    "headers": [],
                    "query_string": b"",
                    "server": ("test", 80),
                    "client": ("test", 1),
                    "scheme": "http",
                }
            ),
            response=Response(),
            code="code",
        )


@pytest.mark.asyncio
async def test_permission_dependency_propagates_database_outage(monkeypatch):
    class UnavailableRepository:
        async def exists_by_id(self, _user_id):
            raise DatabaseConnectionError()

    # The permission dependency imports the repository inside its body.
    monkeypatch.setattr("src.repository.UserRepository", UnavailableRepository)

    with pytest.raises(DatabaseConnectionError):
        await dependencies.require_permission("user:list")(
            Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/",
                    "headers": [],
                    "query_string": b"",
                    "server": ("test", 80),
                    "client": ("test", 1),
                    "scheme": "http",
                }
            ),
            "00000000-0000-0000-0000-000000000001",
        )


@pytest.mark.asyncio
async def test_duplicate_organization_uses_conflict_error():
    from error_contract import ConflictError

    from src.service.organization_service import OrganizationService

    service = OrganizationService()
    service.repo.get_by_code = AsyncMock(return_value={"code": "taken"})
    with pytest.raises(ConflictError):
        await service.create_organization("name", "taken")


@pytest.mark.asyncio
async def test_login_client_malformed_response_does_not_create_client(monkeypatch):
    service = KeycloakService()
    monkeypatch.setattr(service, "get_client_uuid", AsyncMock(return_value="uuid"))
    request = AsyncMock(return_value=_response(200, []))
    monkeypatch.setattr(service, "_keycloak_request", request)
    with pytest.raises(DependencyResponseError):
        await service.ensure_login_client_config()
    assert request.await_count == 1


@pytest.mark.asyncio
async def test_bulk_membership_retains_typed_validation_failures():
    from error_contract import ConflictError

    from src.service.user_organization_service import UserOrganizationService

    service = UserOrganizationService.__new__(UserOrganizationService)
    service.assign_user_to_organization = AsyncMock(side_effect=ConflictError())
    result = await service.bulk_assign_users(user_ids=["user"], organization_id="organization")
    assert result["successes"] == []
    assert result["errors"][0]["user_id"] == "user"

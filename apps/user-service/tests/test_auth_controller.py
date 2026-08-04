from unittest.mock import AsyncMock

import pytest
from fastapi import Response
from starlette.requests import Request

from src.controller.auth_controller import AuthController


def _build_request(path: str, query_string: bytes = b"") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": query_string,
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    }
    return Request(scope)


def _all_set_cookie_headers(response: Response) -> str:
    return "\n".join(
        value.decode("latin1")
        for key, value in response.raw_headers
        if key.decode("latin1").lower() == "set-cookie"
    )


@pytest.mark.asyncio
async def test_oidc_callback_sets_session_cookies():
    controller = AuthController()
    controller.auth_service = AsyncMock()
    controller.auth_service.handle_oidc_callback.return_value = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "id_token": "id-token",
    }

    request = _build_request("/auth/oidc/callback")
    response = Response()

    result = await controller.oidc_callback(
        request=request,
        response=response,
        code="auth-code",
        redirect_uri="http://localhost:3000/auth/oidc/callback",
    )

    set_cookie = _all_set_cookie_headers(response)

    assert result["access_token"] == "access-token"
    assert "access_token=access-token" in set_cookie
    assert "refresh_token=refresh-token" in set_cookie
    assert "id_token=id-token" in set_cookie


@pytest.mark.asyncio
async def test_oidc_callback_without_id_token_does_not_set_id_cookie():
    controller = AuthController()
    controller.auth_service = AsyncMock()
    controller.auth_service.handle_oidc_callback.return_value = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
    }

    request = _build_request("/auth/oidc/callback")
    response = Response()

    await controller.oidc_callback(
        request=request,
        response=response,
        code="auth-code",
        redirect_uri="http://localhost:3000/auth/oidc/callback",
    )

    set_cookie = _all_set_cookie_headers(response)

    assert "access_token=access-token" in set_cookie
    assert "refresh_token=refresh-token" in set_cookie
    assert "id_token=" not in set_cookie


def test_set_cookies_skips_oversized_id_token_cookie():
    controller = AuthController()
    response = Response()

    controller._set_cookies(
        response=response,
        access_token="access-token",
        refresh_token="refresh-token",
        id_token="x" * 5000,
    )

    set_cookie = _all_set_cookie_headers(response)

    assert "access_token=access-token" in set_cookie
    assert "refresh_token=refresh-token" in set_cookie
    assert "id_token=" not in set_cookie


def test_set_cookies_skips_id_token_when_auth_cookie_headers_exceed_proxy_budget():
    controller = AuthController()
    response = Response()

    controller._set_cookies(
        response=response,
        access_token="a" * 1800,
        refresh_token="r" * 1800,
        id_token="i" * 1200,
    )

    set_cookie = _all_set_cookie_headers(response)

    assert "access_token=" in set_cookie
    assert "refresh_token=" in set_cookie
    assert "id_token=" not in set_cookie


@pytest.mark.asyncio
async def test_external_login_passes_redirect_uri_to_auth_service():
    controller = AuthController()
    controller.auth_service = AsyncMock()
    controller.auth_service.external_keycloak_login.return_value = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
    }
    request = _build_request("/auth/external/login")
    response = Response()

    await controller.external_login(
        request=request,
        response=response,
        username="external@example.com",
        password="secret",
        redirect_uri="http://localhost:3000/auth/oidc/callback",
    )

    controller.auth_service.external_keycloak_login.assert_awaited_once_with(
        "external@example.com",
        "secret",
        redirect_uri="http://localhost:3000/auth/oidc/callback",
    )

import base64
import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import Response
from starlette.requests import Request

from src.controller.auth_controller import AuthController


def _build_request(
    path: str,
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers or [],
        "query_string": query_string,
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    }
    return Request(scope)


def _unsigned_jwt(claims: dict) -> str:
    def segment(payload: dict) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
            .decode("ascii")
            .rstrip("=")
        )

    return f"{segment({'alg': 'none'})}.{segment(claims)}.signature"


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


def test_set_cookies_uses_token_lifetimes_from_the_identity_provider():
    """Cookie lifetimes must track the tokens they carry.

    Hardcoding 1h / 30d meant the browser kept sending an access-token cookie
    long after Keycloak had expired it, and kept a refresh_token cookie for a
    month past the SSO session idle timeout - so the app looked signed in and
    then failed to refresh.
    """
    controller = AuthController()
    response = Response()

    controller._set_cookies(
        response=response,
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=300,
        refresh_expires_in=1800,
    )

    set_cookie = _all_set_cookie_headers(response)

    assert "access_token=access-token; HttpOnly; Max-Age=300" in set_cookie
    assert "refresh_token=refresh-token; HttpOnly; Max-Age=1800" in set_cookie


def test_set_cookies_falls_back_when_lifetimes_are_missing_or_zero():
    controller = AuthController()
    response = Response()

    controller._set_cookies(
        response=response,
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=None,
        refresh_expires_in=0,
    )

    set_cookie = _all_set_cookie_headers(response)

    assert "Max-Age=3600" in set_cookie
    assert f"Max-Age={30 * 86400}" in set_cookie


@pytest.mark.asyncio
async def test_refresh_forwards_keycloak_lifetimes_to_cookies():
    controller = AuthController()
    controller.auth_service = AsyncMock()
    controller.auth_service.refresh_access_token.return_value = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 300,
        "refresh_expires_in": 1800,
    }

    request = _build_request(
        "/auth/refresh",
        headers=[(b"cookie", b"refresh_token=old-refresh")],
    )
    response = Response()

    await controller.refresh(request=request, response=response)

    set_cookie = _all_set_cookie_headers(response)

    assert "access_token=new-access; HttpOnly; Max-Age=300" in set_cookie
    assert "refresh_token=new-refresh; HttpOnly; Max-Age=1800" in set_cookie


def test_current_token_lifetime_reads_the_bearer_token():
    """/me must expose the access-token window.

    Without these fields `getSecondsUntilExpiration` returns null on the web
    client, its proactive refresh timer never arms, and the session is only
    ever renewed reactively.
    """
    controller = AuthController()
    issued_at = int(time.time()) - 60
    token = _unsigned_jwt({"exp": issued_at + 300, "iat": issued_at})

    request = _build_request(
        "/auth/me",
        headers=[(b"authorization", f"Bearer {token}".encode())],
    )

    lifetime = controller._current_token_lifetime(request)

    assert lifetime["current_token_expiry_length"] == 300
    assert (
        lifetime["current_token_created_at"] == datetime.fromtimestamp(issued_at, UTC).isoformat()
    )


def test_current_token_lifetime_falls_back_to_the_access_token_cookie():
    controller = AuthController()
    issued_at = int(time.time())
    token = _unsigned_jwt({"exp": issued_at + 900, "iat": issued_at})

    request = _build_request(
        "/auth/me",
        headers=[(b"cookie", f"access_token={token}".encode())],
    )

    assert controller._current_token_lifetime(request)["current_token_expiry_length"] == 900


def test_current_token_lifetime_is_empty_without_a_usable_token():
    controller = AuthController()

    assert controller._current_token_lifetime(_build_request("/auth/me")) == {}
    assert (
        controller._current_token_lifetime(
            _build_request(
                "/auth/me",
                headers=[(b"cookie", b"access_token=not-a-jwt")],
            )
        )
        == {}
    )

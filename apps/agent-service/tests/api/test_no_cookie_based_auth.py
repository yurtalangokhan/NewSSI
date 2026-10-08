"""Ek B (borderline finding, resolved): the platform's auth model is bearer-
token only. Reading fastapiusersauth/session/access_token/id_token cookies
as an authentication fallback let a browser that merely had one of those
cookies set authenticate a cross-origin request without ever holding the
real token -- a CSRF-adjacent risk. Production traffic already goes through
fetch() with an explicit Authorization header (verified: no EventSource
usage, and the only cookie-setting code path is a NODE_ENV=development
debug helper), so the fallback was pure attack surface with no legitimate
use.
"""

from fastapi import Request
import pytest

from api.dependencies import (
    _extract_auth_token,
    extract_auth_token_from_request,
    require_user,
)
from core.exceptions import UnauthorizedError
from integrations.user_service_client import set_current_access_token


def _request_with_cookies(cookies: dict[str, str]) -> Request:
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    scope = {
        "type": "http",
        "headers": [(b"cookie", cookie_header.encode())],
        "method": "GET",
        "path": "/",
    }
    return Request(scope)


@pytest.mark.parametrize("cookie_name", ["fastapiusersauth", "session", "access_token", "id_token"])
def test_extract_auth_token_ignores_every_legacy_cookie(cookie_name):
    request = _request_with_cookies({cookie_name: "cookie-supplied-token"})
    assert _extract_auth_token(request) is None


def test_extract_auth_token_still_honours_the_bearer_header():
    request = _request_with_cookies({})
    request.scope["headers"].append((b"authorization", b"Bearer real-token"))
    assert _extract_auth_token(request) == "real-token"


@pytest.mark.asyncio
async def test_require_user_rejects_a_cookie_only_request_when_keycloak_is_on(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str("test-secret"))
    request = _request_with_cookies({"fastapiusersauth": "cookie-supplied-token"})

    with pytest.raises(UnauthorizedError):
        await require_user(request=request)


def test_extract_auth_token_from_request_uses_the_context_var_not_cookies():
    # require_user populates this ContextVar from the validated Authorization
    # header; downstream code should read it from there, never re-derive a
    # token by scanning request.cookies.
    set_current_access_token("context-token")
    try:
        request = _request_with_cookies({"session": "cookie-token"})
        assert extract_auth_token_from_request(request) == "context-token"
    finally:
        set_current_access_token(None)


def test_extract_auth_token_from_request_falls_back_to_the_header_not_cookies():
    request_scope = {
        "type": "http",
        "headers": [
            (b"authorization", b"Bearer header-token"),
            (b"cookie", b"session=cookie-token"),
        ],
        "method": "GET",
        "path": "/",
    }
    request = Request(request_scope)
    set_current_access_token(None)
    assert extract_auth_token_from_request(request) == "header-token"
